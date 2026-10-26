#!/usr/bin/python3
import hashlib
import hmac
import base64
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import time
import uuid
import plistlib
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_file, session
from werkzeug.middleware.proxy_fix import ProxyFix

APP_DIR = Path('/var/lib/ikev2-manager')
DB_PATH = APP_DIR / 'panel.sqlite3'
CONFIG_DIR = Path('/etc/ikev2-manager')
SETUP_TOKEN_FILE = CONFIG_DIR / 'setup-token'
DOMAIN_FILE = CONFIG_DIR / 'domain'
CA_FILE = APP_DIR / 'server-ca.pem'
HELPER = '/usr/local/sbin/ikev2-panel-helper'
USER_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
VPN_PASS_RE = re.compile(r'^[A-Za-z0-9_.!@#%+=:-]{4,128}$')
ADMIN_PASS_MIN = 14

APP = Flask(__name__)
APP.secret_key = Path('/etc/ikev2-manager/session.key').read_text().strip()
APP.wsgi_app = ProxyFix(APP.wsgi_app, x_for=1, x_proto=1, x_host=1)
APP.config.update(
    SESSION_COOKIE_NAME='vpnmgr', SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Strict',
    PERMANENT_SESSION_LIFETIME=8 * 60 * 60, MAX_CONTENT_LENGTH=64 * 1024,
)

def now():
    return int(time.time())

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=10000')
    return con

def initialize_db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.executescript('''
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL, created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS vpn_users (
        id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
        vpn_password TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
        note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
        quota_bytes INTEGER NOT NULL DEFAULT 30000000000,
        used_up_bytes INTEGER NOT NULL DEFAULT 0,
        used_down_bytes INTEGER NOT NULL DEFAULT 0,
        expires_at INTEGER,
        max_connections INTEGER NOT NULL DEFAULT 1,
        protocols TEXT NOT NULL DEFAULT 'ikev2',
        portal_password_hash TEXT,
        portal_password_changed INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS login_limits (
        ip TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start INTEGER NOT NULL,
        locked_until INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS portal_sessions (
        token_hash TEXT PRIMARY KEY,
        vpn_user_id INTEGER NOT NULL REFERENCES vpn_users(id) ON DELETE CASCADE,
        csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS renewal_requests (
        id INTEGER PRIMARY KEY, vpn_user_id INTEGER NOT NULL REFERENCES vpn_users(id) ON DELETE CASCADE,
        plan_id INTEGER, note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
        created_at INTEGER NOT NULL, reviewed_at INTEGER, reviewed_by TEXT NOT NULL DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, days INTEGER NOT NULL,
        quota_bytes INTEGER NOT NULL, price INTEGER NOT NULL DEFAULT 0,
        protocol TEXT NOT NULL DEFAULT 'all', enabled INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS sales_orders (
        id INTEGER PRIMARY KEY, telegram_id INTEGER NOT NULL, telegram_name TEXT NOT NULL DEFAULT '',
        plan_id INTEGER NOT NULL REFERENCES plans(id), proof_file_id TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'awaiting_payment', vpn_user_id INTEGER REFERENCES vpn_users(id),
        created_at INTEGER NOT NULL, reviewed_at INTEGER, reviewed_by TEXT NOT NULL DEFAULT '',
        delivery_pending INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS usage_samples (
        sample_key TEXT PRIMARY KEY, vpn_user_id INTEGER NOT NULL REFERENCES vpn_users(id) ON DELETE CASCADE,
        protocol TEXT NOT NULL, bytes_up INTEGER NOT NULL DEFAULT 0,
        bytes_down INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS wireguard_peers (
        id INTEGER PRIMARY KEY, vpn_user_id INTEGER NOT NULL REFERENCES vpn_users(id) ON DELETE CASCADE,
        label TEXT NOT NULL, public_key TEXT NOT NULL UNIQUE, assigned_ip TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT ''
      );
    ''')
    existing = {r[1] for r in con.execute('PRAGMA table_info(vpn_users)').fetchall()}
    migrations = {
      'quota_bytes': 'INTEGER NOT NULL DEFAULT 30000000000',
      'used_up_bytes': 'INTEGER NOT NULL DEFAULT 0',
      'used_down_bytes': 'INTEGER NOT NULL DEFAULT 0',
      'expires_at': 'INTEGER',
      'max_connections': 'INTEGER NOT NULL DEFAULT 1',
      'protocols': "TEXT NOT NULL DEFAULT 'ikev2'",
      'portal_password_hash': 'TEXT',
      'portal_password_changed': 'INTEGER NOT NULL DEFAULT 0',
    }
    for name, definition in migrations.items():
        if name not in existing:
            con.execute(f'ALTER TABLE vpn_users ADD COLUMN {name} {definition}')
    con.execute('CREATE INDEX IF NOT EXISTS renewal_status_idx ON renewal_requests(status,created_at)')
    con.execute('CREATE INDEX IF NOT EXISTS orders_status_idx ON sales_orders(status,created_at)')
    con.execute('CREATE INDEX IF NOT EXISTS wg_user_idx ON wireguard_peers(vpn_user_id,revoked)')
    con.commit()
    con.close()
    os.chmod(DB_PATH, 0o600)

initialize_db()

def helper(operation, payload=None, timeout=25):
    args = ['sudo', '-n', HELPER, operation]
    raw = json.dumps(payload, separators=(',', ':')) if payload is not None else ''
    proc = subprocess.run(args, input=raw, text=True, capture_output=True, timeout=timeout)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('مدیریت strongSwan پاسخ معتبر نداد؛ گزارش سرویس را بررسی کن.')
    if proc.returncode or not result.get('ok'):
        raise RuntimeError(result.get('error', proc.stderr[-800:] or 'عملیات strongSwan ناموفق بود'))
    return result

def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + '$' + digest.hex()

