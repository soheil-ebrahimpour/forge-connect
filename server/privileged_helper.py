#!/usr/bin/python3
"""Narrow privileged bridge between the web process and strongSwan."""
import json
import ipaddress
import grp
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

USERS_FILE = Path('/etc/swanctl/conf.d/ikev2-manager-users.conf')
RADIUS_USERS_FILE = Path('/etc/freeradius/3.0/mods-config/files/authorize')
WG_CONFIG = Path('/etc/wireguard/wg0.conf')
SETUP_TOKEN_FILE = Path('/etc/ikev2-manager/setup-token')
VALID_USER = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
VALID_PASSWORD = re.compile(r'^[A-Za-z0-9_.!@#%+=:-]{4,128}$')
SWANCTL = '/usr/sbin/swanctl'

def run(args, timeout=20):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout)

def sync_users():
    payload = sys.stdin.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError('input too large')
    rows = json.loads(payload)
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('invalid account list')
    seen, lines, radius_lines = set(), ['secrets {'], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid account')
        username, password = row.get('username', ''), row.get('password', '')
        maximum = row.get('maxConnections', 1)
        protocols = row.get('protocols', ['ikev2'])
        if not isinstance(username, str) or not VALID_USER.fullmatch(username):
            raise ValueError('invalid username')
        if username in seen:
            raise ValueError('duplicate username')
        if not isinstance(password, str) or not VALID_PASSWORD.fullmatch(password):
            raise ValueError('invalid password')
        if not isinstance(maximum, int) or maximum < 1 or maximum > 50:
            raise ValueError('invalid simultaneous connection limit')
        if not isinstance(protocols, list) or not protocols or any(p not in ('ikev2','ocserv') for p in protocols):
            raise ValueError('invalid RADIUS protocols')
        seen.add(username)
        for protocol, nas in (('ikev2','forge-ikev2'),('ocserv','forge-ocserv')):
            if protocol in protocols:
                radius_lines.extend([f'{username} Cleartext-Password := "{password}", NAS-Identifier == "{nas}"',
                                     f'    Simultaneous-Use := {maximum}',
                                     '    Fall-Through = Yes', ''])
    lines.append('}')
    content = '\n'.join(lines) + '\n'
    USERS_FILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    old = USERS_FILE.read_bytes() if USERS_FILE.exists() else None
    radius_old = RADIUS_USERS_FILE.read_bytes() if RADIUS_USERS_FILE.exists() else None
    fd, temp_name = tempfile.mkstemp(prefix='.ikev2-users-', dir=str(USERS_FILE.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        if not RADIUS_USERS_FILE.exists():
            raise RuntimeError('FreeRADIUS users file is missing')
        radius_fd, radius_temp_name = tempfile.mkstemp(prefix='.authorize-',dir=str(RADIUS_USERS_FILE.parent))
        try:
            os.fchmod(radius_fd,0o640)
            os.fchown(radius_fd,0,grp.getgrnam('freerad').gr_gid)
            with os.fdopen(radius_fd,'w',encoding='utf-8') as stream:
                stream.write('\n'.join(radius_lines) + '\n')
            os.replace(radius_temp_name,RADIUS_USERS_FILE)
        finally:
            if os.path.exists(radius_temp_name): os.unlink(radius_temp_name)
        os.replace(temp_name, USERS_FILE)
        result = run([SWANCTL, '--load-creds', '--clear'])
        if result.returncode:
            if old is None:
                USERS_FILE.unlink(missing_ok=True)
            else:
                USERS_FILE.write_bytes(old)
                USERS_FILE.chmod(0o600)
            if radius_old is not None:
                RADIUS_USERS_FILE.write_bytes(radius_old)
                RADIUS_USERS_FILE.chmod(0o640)
            run([SWANCTL, '--load-creds', '--clear'])
            raise RuntimeError(result.stderr[-1000:] or 'swanctl credential load failed')
        reload_radius = run(['/usr/bin/systemctl', 'reload', 'freeradius.service'])
        if reload_radius.returncode:
            if old is not None:
                USERS_FILE.write_bytes(old); USERS_FILE.chmod(0o600)
            if radius_old is not None:
                RADIUS_USERS_FILE.write_bytes(radius_old); RADIUS_USERS_FILE.chown(0,grp.getgrnam('freerad').gr_gid); RADIUS_USERS_FILE.chmod(0o640)
            run([SWANCTL, '--load-creds', '--clear'])
            run(['/usr/bin/systemctl','reload','freeradius.service'])
            raise RuntimeError(reload_radius.stderr[-800:] or 'could not reload FreeRADIUS')
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {'ok': True}

def sync_wireguard():
    payload = sys.stdin.read(512 * 1024 + 1)
    if len(payload) > 512 * 1024:
        raise ValueError('input too large')
    rows = json.loads(payload)
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('invalid WireGuard peer list')
    desired = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid WireGuard peer')
        key, address = row.get('publicKey',''), row.get('address','')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9+/]{43}=',key):
            raise ValueError('invalid WireGuard public key')
        try:
            parsed = ipaddress.ip_interface(address)
        except (ValueError, TypeError):
            raise ValueError('invalid WireGuard address')
        if parsed.version != 4 or parsed.network.prefixlen != 32 or not parsed.ip in ipaddress.ip_network('10.88.0.0/24'):
            raise ValueError('WireGuard address is outside the assigned pool')
        if key in desired or any(peer['v4']==str(parsed) for peer in desired.values()):
            raise ValueError('duplicate WireGuard peer or address')
        desired[key] = {'v4':str(parsed),'slot':int(parsed.ip.packed[3])}
    if not WG_CONFIG.exists():
        raise RuntimeError('WireGuard has not been configured')
    current = run(['/usr/bin/wg','show','wg0','peers'])
    if current.returncode:
        raise RuntimeError(current.stderr[-800:] or 'WireGuard interface is not active')
    current_keys = set(current.stdout.split())
    for key in current_keys - set(desired):
        removed = run(['/usr/bin/wg','set','wg0','peer',key,'remove'])
        if removed.returncode:
            raise RuntimeError(removed.stderr[-500:] or 'could not remove a WireGuard peer')
    ipv6_enabled=Path('/etc/ikev2-manager/ipv6-enabled').exists() and Path('/etc/ikev2-manager/ipv6-enabled').read_text().strip()=='1'
    for key,peer in desired.items():
        allowed=peer['v4']+(f",fd88:2026:10::{peer['slot']}/128" if ipv6_enabled else '')
        applied = run(['/usr/bin/wg','set','wg0','peer',key,'allowed-ips',allowed])
        if applied.returncode:
            raise RuntimeError(applied.stderr[-500:] or 'could not apply WireGuard peer')
    base = WG_CONFIG.read_text(encoding='utf-8').split('[Peer]')[0].rstrip() + '\n'
    for key,peer in desired.items():
        allowed=peer['v4']+(f", fd88:2026:10::{peer['slot']}/128" if ipv6_enabled else '')
        base += f'\n[Peer]\nPublicKey = {key}\nAllowedIPs = {allowed}\n'
    fd,temp_name=tempfile.mkstemp(prefix='.wg0-',dir=str(WG_CONFIG.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as stream: stream.write(base)
        os.replace(temp_name,WG_CONFIG)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)
    return {'ok':True,'peers':len(desired)}

def wireguard_stats():
    result=run(['/usr/bin/wg','show','wg0','dump'])
    if result.returncode:
        return {'ok':True,'peers':[]}
    peers=[]
    for line in result.stdout.splitlines()[1:]:
        parts=line.split('\t')
        if len(parts)<8: continue
        peers.append({'publicKey':parts[0],'allowedIps':parts[3],
                      'latestHandshake':int(parts[4] or 0),'rxBytes':int(parts[5] or 0),
                      'txBytes':int(parts[6] or 0)})
    return {'ok':True,'peers':peers}

def revoke_ike_id(ike_id):
    if not isinstance(ike_id,int) or ike_id<1:
        raise ValueError('invalid IKE session id')
    result=run([SWANCTL,'--terminate','--ike-id',str(ike_id)],timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr[-500:] or 'could not terminate IKE session')
    return {'ok':True}

def revoke_wireguard_peer(public_key):
    if not isinstance(public_key,str) or not re.fullmatch(r'[A-Za-z0-9+/]{43}=',public_key):
        raise ValueError('invalid WireGuard public key')
    result=run(['/usr/bin/wg','set','wg0','peer',public_key,'remove'])
    if result.returncode:
        raise RuntimeError(result.stderr[-500:] or 'could not remove WireGuard peer')
    return {'ok':True}

def list_sas():
    result = run([SWANCTL, '--list-sas'])
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:] or 'could not read active sessions')
    return {'ok': True, 'output': result.stdout}

