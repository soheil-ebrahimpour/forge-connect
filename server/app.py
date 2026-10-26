#!/usr/bin/python3
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import time
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
VPN_PASS_RE = re.compile(r'^[A-Za-z0-9_.!@#%+=:-]{12,128}$')
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
        note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
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
    ''')
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
        rows = con.execute('SELECT username,vpn_password FROM vpn_users WHERE enabled=1 ORDER BY username').fetchall()
    return helper('sync-users', [{'username': r['username'], 'password': r['vpn_password']} for r in rows])

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
                           'remote': remote_ip, 'virtualAddresses': ' '.join(virtual_ips)})
    return active

@APP.get('/api/dashboard')
@require_auth
def dashboard():
    active = active_connections()
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
    active = active_connections()
    active_counts = {}
    for item in active:
        active_counts[item['username']] = active_counts.get(item['username'], 0) + 1
    with connect() as con:
        rows = con.execute('SELECT id,username,enabled,note,created_at FROM vpn_users ORDER BY created_at DESC').fetchall()
    return jsonify(users=[{'id': r['id'], 'username': r['username'], 'enabled': bool(r['enabled']),
                           'note': r['note'], 'createdAt': datetime.fromtimestamp(r['created_at'], timezone.utc).isoformat(),
                           'activeConnections': active_counts.get(r['username'], 0)} for r in rows])

@APP.post('/api/users')
@require_auth
def create_user():
    data = request.get_json(silent=True) or {}
    raw_username = data.get('username', '')
    username = raw_username.strip() if isinstance(raw_username, str) else ''
    password = data.get('password') or secrets.token_urlsafe(15)
    raw_note = data.get('note', '')
    note = raw_note.strip()[:120] if isinstance(raw_note, str) else ''
    if not USER_RE.fullmatch(username):
        return jsonify(error='نام کاربری باید ۳ تا ۳۲ نویسه و شامل حروف انگلیسی، عدد، نقطه، خط تیره یا زیرخط باشد.'), 400
    if not isinstance(password, str) or not VPN_PASS_RE.fullmatch(password):
        return jsonify(error='رمز VPN باید ۱۲ تا ۱۲۸ نویسه و فقط شامل حروف انگلیسی، عدد و . _ ! @ # % + = : - باشد.'), 400
    try:
        with connect() as con:
            con.execute('INSERT INTO vpn_users(username,vpn_password,enabled,note,created_at) VALUES(?,?,1,?,?)',
                        (username, password, note, now()))
        sync_enabled_users()
    except sqlite3.IntegrityError:
        return jsonify(error='این نام کاربری قبلاً ثبت شده است.'), 409
    except Exception as error:
        with connect() as con: con.execute('DELETE FROM vpn_users WHERE username=?', (username,))
        return jsonify(error=str(error)), 500
    audit(g.admin['username'], 'user_created', username)
    return jsonify(ok=True, username=username, password=password), 201

@APP.patch('/api/users/<int:user_id>')
@require_auth
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify(error='مقدار وضعیت حساب معتبر نیست.'), 400
    with connect() as con:
        row = con.execute('SELECT username,enabled FROM vpn_users WHERE id=?', (user_id,)).fetchone()
        if not row: return jsonify(error='کاربر پیدا نشد.'), 404
        con.execute('UPDATE vpn_users SET enabled=? WHERE id=?', (int(enabled), user_id))
    try:
        sync_enabled_users()
        if not enabled: helper('revoke-user', {'username': row['username']})
    except Exception as error:
        with connect() as con: con.execute('UPDATE vpn_users SET enabled=? WHERE id=?', (row['enabled'], user_id))
        sync_enabled_users()
        return jsonify(error=str(error)), 500
    audit(g.admin['username'], 'user_enabled' if enabled else 'user_disabled', row['username'])
    return jsonify(ok=True)

@APP.post('/api/users/<int:user_id>/password')
@require_auth
def reset_vpn_password(user_id):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or secrets.token_urlsafe(15)
    if not isinstance(password, str) or not VPN_PASS_RE.fullmatch(password):
        return jsonify(error='رمز VPN باید ۱۲ تا ۱۲۸ نویسه و فقط شامل حروف انگلیسی، عدد و . _ ! @ # % + = : - باشد.'), 400
    with connect() as con:
        row = con.execute('SELECT username,vpn_password FROM vpn_users WHERE id=?', (user_id,)).fetchone()
        if not row: return jsonify(error='کاربر پیدا نشد.'), 404
        con.execute('UPDATE vpn_users SET vpn_password=? WHERE id=?', (password, user_id))
    try:
        sync_enabled_users()
        helper('revoke-user', {'username': row['username']})
    except Exception as error:
        with connect() as con: con.execute('UPDATE vpn_users SET vpn_password=? WHERE id=?', (row['vpn_password'], user_id))
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
    return jsonify(connections=active_connections())

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