def verify_password(password, stored):
    try:
        salt_hex, expected = stored.split('$', 1)
        actual = hash_password(password, bytes.fromhex(salt_hex)).split('$', 1)[1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def audit(actor, action, subject=''):
    with connect() as con:
        con.execute('INSERT INTO audit_log(actor,action,subject,created_at) VALUES(?,?,?,?)', (actor, action, subject[:80], now()))

def create_session(admin_id):
    sid, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    with connect() as con:
        con.execute('INSERT INTO sessions(token_hash,admin_id,csrf,expires_at) VALUES(?,?,?,?)',
                    (hashlib.sha256(sid.encode()).hexdigest(), admin_id, csrf, now() + 8 * 60 * 60))
    session.clear()
    session.permanent = True
    session['sid'] = sid
    return csrf

def current_admin():
    sid = session.get('sid')
    if not sid:
        return None
    with connect() as con:
        row = con.execute('''SELECT a.id,a.username,s.csrf FROM sessions s JOIN admins a ON a.id=s.admin_id
          WHERE s.token_hash=? AND s.expires_at>?''', (hashlib.sha256(sid.encode()).hexdigest(), now())).fetchone()
    if not row:
        session.clear()
        return None
    g.csrf = row['csrf']
    return row

def require_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        admin = current_admin()
        if not admin:
            return jsonify(error='لطفاً دوباره وارد شو.', code='auth_required'), 401
        g.admin = admin
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            provided = request.headers.get('X-CSRF-Token', '')
            if not hmac.compare_digest(provided, g.csrf):
                return jsonify(error='درخواست معتبر نیست. صفحه را تازه‌سازی کن.', code='csrf'), 400
        return fn(*args, **kwargs)
    return wrapped

def create_portal_session(user_id):
    sid, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    with connect() as con:
        con.execute('INSERT INTO portal_sessions(token_hash,vpn_user_id,csrf,expires_at) VALUES(?,?,?,?)',
                    (hashlib.sha256(sid.encode()).hexdigest(), user_id, csrf, now() + 8 * 60 * 60))
    session.clear()
    session.permanent = True
    session['portal_sid'] = sid
    return csrf

def current_portal_user():
    sid = session.get('portal_sid')
    if not sid:
        return None
    with connect() as con:
        row = con.execute('''SELECT u.id,u.username,u.enabled,u.quota_bytes,u.used_up_bytes,
            u.used_down_bytes,u.expires_at,u.max_connections,u.portal_password_changed,u.protocols,
            s.csrf FROM portal_sessions s JOIN vpn_users u ON u.id=s.vpn_user_id
            WHERE s.token_hash=? AND s.expires_at>?''',
            (hashlib.sha256(sid.encode()).hexdigest(), now())).fetchone()
    if not row:
        session.clear()
        return None
    g.portal_csrf = row['csrf']
    return row

def require_portal_auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_portal_user()
        if not user:
            return jsonify(error='Please sign in again.', code='auth_required'), 401
        g.portal_user = user
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            provided = request.headers.get('X-CSRF-Token', '')
            if not hmac.compare_digest(provided, g.portal_csrf):
                return jsonify(error='Invalid request. Refresh the page and try again.', code='csrf'), 400
        return fn(*args, **kwargs)
    return wrapped

@APP.before_request
def enforce_host_and_size():
    allowed = {DOMAIN_FILE.read_text().strip().lower(), 'localhost', '127.0.0.1'}
    if request.host.split(':')[0].lower() not in allowed:
        return jsonify(error='Host not allowed'), 400

@APP.after_request
def security_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

def setup_needed():
    with connect() as con:
        return con.execute('SELECT 1 FROM admins LIMIT 1').fetchone() is None

@APP.get('/api/bootstrap')
def bootstrap():
    return jsonify(setupRequired=setup_needed(), domain=DOMAIN_FILE.read_text().strip())

@APP.post('/api/setup/admin')
def setup_admin():
    if not setup_needed():
        return jsonify(error='راه‌اندازی اولیه قبلاً انجام شده است.'), 409
    data = request.get_json(silent=True) or {}
    raw_username = data.get('username', '')
    username = raw_username.strip() if isinstance(raw_username, str) else ''
    password, token = data.get('password', ''), data.get('setupToken', '')
    try:
        expected = SETUP_TOKEN_FILE.read_text().strip()
    except FileNotFoundError:
        return jsonify(error='کد راه‌اندازی پیدا نشد؛ با مدیر سرور تماس بگیر.'), 403
    if not isinstance(token, str) or not hmac.compare_digest(token, expected):
        return jsonify(error='کد راه‌اندازی نادرست است.'), 403
    if not USER_RE.fullmatch(username):
        return jsonify(error='نام مدیر باید ۳ تا ۳۲ نویسه و شامل حروف انگلیسی، عدد، نقطه، خط تیره یا زیرخط باشد.'), 400
    if not isinstance(password, str) or len(password) < ADMIN_PASS_MIN or len(password) > 128:
        return jsonify(error=f'رمز مدیر باید دست‌کم {ADMIN_PASS_MIN} نویسه باشد.'), 400
    with connect() as con:
        if con.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            return jsonify(error='راه‌اندازی اولیه همزمان انجام شده است.'), 409
        cur = con.execute('INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?)', (username, hash_password(password), now()))
        admin_id = cur.lastrowid
    try:
        helper('consume-setup-token')
    except Exception:
        # The committed admin record closes setup even if token cleanup is unavailable.
        pass
    csrf = create_session(admin_id)
    audit(username, 'setup', 'admin')
    return jsonify(ok=True, csrf=csrf, username=username)

def check_login_limit(ip):
    with connect() as con:
        row = con.execute('SELECT failures,window_start,locked_until FROM login_limits WHERE ip=?', (ip,)).fetchone()
    if not row:
        return 0
    if row['locked_until'] > now():
        return row['locked_until'] - now()
    if now() - row['window_start'] > 900:
        return 0
    return 0

def record_login_failure(ip):
    with connect() as con:
        row = con.execute('SELECT failures,window_start FROM login_limits WHERE ip=?', (ip,)).fetchone()
        if not row or now() - row['window_start'] > 900:
            con.execute('INSERT OR REPLACE INTO login_limits(ip,failures,window_start,locked_until) VALUES(?,?,?,0)', (ip, 1, now()))
        else:
            fails = row['failures'] + 1
            con.execute('UPDATE login_limits SET failures=?,locked_until=? WHERE ip=?', (fails, now() + 900 if fails >= 8 else 0, ip))

@APP.post('/api/login')
def login():
    if setup_needed():
        return jsonify(error='ابتدا مدیر پنل را بساز.', code='setup_required'), 409
    ip = request.remote_addr or 'unknown'
    wait = check_login_limit(ip)
    if wait:
        return jsonify(error=f'تلاش‌های ناموفق زیاد است؛ {wait} ثانیه دیگر امتحان کن.'), 429
    data = request.get_json(silent=True) or {}
    username, password = data.get('username', ''), data.get('password', '')
    if not isinstance(username, str): username = ''
    with connect() as con:
        admin = con.execute('SELECT id,username,password_hash FROM admins WHERE username=?', (username,)).fetchone()
    if not admin or not isinstance(password, str) or not verify_password(password, admin['password_hash']):
        record_login_failure(ip)
        return jsonify(error='نام کاربری یا رمز عبور اشتباه است.'), 401
    with connect() as con:
        con.execute('DELETE FROM login_limits WHERE ip=?', (ip,))
    csrf = create_session(admin['id'])
    return jsonify(ok=True, csrf=csrf, username=admin['username'])

@APP.get('/api/portal/bootstrap')
def portal_bootstrap():
    return jsonify(domain=DOMAIN_FILE.read_text().strip(), name='Forge Connect')

@APP.post('/api/portal/login')
def portal_login():
    ip = request.remote_addr or 'unknown'
    wait = check_login_limit(ip)
    if wait:
        return jsonify(error=f'Too many attempts. Try again in {wait} seconds.'), 429
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    if not isinstance(username, str): username = ''
    if not isinstance(password, str): password = ''
    with connect() as con:
        row = con.execute('''SELECT id,username,portal_password_hash,enabled,expires_at
            FROM vpn_users WHERE username=?''', (username.strip(),)).fetchone()
    if (not row or not row['portal_password_hash']
            or not verify_password(password, row['portal_password_hash'])):
        record_login_failure(ip)
        return jsonify(error='Username or password is incorrect.'), 401
    with connect() as con:
        con.execute('DELETE FROM login_limits WHERE ip=?', (ip,))
    csrf = create_portal_session(row['id'])
    return jsonify(ok=True, csrf=csrf, username=row['username'])

@APP.get('/api/portal/me')
@require_portal_auth
def portal_me():
    user = g.portal_user
    with connect() as con:
        peer_count = con.execute('SELECT count(*) FROM wireguard_peers WHERE vpn_user_id=? AND revoked=0', (user['id'],)).fetchone()[0]
        requests = con.execute('''SELECT r.id,r.status,r.created_at,p.name AS plan_name
            FROM renewal_requests r LEFT JOIN plans p ON p.id=r.plan_id
            WHERE r.vpn_user_id=? ORDER BY r.id DESC LIMIT 5''', (user['id'],)).fetchall()
        plans = con.execute('SELECT id,name,days,quota_bytes,price,protocol FROM plans WHERE enabled=1 ORDER BY sort_order,id').fetchall()
    total_used = user['used_up_bytes'] + user['used_down_bytes']
    return jsonify(username=user['username'], csrf=g.portal_csrf,
        domain=DOMAIN_FILE.read_text().strip(), enabled=bool(user['enabled']),
        quotaBytes=user['quota_bytes'], usedBytes=total_used,
        uploadBytes=user['used_up_bytes'], downloadBytes=user['used_down_bytes'],
        expiresAt=user['expires_at'], maxConnections=user['max_connections'],protocols=user['protocols'].split(','),
        wireguardDevices=peer_count, mustChangePassword=not bool(user['portal_password_changed']),
        renewals=[{'id':r['id'],'status':r['status'],'createdAt':r['created_at'],'plan':r['plan_name']} for r in requests],
        plans=[{'id':p['id'],'name':p['name'],'days':p['days'],'quotaBytes':p['quota_bytes'],'price':p['price'],'protocol':p['protocol']} for p in plans])

@APP.post('/api/portal/logout')
@require_portal_auth
def portal_logout():
    sid = session.get('portal_sid', '')
    with connect() as con:
        con.execute('DELETE FROM portal_sessions WHERE token_hash=?', (hashlib.sha256(sid.encode()).hexdigest(),))
    session.clear()
    return jsonify(ok=True)

@APP.post('/api/portal/password')
@require_portal_auth
def portal_change_password():
    data = request.get_json(silent=True) or {}
    current, new = data.get('currentPassword',''), data.get('newPassword','')
    user_id = g.portal_user['id']
    with connect() as con:
        row = con.execute('SELECT username,vpn_password,portal_password_hash FROM vpn_users WHERE id=?', (user_id,)).fetchone()
    if not row or not isinstance(current,str) or not verify_password(current,row['portal_password_hash'] or ''):
        return jsonify(error='Current VPN password is incorrect.'), 400
    if not isinstance(new,str) or not VPN_PASS_RE.fullmatch(new):
        return jsonify(error='New VPN password must be 4–128 supported characters.'), 400
    with connect() as con:
        con.execute('UPDATE vpn_users SET vpn_password=?,portal_password_hash=?,portal_password_changed=1 WHERE id=?',
                    (new,hash_password(new),user_id))
        con.execute('DELETE FROM portal_sessions WHERE vpn_user_id=? AND token_hash<>?',
                    (user_id,hashlib.sha256(session.get('portal_sid','').encode()).hexdigest()))
    try:
        sync_enabled_users()
        sync_wireguard_peers()
        helper('revoke-user', {'username':row['username']})
    except Exception as error:
        with connect() as con: con.execute('UPDATE vpn_users SET vpn_password=? WHERE id=?',(row['vpn_password'],user_id))
        sync_enabled_users()
        return jsonify(error=str(error)),500
    audit(row['username'],'portal_password_changed',row['username'])
    return jsonify(ok=True)

@APP.get('/api/portal/renewal-requests')
@require_portal_auth
def portal_list_renewals():
    with connect() as con:
        rows=con.execute('''SELECT r.id,r.status,r.note,r.created_at,r.reviewed_at,p.name AS plan_name
            FROM renewal_requests r LEFT JOIN plans p ON p.id=r.plan_id
            WHERE r.vpn_user_id=? ORDER BY r.id DESC''',(g.portal_user['id'],)).fetchall()
    return jsonify(requests=[{'id':r['id'],'status':r['status'],'note':r['note'],'plan':r['plan_name'],
        'createdAt':r['created_at'],'reviewedAt':r['reviewed_at']} for r in rows])

@APP.post('/api/portal/renewal-requests')
@require_portal_auth
def portal_create_renewal():
    data=request.get_json(silent=True) or {}
    plan_id=data.get('planId')
    note=data.get('note','')
    if not isinstance(note,str): note=''
    note=note.strip()[:500]
    with connect() as con:
        if con.execute("SELECT 1 FROM renewal_requests WHERE vpn_user_id=? AND status='pending'",(g.portal_user['id'],)).fetchone():
            return jsonify(error='You already have a pending renewal request.'),409
        if plan_id is not None and not con.execute('SELECT 1 FROM plans WHERE id=? AND enabled=1',(plan_id,)).fetchone():
            return jsonify(error='Selected plan is not available.'),400
        cur=con.execute('INSERT INTO renewal_requests(vpn_user_id,plan_id,note,created_at) VALUES(?,?,?,?)',
            (g.portal_user['id'],plan_id,note,now()))
    audit(g.portal_user['username'],'renewal_requested',str(cur.lastrowid))
    return jsonify(ok=True,id=cur.lastrowid),201

@APP.get('/api/me')
@require_auth
def me():
    return jsonify(username=g.admin['username'], csrf=g.csrf)

@APP.post('/api/logout')
@require_auth
def logout():
    sid = session.get('sid', '')
    with connect() as con:
        con.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(sid.encode()).hexdigest(),))
    session.clear()
    return jsonify(ok=True)

