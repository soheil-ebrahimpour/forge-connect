#!/usr/bin/python3
"""Collect strongSwan CHILD_SA and WireGuard counters; enforce expiry/quota."""
import json, re, sqlite3, subprocess, time
from pathlib import Path

DB=Path('/var/lib/ikev2-manager/panel.sqlite3')
HELPER='/usr/local/sbin/ikev2-panel-helper'

def call(op,payload=None):
    p=subprocess.run([HELPER,op],input=json.dumps(payload) if payload is not None else '',text=True,capture_output=True,timeout=20)
    if p.returncode: raise RuntimeError(p.stderr[-500:] or p.stdout[-500:] or op+' failed')
    return json.loads(p.stdout)

def connect():
    c=sqlite3.connect(DB,timeout=10);c.execute('PRAGMA busy_timeout=10000');c.execute('PRAGMA foreign_keys=ON');return c

def ike_samples(output):
    result={}
    blocks=re.split(r'(?m)(?=^[^\s].*: #[0-9]+,)',output)
    for block in blocks:
        top=re.search(r'(?m)^([^\s:]+): #(\d+),',block)
        user=re.search(r"(?m)^\s+remote '([^']+)'",block)
        if not top or not user: continue
        # swanctl --list-sas prints CHILD_SA counters as `in SPI, N bytes` / `out SPI, N bytes`.
        ins=re.findall(r'(?m)^\s*in\s+[^,]+,\s*(\d+)\s+bytes',block)
        outs=re.findall(r'(?m)^\s*out\s+[^,]+,\s*(\d+)\s+bytes',block)
        if ins or outs: result['ike:'+top.group(2)+':'+user.group(1)]=(user.group(1),sum(map(int,ins)),sum(map(int,outs)))
    return result

def collect():
    try: ike=ike_samples(call('list-sas')['output'])
    except Exception: ike={}
    try: wg={p['publicKey']:(int(p['rxBytes']),int(p['txBytes'])) for p in call('wireguard-stats').get('peers',[])}
    except Exception: wg={}
    c=connect(); disabled=[]; now=int(time.time())
    # Resolve current WireGuard keys to their owner.
    key_users={key:username for key,username in c.execute('SELECT w.public_key,u.username FROM wireguard_peers w JOIN vpn_users u ON u.id=w.vpn_user_id WHERE w.revoked=0')}
    samples={}
    samples.update(ike)
    for key,(up,down) in wg.items():
        user=key_users.get(key)
        if user:samples['wg:'+key]=(user,up,down)
    for sample_key,(username,up,down) in samples.items():
        row=c.execute('SELECT id,quota_bytes,used_up_bytes,used_down_bytes,enabled,expires_at FROM vpn_users WHERE username=?',(username,)).fetchone()
        if not row:continue
        old=c.execute('SELECT bytes_up,bytes_down FROM usage_samples WHERE sample_key=?',(sample_key,)).fetchone()
        du=up-(old[0] if old else 0);dd=down-(old[1] if old else 0)
        if du<0:du=up
        if dd<0:dd=down
        c.execute('INSERT INTO usage_samples(sample_key,vpn_user_id,protocol,bytes_up,bytes_down,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(sample_key) DO UPDATE SET bytes_up=excluded.bytes_up,bytes_down=excluded.bytes_down,updated_at=excluded.updated_at',(sample_key,row[0],'wireguard' if sample_key.startswith('wg:') else 'ikev2',up,down,now))
        if du or dd:c.execute('UPDATE vpn_users SET used_up_bytes=used_up_bytes+?,used_down_bytes=used_down_bytes+? WHERE id=?',(du,dd,row[0]))
    c.commit()
    for uid,username,quota,up,down,enabled,expires in c.execute('SELECT id,username,quota_bytes,used_up_bytes,used_down_bytes,enabled,expires_at FROM vpn_users'):
        exhausted=(quota and up+down>=quota) or (expires and expires<=now)
        if enabled and exhausted:
            c.execute('UPDATE vpn_users SET enabled=0 WHERE id=?',(uid,));disabled.append(username)
    c.commit()
    users=[{'username':u,'password':p,'maxConnections':m} for u,p,m in c.execute('SELECT username,vpn_password,max_connections FROM vpn_users WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?) AND (quota_bytes=0 OR used_up_bytes+used_down_bytes<quota_bytes) AND instr(','||protocols||',',',ikev2,')>0',(now,))]
    wg_peers=[{'publicKey':k,'address':a} for k,a in c.execute('''SELECT w.public_key,w.assigned_ip FROM wireguard_peers w JOIN vpn_users u ON u.id=w.vpn_user_id WHERE w.revoked=0 AND u.enabled=1 AND (u.expires_at IS NULL OR u.expires_at>?) AND (u.quota_bytes=0 OR u.used_up_bytes+u.used_down_bytes<u.quota_bytes) AND instr(','||u.protocols||',',',wireguard,')>0''',(now,))]
    c.close()
    if disabled:
        call('sync-users',users);call('sync-wireguard',wg_peers)
        for username in disabled: call('revoke-user',{'username':username})
        # Tear down WireGuard peers as soon as the account is over quota.
        for username in disabled:
            for key, in sqlite3.connect(DB).execute('SELECT public_key FROM wireguard_peers WHERE vpn_user_id=(SELECT id FROM vpn_users WHERE username=?) AND revoked=0',(username,)):
                call('revoke-wireguard-peer',{'publicKey':key})

if __name__=='__main__':
    while True:
        try: collect()
        except Exception as e: print(f'accounting iteration failed: {e}',flush=True)
        time.sleep(5)