def revoke_user(username):
    if not isinstance(username, str) or not VALID_USER.fullmatch(username):
        raise ValueError('invalid username')
    result = run([SWANCTL, '--list-sas'])
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:] or 'could not list sessions')
    chunks = re.split(r'(?m)(?=^[^\s].*: #[0-9]+,)', result.stdout)
    terminated = 0
    for chunk in chunks:
        identity = re.search(r"(?m)^\s+remote '([^']+)'", chunk)
        ike = re.search(r'(?m)^\S+: #(\d+),', chunk)
        if identity and ike and identity.group(1) == username:
            closed = run([SWANCTL, '--terminate', '--ike-id', ike.group(1)], timeout=12)
            if closed.returncode:
                raise RuntimeError(closed.stderr[-500:] or 'could not terminate session')
            terminated += 1
    if run(['/usr/bin/systemctl','is-active','--quiet','ocserv.service']).returncode == 0:
        run(['/usr/bin/occtl','terminate','user',username],timeout=12)
    return {'ok': True, 'terminated': terminated}

def revoke_ocserv_user(username):
    if not isinstance(username, str) or not VALID_USER.fullmatch(username):
        raise ValueError('invalid username')
    if run(['/usr/bin/systemctl','is-active','--quiet','ocserv.service']).returncode != 0:
        return {'ok':True,'terminated':False}
    result=run(['/usr/bin/occtl','terminate','user',username],timeout=12)
    if result.returncode and 'not connected' not in result.stderr.lower():
        raise RuntimeError(result.stderr[-500:] or 'could not terminate OpenConnect session')
    return {'ok':True,'terminated':result.returncode==0}