@APP.post('/api/admin/credentials')
@require_auth
def update_admin():
    data = request.get_json(silent=True) or {}
    current = data.get('currentPassword', '')
    raw_name = data.get('username', '')
    new_name = raw_name.strip() if isinstance(raw_name, str) else ''
    new_pass = data.get('newPassword', '')
    with connect() as con:
        row = con.execute('SELECT id,password_hash FROM admins WHERE id=?', (g.admin['id'],)).fetchone()
    if not row or not verify_password(current, row['password_hash']):
        return jsonify(error='رمز فعلی نادرست است.'), 400
    if not USER_RE.fullmatch(new_name):
        return jsonify(error='نام مدیر نامعتبر است.'), 400
    if not isinstance(new_pass, str) or len(new_pass) < ADMIN_PASS_MIN or len(new_pass) > 128:
        return jsonify(error=f'رمز جدید باید دست‌کم {ADMIN_PASS_MIN} نویسه باشد.'), 400
    try:
        with connect() as con:
            con.execute('UPDATE admins SET username=?,password_hash=? WHERE id=?', (new_name, hash_password(new_pass), row['id']))
            con.execute('DELETE FROM sessions WHERE admin_id=?', (row['id'],))
    except sqlite3.IntegrityError:
        return jsonify(error='این نام مدیر از قبل استفاده شده است.'), 409
    csrf = create_session(row['id'])
    audit(new_name, 'admin_credentials_changed', 'admin')
    return jsonify(ok=True, csrf=csrf, username=new_name)

