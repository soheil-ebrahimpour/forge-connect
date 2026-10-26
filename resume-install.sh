#!/usr/bin/env bash
# Finish Forge Connect after install.sh stopped while validating ocserv.conf.
set -Eeuo pipefail
if [[ "$(id -u)" -ne 0 ]]; then echo 'Run with sudo: sudo bash ./resume-install.sh' >&2; exit 1; fi
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN_FILE=/etc/ikev2-manager/domain
IFACE_FILE=/etc/ikev2-manager/interface
IPV6_FILE=/etc/ikev2-manager/ipv6-enabled
for f in "$DOMAIN_FILE" "$IFACE_FILE" "$IPV6_FILE" /etc/swanctl/swanctl.conf /etc/radcli/radiusclient.conf /etc/letsencrypt/renewal-hooks/deploy; do
  [[ -e "$f" ]] || { echo "This does not look like the partial Forge Connect installation: missing $f" >&2; exit 1; }
done
DOMAIN="$(cat "$DOMAIN_FILE")"
IFACE="$(cat "$IFACE_FILE")"
IPV6="$(cat "$IPV6_FILE")"
[[ "$DOMAIN" =~ ^([A-Za-z0-9][A-Za-z0-9-]*\.)+[A-Za-z]{2,63}$ && "$IFACE" =~ ^[A-Za-z0-9_.:-]+$ && "$IPV6" =~ ^[01]$ ]] || { echo 'Invalid saved install settings.' >&2; exit 1; }
[[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" && -f "/etc/letsencrypt/live/$DOMAIN/privkey.pem" ]] || { echo 'The HTTPS certificate is missing; resume cannot continue.' >&2; exit 1; }
[[ -x /usr/local/sbin/ikev2-panel-helper && -f /opt/ikev2-manager/app.py && -f /opt/ikev2-manager/accounting_worker.py && -f /opt/ikev2-manager/telegram_worker.py ]] || { echo 'The panel files are missing; resume cannot continue.' >&2; exit 1; }
if [[ ! -s /etc/radcli/dictionary ]]; then
  apt-get -o Dpkg::Options::=--force-confmiss install --reinstall -y -qq libradcli4
fi
[[ -s /etc/radcli/dictionary ]] || { echo 'radcli dictionary is missing.' >&2; exit 1; }
sed -i 's#^dictionary .*#dictionary /etc/radcli/dictionary#' /etc/radcli/radiusclient.conf
OCSERV_V6=''
if [[ "$IPV6" == 1 ]]; then OCSERV_V6='ipv6-network = fd99:2026:10::/64'; fi
cat > /etc/ocserv/ocserv.conf <<EOF
auth = "radius[config=/etc/radcli/radiusclient.conf,nas-identifier=forge-ocserv]"
acct = "radius[config=/etc/radcli/radiusclient.conf]"
tcp-port = 8443
udp-port = 8443
server-cert = /etc/letsencrypt/live/$DOMAIN/fullchain.pem
server-key = /etc/letsencrypt/live/$DOMAIN/privkey.pem
run-as-user = nobody
run-as-group = nogroup
use-occtl = true
socket-file = /run/ocserv-socket
device = vpns
max-clients = 512
max-same-clients = 50
stats-report-time = 5
server-stats-reset-time = 604800
ipv4-network = 10.99.0.0/24
$OCSERV_V6
route = default
dns = 1.1.1.1
dns = 1.0.0.1
disconnect-script = /usr/local/sbin/forge-connect-ocserv-accounting
EOF
chmod 640 /etc/ocserv/ocserv.conf
ocserv -t -c /etc/ocserv/ocserv.conf
cat > /etc/letsencrypt/renewal-hooks/deploy/ikev2-manager-reload-nginx <<'EOF'
#!/bin/sh
systemctl reload nginx
systemctl reload-or-restart ocserv
EOF
chmod 750 /etc/letsencrypt/renewal-hooks/deploy/ikev2-manager-reload-nginx
cat > /etc/sudoers.d/ikev2-panel <<'EOF'
ikev2-panel ALL=(root) NOPASSWD: /usr/local/sbin/ikev2-panel-helper
EOF
chmod 440 /etc/sudoers.d/ikev2-panel
visudo -cf /etc/sudoers.d/ikev2-panel >/dev/null
cat > /etc/systemd/system/ikev2-manager.service <<'EOF'
[Unit]
Description=IKEv2 VPN management panel API
After=network.target strongswan.service
Wants=strongswan.service
[Service]
Type=simple
User=ikev2-panel
Group=ikev2-panel
WorkingDirectory=/opt/ikev2-manager
ExecStart=/usr/bin/gunicorn --workers 2 --bind 127.0.0.1:15151 --access-logfile - --error-logfile - app:APP
Restart=on-failure
RestartSec=3
UMask=0077
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/ikev2-manager /etc/swanctl/conf.d /etc/ikev2-manager /etc/freeradius/3.0/mods-config/files /etc/wireguard
ReadOnlyPaths=/etc/swanctl/x509ca
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
EOF
if [[ ! -e /etc/ikev2-manager/setup-token ]]; then
  TOKEN="$(openssl rand -hex 24)"
  printf '%s\n' "$TOKEN" > /etc/ikev2-manager/setup-token
  chown root:ikev2-panel /etc/ikev2-manager/setup-token
  chmod 440 /etc/ikev2-manager/setup-token
else
  TOKEN="$(cat /etc/ikev2-manager/setup-token)"
fi
systemctl daemon-reload
systemctl enable --now ocserv.service ikev2-manager.service
nginx -t
systemctl reload nginx
[[ -f /var/lib/ikev2-manager/panel.sqlite3 ]] || { echo 'Panel database was not created.' >&2; exit 1; }
python3 - <<'PY' | /usr/local/sbin/ikev2-panel-helper sync-users >/dev/null
import json,sqlite3,time
c=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
rows=c.execute('''SELECT username,vpn_password,max_connections,protocols FROM vpn_users
 WHERE enabled=1 AND (expires_at IS NULL OR expires_at>?)
 AND (quota_bytes=0 OR used_up_bytes+used_down_bytes<quota_bytes)
 AND (instr(','||protocols||',',',ikev2,')>0 OR instr(','||protocols||',',',ocserv,')>0)''',(int(time.time()),))
print(json.dumps([{'username':u,'password':p,'maxConnections':m,
 'protocols':[x for x in ps.split(',') if x in ('ikev2','ocserv')]} for u,p,m,ps in rows]))
PY
python3 - <<'PY' | /usr/local/sbin/ikev2-panel-helper sync-wireguard >/dev/null
import json,sqlite3
c=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
print(json.dumps([{'publicKey':k,'address':a} for k,a in c.execute('SELECT public_key,assigned_ip FROM wireguard_peers WHERE revoked=0')]))
PY
swanctl --load-conns >/dev/null
systemctl enable --now forge-connect-accounting.service forge-connect-telegram.service
for svc in ikev2-manager strongswan ocserv freeradius nginx; do
  [[ "$(systemctl is-active "$svc")" == active ]] || { echo "Service failed: $svc; check journalctl -u $svc -n 80" >&2; exit 1; }
done
echo "Panel: https://$DOMAIN"
echo "Protocols: IKEv2, WireGuard (UDP 51820), OpenConnect (TCP/UDP 8443)."
echo 'One-time setup code:'
echo "$TOKEN"
