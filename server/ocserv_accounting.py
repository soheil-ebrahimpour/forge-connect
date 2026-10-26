#!/usr/bin/python3
"""Record per-session OpenConnect traffic and revoke exhausted accounts."""
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

DB = Path('/var/lib/ikev2-manager/panel.sqlite3')
HELPER = '/usr/local/sbin/ikev2-panel-helper'
USER_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')


def helper(operation, payload):
    result = subprocess.run([HELPER, operation], input=json.dumps(payload), text=True,
                            capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr[-500:] or result.stdout[-500:] or operation + ' failed')


def main():
    username = os.environ.get('USERNAME', '')
    if not USER_RE.fullmatch(username):
        raise ValueError('invalid OpenConnect username')
    uploaded = int(os.environ.get('STATS_BYTES_IN', '0'))
    downloaded = int(os.environ.get('STATS_BYTES_OUT', '0'))
    if min(uploaded, downloaded) < 0 or max(uploaded, downloaded) > 2**63 - 1:
        raise ValueError('invalid OpenConnect accounting counters')

    con = sqlite3.connect(DB, timeout=15)
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('PRAGMA foreign_keys=ON')
    try:
        row = con.execute('SELECT id,protocols,quota_bytes FROM vpn_users WHERE username=?',
                           (username,)).fetchone()
        if not row or 'ocserv' not in row[1].split(','):
            return
        con.execute('UPDATE vpn_users SET used_up_bytes=used_up_bytes+?, used_down_bytes=used_down_bytes+? WHERE id=?',
                    (uploaded, downloaded, row[0]))
        used = con.execute('SELECT used_up_bytes+used_down_bytes FROM vpn_users WHERE id=?',
                            (row[0],)).fetchone()[0]
        con.commit()
        exhausted = bool(row[2] and used >= row[2])
    finally:
        con.close()

    if exhausted:
        now = int(time.time())
        con = sqlite3.connect(DB, timeout=15)
        try:
            users = []
            for name, password, maximum, protocols in con.execute('''
                SELECT username,vpn_password,max_connections,protocols FROM vpn_users
                WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?)
                  AND (quota_bytes=0 OR used_up_bytes+used_down_bytes<quota_bytes)
                  AND (instr(','||protocols||',',',ikev2,')>0 OR instr(','||protocols||',',',ocserv,')>0)
            ''', (now,)):
                users.append({'username': name, 'password': password, 'maxConnections': maximum,
                              'protocols': [p for p in protocols.split(',') if p in ('ikev2', 'ocserv')]})
            peers = [{'publicKey': key, 'address': address} for key, address in con.execute('''
                SELECT w.public_key,w.assigned_ip FROM wireguard_peers w
                JOIN vpn_users u ON u.id=w.vpn_user_id
                WHERE w.revoked=0 AND u.enabled=1 AND (u.expires_at IS NULL OR u.expires_at>?)
                  AND (u.quota_bytes=0 OR u.used_up_bytes+u.used_down_bytes<u.quota_bytes)
                  AND instr(','||u.protocols||',',',wireguard,')>0
            ''', (now,))]
        finally:
            con.close()
        helper('sync-users', users)
        helper('sync-wireguard', peers)
        helper('revoke-user', {'username': username})


if __name__ == '__main__':
    main()