def sync_enabled_users():
    with connect() as con:
        rows = con.execute('''SELECT username,vpn_password,max_connections FROM vpn_users
          WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?)
          AND (quota_bytes=0 OR used_up_bytes+used_down_bytes<quota_bytes)
          AND instr(','||protocols||',',',ikev2,')>0 ORDER BY username''',(now(),)).fetchall()
    return helper('sync-users', [{'username': r['username'], 'password': r['vpn_password'],
                                  'maxConnections':r['max_connections']} for r in rows])

def active_connections():
    output = helper('list-sas').get('output', '')
    chunks = re.split(r'(?m)(?=^[^\s].*: #[0-9]+,)', output)
    active = []
    for chunk in chunks:
        line = re.search(r'(?m)^([^\s:]+): #(\d+),\s*(\w+)', chunk)
        identity = re.search(r"(?m)^\s+remote '([^']+)' @ ([^\n]+)", chunk)
        if line and identity:
            remote_text = identity.group(2).strip()
            if remote_text.startswith('['):
                remote_ip = remote_text[1:].split(']', 1)[0]
            else:
                remote_ip = remote_text.split('[', 1)[0].strip()
            bracket_values = re.findall(r'\[([^\]]+)\]', remote_text)
            virtual_ips = [value for value in bracket_values if value != remote_ip and ('.' in value or ':' in value)]
            active.append({'id': int(line.group(2)), 'state': line.group(3), 'username': identity.group(1),
                           'remote': remote_ip, 'virtualAddresses': ' '.join(virtual_ips),'protocol':'IKEv2'})
    return active

def all_active_connections():
    active=active_connections()
    try: peers=helper('wireguard-stats').get('peers',[])
    except Exception: peers=[]
    if not peers:return active
    with connect() as con:
        owners={r['public_key']:(r['username'],r['label'],r['assigned_ip']) for r in con.execute('''SELECT p.public_key,p.label,p.assigned_ip,u.username FROM wireguard_peers p JOIN vpn_users u ON u.id=p.vpn_user_id WHERE p.revoked=0 AND u.enabled=1''')}
    current=now()
    for peer in peers:
        owner=owners.get(peer['publicKey'])
        if owner and peer['latestHandshake'] and current-peer['latestHandshake']<180:
            username,label,address=owner
            active.append({'id':'wg-'+label,'username':username,'state':'ESTABLISHED','remote':'WireGuard','virtualAddresses':address,'protocol':'WireGuard'})
    return active

@APP.get('/api/dashboard')
@require_auth
def dashboard():
    active = all_active_connections()
    with connect() as con:
        total = con.execute('SELECT count(*) FROM vpn_users').fetchone()[0]
        enabled = con.execute('SELECT count(*) FROM vpn_users WHERE enabled=1').fetchone()[0]
        vstatus = helper('status').get('vpn', 'unknown')
    return jsonify(vpnStatus=vstatus, totalUsers=total, enabledUsers=enabled,
                   activeConnections=len(active), ipv6Enabled=Path('/etc/ikev2-manager/ipv6-enabled').exists(),
                   domain=DOMAIN_FILE.read_text().strip())

@APP.get('/api/users')
@require_auth
def list_users():
    active = all_active_connections()
    active_counts = {}
    for item in active:
        counts=active_counts.setdefault(item['username'],{'ikev2':0,'wireguard':0})
        counts['wireguard' if item.get('protocol')=='WireGuard' else 'ikev2']+=1
    with connect() as con:
        rows = con.execute('''SELECT id,username,enabled,note,created_at,quota_bytes,used_up_bytes,
            used_down_bytes,expires_at,max_connections,protocols,portal_password_hash,
            (SELECT count(*) FROM wireguard_peers p WHERE p.vpn_user_id=vpn_users.id AND p.revoked=0) AS wg_devices
            FROM vpn_users ORDER BY created_at DESC''').fetchall()
    return jsonify(users=[{'id': r['id'], 'username': r['username'], 'enabled': bool(r['enabled']),
                           'note': r['note'], 'createdAt': datetime.fromtimestamp(r['created_at'], timezone.utc).isoformat(),
                           'activeConnections': sum(active_counts.get(r['username'],{}).values()),
                           'ikeConnections':active_counts.get(r['username'],{}).get('ikev2',0),
                           'wireguardConnections':active_counts.get(r['username'],{}).get('wireguard',0),
                           'wireguardDevices':r['wg_devices'],
                           'quotaBytes':r['quota_bytes'],'usedBytes':r['used_up_bytes']+r['used_down_bytes'],
                           'uploadBytes':r['used_up_bytes'],'downloadBytes':r['used_down_bytes'],
                           'expiresAt':r['expires_at'],'maxConnections':r['max_connections'],
                           'protocols':r['protocols'].split(','),'portalEnabled':bool(r['portal_password_hash'])} for r in rows])

@APP.post('/api/users')
@require_auth
def create_user():
    data = request.get_json(silent=True) or {}
    raw_username = data.get('username', '')
    username = raw_username.strip() if isinstance(raw_username, str) else ''
    password = data.get('password') or secrets.token_urlsafe(15)
    raw_note = data.get('note', '')
    note = raw_note.strip()[:120] if isinstance(raw_note, str) else ''
    quota_gb=data.get('quotaGB',30)
    days=data.get('days',30)
    maximum=data.get('maxConnections',1)
    protocols=data.get('protocols',['ikev2'])
    if isinstance(quota_gb,bool) or not isinstance(quota_gb,(int,float)) or quota_gb<0 or quota_gb>100000:
        return jsonify(error='حجم مجاز نامعتبر است.'),400
    if isinstance(days,bool) or not isinstance(days,int) or days<0 or days>3650:
        return jsonify(error='مدت اعتبار نامعتبر است.'),400
    if isinstance(maximum,bool) or not isinstance(maximum,int) or maximum<1 or maximum>50:
        return jsonify(error='سقف اتصال باید بین ۱ تا ۵۰ باشد.'),400
    if not isinstance(protocols,list) or not protocols or any(p not in ('ikev2','wireguard') for p in protocols):
        return jsonify(error='پروتکل انتخاب‌شده معتبر نیست.'),400
    quota_bytes=int(quota_gb*1_000_000_000) if quota_gb else 0
    expires_at=now()+days*86400 if days else None
    if not USER_RE.fullmatch(username):
        return jsonify(error='نام کاربری باید ۳ تا ۳۲ نویسه و شامل حروف انگلیسی، عدد، نقطه، خط تیره یا زیرخط باشد.'), 400
    if not isinstance(password, str) or not VPN_PASS_RE.fullmatch(password):
        return jsonify(error='رمز VPN باید ۴ تا ۱۲۸ نویسه و فقط شامل حروف انگلیسی، عدد و . _ ! @ # % + = : - باشد.'), 400
    try:
        with connect() as con:
            con.execute('''INSERT INTO vpn_users(username,vpn_password,enabled,note,created_at,
                quota_bytes,expires_at,max_connections,protocols,portal_password_hash)
                VALUES(?,?,1,?,?,?,?,?,?,?)''',
                (username,password,note,now(),quota_bytes,expires_at,maximum,','.join(sorted(set(protocols))),hash_password(password)))
        sync_enabled_users()
        sync_wireguard_peers()
    except sqlite3.IntegrityError:
        return jsonify(error='این نام کاربری قبلاً ثبت شده است.'), 409
    except Exception as error:
        with connect() as con: con.execute('DELETE FROM vpn_users WHERE username=?', (username,))
        return jsonify(error=str(error)), 500
    audit(g.admin['username'],'user_created',username)
    return jsonify(ok=True, username=username, password=password, portalUsername=username,
        portalPassword=password, portalUrl=request.host_url.rstrip('/')+'/portal'), 201