def ocserv_users():
    if run(['/usr/bin/systemctl','is-active','--quiet','ocserv.service']).returncode != 0:
        return {'ok':True,'users':[]}
    result=run(['/usr/bin/occtl','--json','show','users'],timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr[-800:] or 'could not read OpenConnect sessions')
    try:
        data=json.loads(result.stdout or '[]')
    except json.JSONDecodeError:
        raise RuntimeError('occtl returned invalid JSON')
    return {'ok':True,'users':data}

def status():
    unit = run(['/usr/bin/systemctl', 'is-active', 'strongswan.service'])
    return {'ok': True, 'vpn': unit.stdout.strip() if unit.returncode == 0 else 'inactive'}

def consume_setup_token():
    SETUP_TOKEN_FILE.unlink(missing_ok=True)
    return {'ok': True}

def main():
    if len(sys.argv) != 2:
        raise ValueError('operation required')
    operation = sys.argv[1]
    if operation == 'sync-users':
        result = sync_users()
    elif operation == 'sync-wireguard':
        result = sync_wireguard()
    elif operation == 'wireguard-stats':
        result = wireguard_stats()
    elif operation == 'revoke-ike-id':
        body = json.loads(sys.stdin.read(4096))
        result = revoke_ike_id(body.get('ikeId'))
    elif operation == 'revoke-wireguard-peer':
        body = json.loads(sys.stdin.read(4096))
        result = revoke_wireguard_peer(body.get('publicKey',''))
    elif operation == 'list-sas':
        result = list_sas()
    elif operation == 'ocserv-users':
        result = ocserv_users()
    elif operation == 'revoke-ocserv-user':
        body=json.loads(sys.stdin.read(4096))
        result=revoke_ocserv_user(body.get('username',''))
    elif operation == 'revoke-user':
        body = json.loads(sys.stdin.read(4096))
        result = revoke_user(body.get('username', ''))
    elif operation == 'status':
        result = status()
    elif operation == 'consume-setup-token':
        result = consume_setup_token()
    else:
        raise ValueError('operation not allowed')
    print(json.dumps(result))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        raise SystemExit(1)
