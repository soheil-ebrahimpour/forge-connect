#!/usr/bin/python3
"""Narrow privileged bridge between the web process and strongSwan."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

USERS_FILE = Path('/etc/swanctl/conf.d/ikev2-manager-users.conf')
SETUP_TOKEN_FILE = Path('/etc/ikev2-manager/setup-token')
VALID_USER = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
VALID_PASSWORD = re.compile(r'^[A-Za-z0-9_.!@#%+=:-]{12,128}$')
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
    seen, lines = set(), ['secrets {']
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid account')
        username, password = row.get('username', ''), row.get('password', '')
        if not isinstance(username, str) or not VALID_USER.fullmatch(username):
            raise ValueError('invalid username')
        if username in seen:
            raise ValueError('duplicate username')
        if not isinstance(password, str) or not VALID_PASSWORD.fullmatch(password):
            raise ValueError('invalid password')
        seen.add(username)
        lines.extend([f'  eap-{username} {{', f'    id = {username}', f'    secret = "{password}"', '  }'])
    lines.append('}')
    content = '\n'.join(lines) + '\n'
    USERS_FILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    old = USERS_FILE.read_bytes() if USERS_FILE.exists() else None
    fd, temp_name = tempfile.mkstemp(prefix='.ikev2-users-', dir=str(USERS_FILE.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temp_name, USERS_FILE)
        result = run([SWANCTL, '--load-creds', '--clear'])
        if result.returncode:
            if old is None:
                USERS_FILE.unlink(missing_ok=True)
            else:
                USERS_FILE.write_bytes(old)
                USERS_FILE.chmod(0o600)
            run([SWANCTL, '--load-creds', '--clear'])
            raise RuntimeError(result.stderr[-1000:] or 'swanctl credential load failed')
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {'ok': True}

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
    return {'ok': True, 'terminated': terminated}

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
    elif operation == 'list-sas':
        result = list_sas()
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