@APP.patch('/api/users/<int:user_id>')
@require_auth
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    if not data or any(k not in ('enabled','quotaGB','days','maxConnections','protocols') for k in data):
        return jsonify(error='درخواست تغییری برای ذخیره ندارد.'),400
    with connect() as con:
        row = con.execute('SELECT * FROM vpn_users WHERE id=?', (user_id,)).fetchone()
        if not row: return jsonify(error='کاربر پیدا نشد.'), 404
        fields=[]; values=[]
        if 'enabled' in data:
            if not isinstance(data['enabled'],bool): return jsonify(error='مقدار وضعیت حساب معتبر نیست.'),400
            if data['enabled'] and ((row['expires_at'] and row['expires_at']<=now()) or (row['quota_bytes'] and row['used_up_bytes']+row['used_down_bytes']>=row['quota_bytes'])):
                return jsonify(error='اشتراک منقضی شده یا سهمیه تمام شده است؛ ابتدا تمدید یا سهمیه را افزایش دهید.'),400
            fields.append('enabled=?'); values.append(int(data['enabled']))
        if 'quotaGB' in data:
            value=data['quotaGB']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 or value>100000:return jsonify(error='حجم مجاز نامعتبر است.'),400
            fields.append('quota_bytes=?');values.append(int(value*1_000_000_000) if value else 0)
        if 'days' in data:
            value=data['days']
            if isinstance(value,bool) or not isinstance(value,int) or value<0 or value>3650:return jsonify(error='مدت اعتبار نامعتبر است.'),400
            fields.append('expires_at=?');values.append(now()+value*86400 if value else None)
        if 'maxConnections' in data:
            value=data['maxConnections']
            if isinstance(value,bool) or not isinstance(value,int) or value<1 or value>50:return jsonify(error='سقف اتصال نامعتبر است.'),400
            fields.append('max_connections=?');values.append(value)
        if 'protocols' in data:
            value=data['protocols']
            if not isinstance(value,list) or not value or any(p not in ('ikev2','wireguard') for p in value):return jsonify(error='پروتکل نامعتبر است.'),400
            fields.append('protocols=?');values.append(','.join(sorted(set(value))))
        values.append(user_id)
        con.execute('UPDATE vpn_users SET '+','.join(fields)+' WHERE id=?',values)
        enabled=bool(data.get('enabled',row['enabled']))
    try:
        sync_enabled_users()
        sync_wireguard_peers()
        if not enabled: helper('revoke-user', {'username': row['username']})
    except Exception as error:
        with connect() as con:
            for col in ('enabled','quota_bytes','expires_at','max_connections','protocols'):
                con.execute(f'UPDATE vpn_users SET {col}=? WHERE id=?',(row[col],user_id))
        sync_enabled_users()
        return jsonify(error=str(error)), 500
    audit(g.admin['username'], 'user_updated' if len(data)>1 else ('user_enabled' if enabled else 'user_disabled'), row['username'])
    return jsonify(ok=True)

@APP.post('/api/users/<int:user_id>/password')
@require_auth
def reset_vpn_password(user_id):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or secrets.token_urlsafe(15)
    if not isinstance(password, str) or not VPN_PASS_RE.fullmatch(password):
        return jsonify(error='رمز VPN باید ۴ تا ۱۲۸ نویسه و فقط شامل حروف انگلیسی، عدد و . _ ! @ # % + = : - باشد.'), 400
    with connect() as con:
        row = con.execute('SELECT username,vpn_password FROM vpn_users WHERE id=?', (user_id,)).fetchone()
        if not row: return jsonify(error='کاربر پیدا نشد.'), 404
        con.execute('UPDATE vpn_users SET vpn_password=?,portal_password_hash=?,portal_password_changed=0 WHERE id=?',
                    (password,hash_password(password),user_id))
    try:
        sync_enabled_users()
        sync_wireguard_peers()
        helper('revoke-user', {'username': row['username']})
    except Exception as error:
        with connect() as con: con.execute('UPDATE vpn_users SET vpn_password=?,portal_password_hash=? WHERE id=?',
                                            (row['vpn_password'],hash_password(row['vpn_password']),user_id))
        sync_enabled_users()
        return jsonify(error=str(error)), 500
    audit(g.admin['username'], 'user_password_reset', row['username'])
    return jsonify(ok=True, username=row['username'], password=password)

@APP.delete('/api/users/<int:user_id>')
@require_auth
def delete_user(user_id):
    with connect() as con:
        row = con.execute('SELECT username,vpn_password,enabled,note,created_at FROM vpn_users WHERE id=?', (user_id,)).fetchone()
        if not row: return jsonify(error='کاربر پیدا نشد.'), 404
        con.execute('DELETE FROM vpn_users WHERE id=?', (user_id,))
    try:
        sync_enabled_users()
        sync_wireguard_peers()
        helper('revoke-user', {'username': row['username']})
    except Exception as error:
        with connect() as con:
            con.execute('INSERT INTO vpn_users(id,username,vpn_password,enabled,note,created_at) VALUES(?,?,?,?,?,?)',
                        (user_id, row['username'], row['vpn_password'], row['enabled'], row['note'], row['created_at']))
        sync_enabled_users()
        return jsonify(error=str(error)), 500
    audit(g.admin['username'], 'user_deleted', row['username'])
    return jsonify(ok=True)

@APP.get('/api/connections')
@require_auth
def connections():
    return jsonify(connections=all_active_connections())

@APP.get('/api/ca')
@require_auth
def download_ca():
    if not CA_FILE.exists(): return jsonify(error='گواهی CA در دسترس نیست.'), 404
    return send_file(CA_FILE, mimetype='application/x-x509-ca-cert', as_attachment=True, download_name='ikev2-root-ca.pem')

@APP.get('/api/audit')
@require_auth
def audit_history():
    with connect() as con:
        rows = con.execute('SELECT actor,action,subject,created_at FROM audit_log ORDER BY id DESC LIMIT 100').fetchall()
    return jsonify(events=[{'actor': r['actor'], 'action': r['action'], 'subject': r['subject'],
                            'createdAt': datetime.fromtimestamp(r['created_at'], timezone.utc).isoformat()} for r in rows])

def bytes_for_gb(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 or value>100000:
        raise ValueError('حجم طرح باید بین صفر و ۱۰۰٬۰۰۰ گیگابایت باشد.')
    return int(value*1_000_000_000)

def clean_plan(data):
    name=data.get('name','')
    days=data.get('days')
    price=data.get('price',0)
    protocol=data.get('protocol','all')
    quota=bytes_for_gb(data.get('quotaGB',30))
    if not isinstance(name,str) or not 2<=len(name.strip())<=60: raise ValueError('نام طرح معتبر نیست.')
    if isinstance(days,bool) or not isinstance(days,int) or days<1 or days>3650: raise ValueError('مدت طرح باید بین ۱ تا ۳۶۵۰ روز باشد.')
    if isinstance(price,bool) or not isinstance(price,int) or price<0 or price>10**12: raise ValueError('قیمت نامعتبر است.')
    if protocol not in ('all','ikev2','wireguard'): raise ValueError('پروتکل طرح نامعتبر است.')
    return name.strip(),days,quota,price,protocol

@APP.get('/api/plans')
@require_auth
def admin_plans():
    with connect() as con: rows=con.execute('SELECT * FROM plans ORDER BY sort_order,id').fetchall()
    return jsonify(plans=[{'id':r['id'],'name':r['name'],'days':r['days'],'quotaBytes':r['quota_bytes'],
        'price':r['price'],'protocol':r['protocol'],'enabled':bool(r['enabled'])} for r in rows])

@APP.post('/api/plans')
@require_auth
def create_plan():
    data=request.get_json(silent=True) or {}
    try: name,days,quota,price,protocol=clean_plan(data)
    except ValueError as error: return jsonify(error=str(error)),400
    with connect() as con:
        cur=con.execute('INSERT INTO plans(name,days,quota_bytes,price,protocol,enabled,sort_order,created_at) VALUES(?,?,?,?,?,1,0,?)',
                        (name,days,quota,price,protocol,now()))
    audit(g.admin['username'],'plan_created',name)
    return jsonify(ok=True,id=cur.lastrowid),201

@APP.patch('/api/plans/<int:plan_id>')
@require_auth
def update_plan(plan_id):
    data=request.get_json(silent=True) or {}
    with connect() as con:
        old=con.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone()
    if not old:return jsonify(error='طرح پیدا نشد.'),404
    merged={'name':data.get('name',old['name']),'days':data.get('days',old['days']),
        'quotaGB':data.get('quotaGB',old['quota_bytes']/1_000_000_000),'price':data.get('price',old['price']),
        'protocol':data.get('protocol',old['protocol'])}
    try:name,days,quota,price,protocol=clean_plan(merged)
    except ValueError as error:return jsonify(error=str(error)),400
    enabled=data.get('enabled',bool(old['enabled']))
    if not isinstance(enabled,bool):return jsonify(error='وضعیت طرح نامعتبر است.'),400
    with connect() as con:
        con.execute('UPDATE plans SET name=?,days=?,quota_bytes=?,price=?,protocol=?,enabled=? WHERE id=?',
                    (name,days,quota,price,protocol,int(enabled),plan_id))
    audit(g.admin['username'],'plan_updated',name)
    return jsonify(ok=True)

@APP.delete('/api/plans/<int:plan_id>')
@require_auth
def delete_plan(plan_id):
    with connect() as con:
        row=con.execute('SELECT name FROM plans WHERE id=?',(plan_id,)).fetchone()
        if not row:return jsonify(error='طرح پیدا نشد.'),404
        con.execute('UPDATE plans SET enabled=0 WHERE id=?',(plan_id,))
    audit(g.admin['username'],'plan_disabled',row['name'])
    return jsonify(ok=True)

def store_setting(key,value):
    with connect() as con:
        con.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))

def setting(key,default=''):
    with connect() as con:
        row=con.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
    return row['value'] if row else default

@APP.get('/api/admin/settings')
@require_auth
def admin_settings():
    token=setting('telegram_token')
    return jsonify(telegramConfigured=bool(token),telegramTokenHint=(f'••••{token[-4:]}' if token else ''),
        telegramAdminChat=setting('telegram_admin_chat'),paymentCard=setting('payment_card'),
        paymentHolder=setting('payment_holder'),salesEnabled=bool(token and setting('payment_card')),
        protocols={'ikev2':True,'wireguard':True})

@APP.patch('/api/admin/settings')
@require_auth
def update_settings():
    data=request.get_json(silent=True) or {}
    allowed={'telegramToken','telegramAdminChat','paymentCard','paymentHolder','clearTelegramToken'}
    if set(data)-allowed:return jsonify(error='تنظیم ناشناخته است.'),400
    if 'telegramToken' in data:
        token=data['telegramToken']
        if not isinstance(token,str) or len(token)>160:return jsonify(error='توکن ربات نامعتبر است.'),400
        if token.strip():
            if not re.fullmatch(r'\d{5,15}:[A-Za-z0-9_-]{25,}',token.strip()):return jsonify(error='قالب توکن تلگرام معتبر نیست.'),400
            store_setting('telegram_token',token.strip())
    if data.get('clearTelegramToken') is True:store_setting('telegram_token','')
    for key,limit in (('telegramAdminChat',40),('paymentCard',40),('paymentHolder',100)):
        if key in data:
            value=data[key]
            if not isinstance(value,str) or len(value)>limit:return jsonify(error='مقدار تنظیم نامعتبر است.'),400
            store_setting({'telegramAdminChat':'telegram_admin_chat','paymentCard':'payment_card','paymentHolder':'payment_holder'}[key],value.strip())
    audit(g.admin['username'],'sales_settings_updated','telegram')
    return admin_settings()

@APP.get('/api/admin/renewals')
@require_auth
def admin_renewals():
    with connect() as con:
        rows=con.execute('''SELECT r.*,u.username,p.name AS plan_name,p.days,p.quota_bytes,p.protocol
          FROM renewal_requests r JOIN vpn_users u ON u.id=r.vpn_user_id
          LEFT JOIN plans p ON p.id=r.plan_id ORDER BY (r.status='pending') DESC,r.id DESC LIMIT 300''').fetchall()
    return jsonify(requests=[{'id':r['id'],'username':r['username'],'status':r['status'],'note':r['note'],
        'plan':r['plan_name'],'createdAt':r['created_at'],'reviewedAt':r['reviewed_at']} for r in rows])

@APP.post('/api/admin/renewals/<int:request_id>/review')
@require_auth
def review_renewal(request_id):
    data=request.get_json(silent=True) or {}
    decision=data.get('decision')
    if decision not in ('approve','reject'):return jsonify(error='تصمیم نامعتبر است.'),400
    with connect() as con:
        row=con.execute('''SELECT r.*,p.days,p.quota_bytes,p.protocol,u.username,u.expires_at
          FROM renewal_requests r JOIN vpn_users u ON u.id=r.vpn_user_id
          LEFT JOIN plans p ON p.id=r.plan_id WHERE r.id=?''',(request_id,)).fetchone()
        if not row:return jsonify(error='درخواست تمدید پیدا نشد.'),404
        if row['status']!='pending':return jsonify(error='این درخواست قبلاً بررسی شده است.'),409
        if decision=='approve':
            if row['plan_id'] and not row['days']:return jsonify(error='طرح تمدید دیگر در دسترس نیست.'),409
            if row['plan_id']:
                start=max(now(),row['expires_at'] or 0)
                protocols=row['protocol'] if row['protocol']!='all' else 'ikev2,wireguard'
                con.execute('''UPDATE vpn_users SET enabled=1,expires_at=?,quota_bytes=?,used_up_bytes=0,
                    used_down_bytes=0,protocols=? WHERE id=?''',
                    (start+row['days']*86400,row['quota_bytes'],protocols,row['vpn_user_id']))
            else:
                con.execute('UPDATE vpn_users SET enabled=1,expires_at=? WHERE id=?',
                    (max(now(),row['expires_at'] or 0)+30*86400,row['vpn_user_id']))
        status='approved' if decision=='approve' else 'rejected'
        con.execute('UPDATE renewal_requests SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?',
                    (status,now(),g.admin['username'],request_id))
    if decision=='approve':
        sync_enabled_users()
        sync_wireguard_peers()
    audit(g.admin['username'],'renewal_'+status,row['username'])
    return jsonify(ok=True,status=status)

@APP.get('/api/admin/orders')
@require_auth
def admin_orders():
    with connect() as con:
        rows=con.execute('''SELECT o.*,p.name AS plan_name,p.days,p.quota_bytes,p.price,u.username
          FROM sales_orders o JOIN plans p ON p.id=o.plan_id LEFT JOIN vpn_users u ON u.id=o.vpn_user_id
          ORDER BY (o.status='pending_review') DESC,o.id DESC LIMIT 300''').fetchall()
    return jsonify(orders=[{'id':r['id'],'telegramId':r['telegram_id'],'telegramName':r['telegram_name'],
        'plan':r['plan_name'],'days':r['days'],'quotaBytes':r['quota_bytes'],'price':r['price'],
        'status':r['status'],'username':r['username'],'hasProof':bool(r['proof_file_id']),
        'createdAt':r['created_at']} for r in rows])

def new_vpn_identity():
    for _ in range(8):
        username='fc'+uuid.uuid4().hex[:10]
        with connect() as con:
            if not con.execute('SELECT 1 FROM vpn_users WHERE username=?',(username,)).fetchone():return username
    raise RuntimeError('Could not allocate a unique VPN username')

@APP.post('/api/admin/orders/<int:order_id>/review')
@require_auth
def review_order(order_id):
    data=request.get_json(silent=True) or {}
    decision=data.get('decision')
    if decision not in ('approve','reject'):return jsonify(error='تصمیم نامعتبر است.'),400
    password=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_') for _ in range(20))
    with connect() as con:
        order=con.execute('''SELECT o.*,p.days,p.quota_bytes,p.protocol FROM sales_orders o
          JOIN plans p ON p.id=o.plan_id WHERE o.id=?''',(order_id,)).fetchone()
        if not order:return jsonify(error='سفارش پیدا نشد.'),404
        if order['status']!='pending_review':return jsonify(error='این سفارش منتظر بررسی نیست.'),409
        user_id=None
        if decision=='approve':
            username=new_vpn_identity()
            protocols=order['protocol'] if order['protocol']!='all' else 'ikev2,wireguard'
            cur=con.execute('''INSERT INTO vpn_users(username,vpn_password,enabled,note,created_at,quota_bytes,
              expires_at,max_connections,protocols,portal_password_hash) VALUES(?,?,1,?,?,?,?,1,?,?)''',
              (username,password,f'Telegram order #{order_id}',now(),order['quota_bytes'],now()+order['days']*86400,protocols,hash_password(password)))
            user_id=cur.lastrowid
            status='approved'
        else:status='rejected'
        con.execute('''UPDATE sales_orders SET status=?,vpn_user_id=?,reviewed_at=?,reviewed_by=?,delivery_pending=1 WHERE id=?''',
            (status,user_id,now(),g.admin['username'],order_id))
    if decision=='approve':
        try:sync_enabled_users()
        except Exception as error:
            with connect() as con:con.execute('UPDATE sales_orders SET status="provisioning_failed",delivery_pending=0 WHERE id=?',(order_id,))
            return jsonify(error=str(error)),500
    audit(g.admin['username'],'order_'+status,str(order_id))
    return jsonify(ok=True,status=status,username=username if user_id else None)

def user_protocols(user):
    return set(user['protocols'].split(','))

def ca_der_bytes():
    if not CA_FILE.exists(): raise FileNotFoundError('CA certificate is not installed')
    text=CA_FILE.read_text(encoding='ascii')
    raw=''.join(line.strip() for line in text.splitlines() if not line.startswith('---'))
    return base64.b64decode(raw,validate=True)

@APP.get('/api/portal/ca')
@require_portal_auth
def portal_ca():
    if not CA_FILE.exists():return jsonify(error='CA certificate is unavailable.'),404
    return send_file(CA_FILE,mimetype='application/x-x509-ca-cert',as_attachment=True,download_name='forge-connect-root-ca.pem')

@APP.get('/api/portal/profile/android')
@require_portal_auth
def android_profile():
    user=g.portal_user
    if 'ikev2' not in user_protocols(user):return jsonify(error='IKEv2 is not included in your plan.'),403
    ca=base64.b64encode(ca_der_bytes()).decode('ascii')
    profile={'uuid':str(uuid.uuid4()),'name':'Forge Connect','type':'ikev2-eap',
        'remote':{'addr':DOMAIN_FILE.read_text().strip(),'id':DOMAIN_FILE.read_text().strip(),'cert':ca},
        'local':{'eap_id':user['username']},'dns-servers':['1.1.1.1','1.0.0.1']}
    data=json.dumps(profile,ensure_ascii=False,separators=(',',':')).encode()
    return send_file(io.BytesIO(data),mimetype='application/vnd.strongswan.profile',as_attachment=True,
                     download_name='forge-connect.sswan')

@APP.get('/api/portal/profile/ios')
@require_portal_auth
def ios_profile():
    user=g.portal_user
    if 'ikev2' not in user_protocols(user):return jsonify(error='IKEv2 is not included in your plan.'),403
    host=DOMAIN_FILE.read_text().strip()
    uid=str(uuid.uuid4()); cert_uid=str(uuid.uuid4()); vpn_uid=str(uuid.uuid4())
    cert_payload={'PayloadContent':ca_der_bytes(),'PayloadDescription':'Forge Connect root CA',
        'PayloadDisplayName':'Forge Connect CA','PayloadIdentifier':'com.forgeconnect.ca.'+cert_uid,
        'PayloadType':'com.apple.security.root','PayloadUUID':cert_uid,'PayloadVersion':1}
    vpn_payload={'PayloadDescription':'Forge Connect IKEv2 VPN','PayloadDisplayName':'Forge Connect',
        'PayloadIdentifier':'com.forgeconnect.vpn.'+vpn_uid,'PayloadType':'com.apple.vpn.managed',
        'PayloadUUID':vpn_uid,'PayloadVersion':1,'VPNType':'IKEv2','IKEv2':{
            'RemoteAddress':host,'RemoteIdentifier':host,'AuthName':user['username'],
            'AuthenticationMethod':'None','ExtendedAuthEnabled':True,'DisableMOBIKE':False,
            'DeadPeerDetectionRate':'Medium','EnableCertificateRevocationCheck':False,
            'ServerCertificateIssuerCommonName':host+' VPN Root CA',
            'UseConfigurationAttributeInternalIPSubnet':True}}
    payload={'PayloadContent':[cert_payload,vpn_payload],'PayloadDescription':'Forge Connect client configuration',
        'PayloadDisplayName':'Forge Connect','PayloadIdentifier':'com.forgeconnect.profile.'+uid,
        'PayloadOrganization':'Forge Connect','PayloadRemovalDisallowed':False,
        'PayloadType':'Configuration','PayloadUUID':uid,'PayloadVersion':1}
    data=plistlib.dumps(payload,fmt=plistlib.FMT_XML,sort_keys=False)
    return send_file(io.BytesIO(data),mimetype='application/x-apple-aspen-config',as_attachment=True,
                     download_name='forge-connect.mobileconfig')

def sync_wireguard_peers():
    with connect() as con:
        rows=con.execute('''SELECT p.public_key,p.assigned_ip FROM wireguard_peers p
          JOIN vpn_users u ON u.id=p.vpn_user_id WHERE p.revoked=0 AND u.enabled=1
          AND (u.expires_at IS NULL OR u.expires_at>?)
          AND (u.quota_bytes=0 OR u.used_up_bytes+u.used_down_bytes<u.quota_bytes)
          AND instr(','||u.protocols||',',',wireguard,')>0''',(now(),)).fetchall()
    return helper('sync-wireguard',[{'publicKey':r['public_key'],'address':r['assigned_ip']} for r in rows])

@APP.get('/api/portal/wireguard/devices')
@require_portal_auth
def portal_wireguard_devices():
    with connect() as con:
        rows=con.execute('SELECT id,label,assigned_ip,created_at,revoked FROM wireguard_peers WHERE vpn_user_id=? ORDER BY id DESC',
                         (g.portal_user['id'],)).fetchall()
    return jsonify(devices=[{'id':r['id'],'label':r['label'],'address':r['assigned_ip'],'createdAt':r['created_at'],'revoked':bool(r['revoked'])} for r in rows])

@APP.post('/api/portal/wireguard/devices')
@require_portal_auth
def create_wireguard_device():
    user=g.portal_user
    with connect() as con:
        row=con.execute('SELECT protocols,enabled,expires_at,quota_bytes,used_up_bytes,used_down_bytes,max_connections FROM vpn_users WHERE id=?',(user['id'],)).fetchone()
        count=con.execute('SELECT count(*) FROM wireguard_peers WHERE vpn_user_id=? AND revoked=0',(user['id'],)).fetchone()[0]
        if not row['enabled']:return jsonify(error='Your account is disabled.'),403
        if 'wireguard' not in row['protocols'].split(','):return jsonify(error='WireGuard is not included in your plan.'),403
        if count>=row['max_connections']:return jsonify(error='You have reached the device limit for this account.'),409
        if row['expires_at'] and row['expires_at']<=now():return jsonify(error='Your subscription has expired.'),403
        if row['quota_bytes'] and row['used_up_bytes']+row['used_down_bytes']>=row['quota_bytes']:return jsonify(error='Your data allowance is used up.'),403
        label=data_label=(request.get_json(silent=True) or {}).get('label','')
        if not isinstance(label,str) or not 2<=len(label.strip())<=48 or re.search(r'[\x00-\x1f\[\]]',label):return jsonify(error='Device name must contain 2–48 safe characters.'),400
        used={r[0] for r in con.execute('SELECT assigned_ip FROM wireguard_peers').fetchall()}
        slot=next((n for n in range(2,255) if f'10.88.0.{n}/32' not in used),None)
        if slot is None:return jsonify(error='WireGuard address pool is full.'),409
    private=subprocess.run(['/usr/bin/wg','genkey'],text=True,capture_output=True,timeout=5)
    if private.returncode:return jsonify(error='WireGuard key generation failed.'),500
    private_key=private.stdout.strip()
    public=subprocess.run(['/usr/bin/wg','pubkey'],input=private_key+'\n',text=True,capture_output=True,timeout=5)
    if public.returncode:return jsonify(error='WireGuard key generation failed.'),500
    public_key=public.stdout.strip(); address=f'10.88.0.{slot}/32'
    with connect() as con:
        cur=con.execute('INSERT INTO wireguard_peers(vpn_user_id,label,public_key,assigned_ip,created_at) VALUES(?,?,?,?,?)',
                        (user['id'],label.strip(),public_key,address,now()))
        peer_id=cur.lastrowid
    try:sync_wireguard_peers()
    except Exception as error:
        with connect() as con:con.execute('DELETE FROM wireguard_peers WHERE id=?',(peer_id,))
        return jsonify(error=str(error)),500
    try:server_public=Path('/etc/wireguard/server_public').read_text().strip()
    except OSError:return jsonify(error='WireGuard server key is unavailable.'),503
    host=DOMAIN_FILE.read_text().strip()
    ipv6_enabled=Path('/etc/ikev2-manager/ipv6-enabled').exists() and Path('/etc/ikev2-manager/ipv6-enabled').read_text().strip()=='1'
    slot=int(address.split('.')[-1].split('/')[0])
    interface_address=address+(f', fd88:2026:10::{slot}/128' if ipv6_enabled else '')
    # Route IPv6 into the tunnel even on IPv4-only VPSs, where it is intentionally dropped.
    routes='0.0.0.0/0, ::/0'
    config=f'[Interface]\nPrivateKey = {private_key}\nAddress = {interface_address}\nDNS = 1.1.1.1, 1.0.0.1\n\n[Peer]\nPublicKey = {server_public}\nEndpoint = {host}:51820\nAllowedIPs = {routes}\nPersistentKeepalive = 25\n'
    audit(user['username'],'wireguard_device_created',label.strip())
    return jsonify(ok=True,id=peer_id,label=label.strip(),config=config,publicKey=public_key),201

@APP.delete('/api/portal/wireguard/devices/<int:peer_id>')
@require_portal_auth
def delete_wireguard_device(peer_id):
    with connect() as con:
        row=con.execute('SELECT public_key,label FROM wireguard_peers WHERE id=? AND vpn_user_id=? AND revoked=0',
                        (peer_id,g.portal_user['id'])).fetchone()
        if not row:return jsonify(error='Device not found.'),404
        con.execute('UPDATE wireguard_peers SET revoked=1 WHERE id=?',(peer_id,))
    try:sync_wireguard_peers()
    except Exception as error:return jsonify(error=str(error)),500
    audit(g.portal_user['username'],'wireguard_device_revoked',row['label'])
    return jsonify(ok=True)
