#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="${VPN_DOMAIN:-}"
EMAIL="${ACME_EMAIL:-}"
RESTORE_FILE=""
if [[ "${1:-}" == "--restore" ]]; then RESTORE_FILE="${2:-}"; [[ -n "$RESTORE_FILE" ]] || { echo 'Usage: sudo ./install.sh [--restore encrypted-backup.enc]' >&2; exit 2; }; fi
if [[ "$(id -u)" -ne 0 ]]; then echo 'Run with sudo: sudo ./install.sh' >&2; exit 1; fi
if [[ ! -f "$ROOT_DIR/server/app.py" || ! -f "$ROOT_DIR/server/privileged_helper.py" || ! -f "$ROOT_DIR/web/dist/index.html" ]]; then
  echo 'Package is incomplete. Build the React panel first (npm ci && npm run build).' >&2; exit 1
fi
if [[ ! -r /etc/os-release ]]; then echo 'Ubuntu 24.04 is required.' >&2; exit 1; fi
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || { echo 'This installer supports Ubuntu 24.04 LTS only.' >&2; exit 1; }
if [[ -e /etc/ikev2-manager || -e /etc/swanctl/swanctl.conf ]]; then
  echo 'An existing VPN or manager configuration was found. This installer is for a fresh server and will not overwrite it.' >&2; exit 1
fi
if [[ -e /etc/ocserv/ocserv.conf ]]; then
  echo 'An existing ocserv configuration was found. This installer is for a fresh server and will not replace it.' >&2; exit 1
fi
if [[ -d /etc/nginx/sites-enabled ]]; then
  for site in /etc/nginx/sites-enabled/*; do
    [[ -e "$site" || -L "$site" ]] || continue
    [[ "$(basename -- "$site")" == default ]] || { echo "Existing Nginx site found: $site. Refusing to replace web configuration." >&2; exit 1; }
  done
fi

if [[ -z "$DOMAIN" ]]; then read -r -p 'Domain for the VPN and web panel (e.g. vpn.example.com): ' DOMAIN; fi
[[ "$DOMAIN" =~ ^([A-Za-z0-9][A-Za-z0-9-]*\.)+[A-Za-z]{2,63}$ ]] || { echo 'Enter a valid fully-qualified domain name.' >&2; exit 1; }
DOMAIN="${DOMAIN,,}"
if [[ -z "$EMAIL" ]]; then read -r -p 'Email for TLS certificate expiry notices (optional): ' EMAIL; fi
if [[ -n "$EMAIL" && ! "$EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then echo 'Email address format is invalid.' >&2; exit 1; fi

if [[ -n "$RESTORE_FILE" ]]; then
  [[ -f "$RESTORE_FILE" ]] || { echo 'Backup file not found.' >&2; exit 1; }
  read -r -s -p 'Backup encryption password: ' RESTORE_PASSWORD; echo
  [[ -n "$RESTORE_PASSWORD" ]] || { echo 'Backup password cannot be empty.' >&2; exit 1; }
fi

PUBLIC4="$(python3 - <<'PY'
import urllib.request
try:
    print(urllib.request.urlopen('https://api.ipify.org', timeout=10).read(64).decode().strip())
except Exception:
    print('')
PY
)"
[[ "$PUBLIC4" =~ ^[0-9.]+$ ]] || { echo 'Could not detect the server public IPv4 address.' >&2; exit 1; }
DNS4="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)"
if [[ -z "$DNS4" ]]; then echo "DNS for $DOMAIN does not resolve yet. Create an A record to $PUBLIC4, wait for propagation, then rerun." >&2; exit 1; fi
if ! grep -Fxq "$PUBLIC4" <<<"$DNS4"; then
  echo "Notice: $DOMAIN resolves to a different address (possibly through a DNS proxy). This can work if HTTP validation reaches this server."
  read -r -p 'Continue anyway? [y/N] ' answer
  [[ "$answer" =~ ^[Yy]$ ]] || exit 1
fi

IFACE="$(ip -o -4 route show default | awk 'NR==1 {print $5}')"
[[ "$IFACE" =~ ^[A-Za-z0-9_.:-]+$ ]] || { echo 'Could not detect the public network interface.' >&2; exit 1; }
VPN4='10.77.0.0/24'
VPN6='fd77:2026:10::/64'
OCSERV4='10.99.0.0/24'
OCSERV6='fd99:2026:10::/64'
IPV6=0
if ip -6 route get 2606:4700:4700::1111 >/dev/null 2>&1 && ip -6 -o addr show dev "$IFACE" scope global | grep -qv 'fe80:'; then IPV6=1; fi

echo '[1/10] Installing system packages…'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq strongswan-swanctl charon-systemd strongswan-pki libcharon-extra-plugins libcharon-extauth-plugins \
  freeradius freeradius-utils wireguard-tools ocserv nginx certbot python3-certbot-nginx python3-flask gunicorn ufw iptables curl openssl sudo
systemctl disable --now ocserv.service 2>/dev/null || true

echo '[2/10] Preparing secure directories…'
getent group ikev2-panel >/dev/null || groupadd --system ikev2-panel
id ikev2-panel >/dev/null 2>&1 || useradd --system --gid ikev2-panel --home-dir /var/lib/ikev2-manager --shell /usr/sbin/nologin ikev2-panel
install -d -o root -g root -m 755 /opt/ikev2-manager /opt/ikev2-manager/web /opt/ikev2-manager/web/dist
install -d -o ikev2-panel -g ikev2-panel -m 700 /var/lib/ikev2-manager
install -d -o root -g ikev2-panel -m 750 /etc/ikev2-manager
install -d -o root -g root -m 755 /etc/swanctl/conf.d /etc/swanctl/private /etc/swanctl/x509 /etc/swanctl/x509ca
install -d -o root -g root -m 755 /etc/letsencrypt/renewal-hooks/deploy
install -o root -g root -m 640 "$ROOT_DIR/server/app.py" /opt/ikev2-manager/app.py
install -o root -g root -m 640 "$ROOT_DIR/server/accounting_worker.py" /opt/ikev2-manager/accounting_worker.py
install -o root -g root -m 640 "$ROOT_DIR/server/telegram_worker.py" /opt/ikev2-manager/telegram_worker.py
install -o root -g root -m 640 "$ROOT_DIR/server/ocserv_accounting.py" /opt/ikev2-manager/ocserv_accounting.py
cat > /usr/local/sbin/forge-connect-ocserv-accounting <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /opt/ikev2-manager/ocserv_accounting.py
EOF
chmod 750 /usr/local/sbin/forge-connect-ocserv-accounting
install -o root -g root -m 750 "$ROOT_DIR/server/privileged_helper.py" /usr/local/sbin/ikev2-panel-helper
cp -a "$ROOT_DIR/web/dist/." /opt/ikev2-manager/web/dist/
chmod -R a+rX /opt/ikev2-manager
printf '%s\n' "$DOMAIN" > /etc/ikev2-manager/domain
chown root:ikev2-panel /etc/ikev2-manager/domain; chmod 640 /etc/ikev2-manager/domain
printf '%s\n' "$IFACE" > /etc/ikev2-manager/interface
chown root:root /etc/ikev2-manager/interface; chmod 644 /etc/ikev2-manager/interface
printf '%s\n' "$IPV6" > /etc/ikev2-manager/ipv6-enabled
chown root:ikev2-panel /etc/ikev2-manager/ipv6-enabled; chmod 640 /etc/ikev2-manager/ipv6-enabled
openssl rand -hex 32 > /etc/ikev2-manager/session.key
chown root:ikev2-panel /etc/ikev2-manager/session.key; chmod 640 /etc/ikev2-manager/session.key

RESTORE_TMP=''
cleanup_restore() { [[ -z "$RESTORE_TMP" ]] || rm -rf -- "$RESTORE_TMP"; unset RESTORE_PASSWORD 2>/dev/null || true; }
trap cleanup_restore EXIT
if [[ -n "$RESTORE_FILE" ]]; then
  RESTORE_TMP="$(mktemp -d /tmp/ikev2-restore.XXXXXX)"; chmod 700 "$RESTORE_TMP"
  printf '%s' "$RESTORE_PASSWORD" > "$RESTORE_TMP/pass"; chmod 600 "$RESTORE_TMP/pass"
  if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in "$RESTORE_FILE" -pass "file:$RESTORE_TMP/pass" -out "$RESTORE_TMP/archive.tar.gz" 2>/dev/null; then
    echo 'Could not decrypt the backup. Check its password.' >&2; exit 1
  fi
  mkdir "$RESTORE_TMP/data"
  tar -xzf "$RESTORE_TMP/archive.tar.gz" -C "$RESTORE_TMP/data" --no-same-owner panel.sqlite3 ca-private-key.pem ca-root.pem
  if tar -tzf "$RESTORE_TMP/archive.tar.gz" | grep -Fxq 'wg-server-private.key'; then tar -xzf "$RESTORE_TMP/archive.tar.gz" -C "$RESTORE_TMP/data" --no-same-owner wg-server-private.key; fi
  [[ -f "$RESTORE_TMP/data/panel.sqlite3" && -f "$RESTORE_TMP/data/ca-private-key.pem" && -f "$RESTORE_TMP/data/ca-root.pem" ]] || { echo 'Backup is incomplete or incompatible.' >&2; exit 1; }
fi

echo '[3/10] Creating or restoring the VPN authority…'
if [[ -n "$RESTORE_FILE" ]]; then
  install -o ikev2-panel -g ikev2-panel -m 600 "$RESTORE_TMP/data/panel.sqlite3" /var/lib/ikev2-manager/panel.sqlite3
  python3 - <<'PY'
import sqlite3
con=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
con.execute('DELETE FROM sessions')
con.commit(); con.close()
PY
  install -o root -g root -m 600 "$RESTORE_TMP/data/ca-private-key.pem" /etc/swanctl/private/ikev2-ca-key.pem
  install -o root -g root -m 644 "$RESTORE_TMP/data/ca-root.pem" /etc/swanctl/x509ca/ikev2-root-ca.pem
  install -o root -g ikev2-panel -m 640 "$RESTORE_TMP/data/ca-root.pem" /var/lib/ikev2-manager/server-ca.pem
else
  pki --gen --type rsa --size 3072 --outform pem > /etc/swanctl/private/ikev2-ca-key.pem
  chmod 600 /etc/swanctl/private/ikev2-ca-key.pem
  pki --self --ca --lifetime 3650 --in /etc/swanctl/private/ikev2-ca-key.pem --dn "CN=$DOMAIN VPN Root CA" --outform pem > /etc/swanctl/x509ca/ikev2-root-ca.pem
  chmod 644 /etc/swanctl/x509ca/ikev2-root-ca.pem
  install -o root -g ikev2-panel -m 640 /etc/swanctl/x509ca/ikev2-root-ca.pem /var/lib/ikev2-manager/server-ca.pem
fi
pki --gen --type rsa --size 3072 --outform pem > /etc/swanctl/private/ikev2-server-key.pem
chmod 600 /etc/swanctl/private/ikev2-server-key.pem
pki --pub --in /etc/swanctl/private/ikev2-server-key.pem | pki --issue --cacert /etc/swanctl/x509ca/ikev2-root-ca.pem \
  --cakey /etc/swanctl/private/ikev2-ca-key.pem --dn "CN=$DOMAIN" --san "$DOMAIN" --flag serverAuth --lifetime 1825 --outform pem > /etc/swanctl/x509/ikev2-server-cert.pem
chmod 644 /etc/swanctl/x509/ikev2-server-cert.pem

echo '[4/10] Configuring IKEv2 and IP pools…'
if [[ "$IPV6" == 1 ]]; then
  TS='0.0.0.0/0,::/0'
  POOLS='vpn4,vpn6'
  POOL6="  vpn6 {\n    addrs = $VPN6\n    dns = 2606:4700:4700::1111,2606:4700:4700::1001\n  }"
else
  TS='0.0.0.0/0'
  POOLS='vpn4'
  POOL6=''
fi
cat > /etc/swanctl/swanctl.conf <<EOF
include conf.d/*.conf

connections {
  ikev2-eap {
    version = 2
    local_addrs = %any
    proposals = aes256-sha256-modp2048,aes128-sha256-modp2048
    send_cert = always
    fragmentation = yes
    pools = $POOLS
    dpd_delay = 30s
    local {
      auth = pubkey
      certs = ikev2-server-cert.pem
      id = $DOMAIN
    }
    remote {
      auth = eap-radius
      eap_id = %any
    }
    children {
      full-tunnel {
        local_ts = $TS
        esp_proposals = aes256-sha256-modp2048,aes128-sha256-modp2048
      }
    }
  }
}
pools {
  vpn4 {
    addrs = $VPN4
    dns = 1.1.1.1,1.0.0.1
  }
$(printf '%b' "$POOL6")
}
EOF
chmod 600 /etc/swanctl/swanctl.conf
printf 'secrets {\n}\n' > /etc/swanctl/conf.d/ikev2-manager-users.conf
chmod 600 /etc/swanctl/conf.d/ikev2-manager-users.conf

echo '[5/11] Configuring local RADIUS accounting and device limits…'
RADIUS_SECRET="$(openssl rand -hex 32)"
cat > /etc/strongswan.d/charon/eap-radius.conf <<EOF
eap-radius {
  load = yes
  accounting = yes
  accounting_interval = 10
  servers {
    localhost {
      address = 127.0.0.1
      secret = $RADIUS_SECRET
      nas_identifier = forge-ikev2
      auth_port = 1812
      acct_port = 1813
    }
  }
}
EOF
chmod 600 /etc/strongswan.d/charon/eap-radius.conf
python3 - "$RADIUS_SECRET" <<'PY'
import pathlib,re,sys
p=pathlib.Path('/etc/freeradius/3.0/clients.conf')
s=p.read_text()
block='client localhost {\n\tipaddr = 127.0.0.1\n\tsecret = '+sys.argv[1]+'\n\t proto = *\n}\n'
if re.search(r'(?ms)^client localhost\s*\{.*?^\}',s): s=re.sub(r'(?ms)^client localhost\s*\{.*?^\}',block.rstrip(),s,count=1)
else: s += '\n'+block
p.write_text(s)
site=pathlib.Path('/etc/freeradius/3.0/sites-enabled/default')
if site.exists():
    s=site.read_text()
    # radutmp records authenticated sessions for Simultaneous-Use checks.
    if re.search(r'(?m)^session\s*\{',s) and not re.search(r'(?ms)^session\s*\{[^}]*\bradutmp\b',s):
        s=re.sub(r'(?m)^session\s*\{', 'session {\n\tradutmp',s,count=1)
    if re.search(r'(?m)^accounting\s*\{',s) and not re.search(r'(?ms)^accounting\s*\{[^}]*\bradutmp\b',s):
        s=re.sub(r'(?m)^accounting\s*\{', 'accounting {\n\tradutmp',s,count=1)
    site.write_text(s)
unique=pathlib.Path('/etc/freeradius/3.0/mods-available/acct_unique')
if unique.exists():
    s=unique.read_text()
    if re.search(r'(?m)^\s*key\s*=',s):
        s=re.sub(r'(?m)^\s*key\s*=.*$', 'key = "%{tolower:%{User-Name}}:%{Acct-Session-Id}:%{NAS-IP-Address}"', s, count=1)
        unique.write_text(s)
PY
freeradius -XC >/dev/null
systemctl enable --now freeradius.service
install -d -o root -g root -m 750 /etc/radcli
cat > /etc/radcli/radiusclient.conf <<'EOF'
authserver 127.0.0.1:1812
acctserver 127.0.0.1:1813
servers /etc/radcli/servers
dictionary /usr/share/freeradius/dictionary
radius_timeout 5
radius_retries 2
bindaddr 127.0.0.1
EOF
printf '127.0.0.1 %s\n' "$RADIUS_SECRET" > /etc/radcli/servers
chmod 600 /etc/radcli/servers

echo '[6/11] Preparing WireGuard…'
install -d -o root -g root -m 700 /etc/wireguard
if [[ -n "$RESTORE_FILE" && -f "$RESTORE_TMP/data/wg-server-private.key" ]]; then
  install -o root -g root -m 600 "$RESTORE_TMP/data/wg-server-private.key" /etc/wireguard/server_private
else
  umask 077; wg genkey > /etc/wireguard/server_private
fi
wg pubkey < /etc/wireguard/server_private > /etc/wireguard/server_public
chmod 600 /etc/wireguard/server_private /etc/wireguard/server_public
WG_PRIVATE="$(cat /etc/wireguard/server_private)"
WG6_ADDRESS=''
WG6_UP=''
WG6_DOWN=''
if [[ "$IPV6" == 1 ]]; then
  WG6_ADDRESS=', fd88:2026:10::1/64'
  WG6_UP='; ip6tables -t nat -A POSTROUTING -s fd88:2026:10::/64 -o '$IFACE' -j MASQUERADE; ip6tables -A FORWARD -i wg0 -o '$IFACE' -j ACCEPT; ip6tables -A FORWARD -i '$IFACE' -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT'
  WG6_DOWN='; ip6tables -t nat -D POSTROUTING -s fd88:2026:10::/64 -o '$IFACE' -j MASQUERADE; ip6tables -D FORWARD -i wg0 -o '$IFACE' -j ACCEPT; ip6tables -D FORWARD -i '$IFACE' -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT'
fi
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.88.0.1/24$WG6_ADDRESS
ListenPort = 51820
PrivateKey = $WG_PRIVATE
PostUp = iptables -t nat -A POSTROUTING -s 10.88.0.0/24 -o $IFACE -j MASQUERADE; iptables -A FORWARD -i wg0 -o $IFACE -j ACCEPT; iptables -A FORWARD -i $IFACE -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT$WG6_UP
PostDown = iptables -t nat -D POSTROUTING -s 10.88.0.0/24 -o $IFACE -j MASQUERADE; iptables -D FORWARD -i wg0 -o $IFACE -j ACCEPT; iptables -D FORWARD -i $IFACE -o wg0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT$WG6_DOWN
EOF
chmod 600 /etc/wireguard/wg0.conf

echo '[7/11] Enabling routing and firewall rules…'
cat > /etc/sysctl.d/99-ikev2-manager.conf <<EOF
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=$IPV6
net.ipv6.conf.$IFACE.accept_ra=2
EOF
sysctl --system >/dev/null
cat > /usr/local/sbin/ikev2-manager-firewall <<EOF
#!/bin/sh
set -eu
IFACE='$IFACE'
VPN4='$VPN4'
iptables -t nat -C POSTROUTING -s "\$VPN4" -o "\$IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s "\$VPN4" -o "\$IFACE" -j MASQUERADE
iptables -C FORWARD -s "\$VPN4" -o "\$IFACE" -j ACCEPT 2>/dev/null || iptables -A FORWARD -s "\$VPN4" -o "\$IFACE" -j ACCEPT
iptables -C FORWARD -d "\$VPN4" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -A FORWARD -d "\$VPN4" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
OCSERV4='$OCSERV4'
iptables -t nat -C POSTROUTING -s "\$OCSERV4" -o "\$IFACE" -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s "\$OCSERV4" -o "\$IFACE" -j MASQUERADE
iptables -C FORWARD -s "\$OCSERV4" -o "\$IFACE" -j ACCEPT 2>/dev/null || iptables -A FORWARD -s "\$OCSERV4" -o "\$IFACE" -j ACCEPT
iptables -C FORWARD -d "\$OCSERV4" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || iptables -A FORWARD -d "\$OCSERV4" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
EOF
if [[ "$IPV6" == 1 ]]; then cat >> /usr/local/sbin/ikev2-manager-firewall <<EOF
VPN6='$VPN6'
ip6tables -t nat -C POSTROUTING -s "\$VPN6" -o "\$IFACE" -j MASQUERADE 2>/dev/null || ip6tables -t nat -A POSTROUTING -s "\$VPN6" -o "\$IFACE" -j MASQUERADE
ip6tables -C FORWARD -s "\$VPN6" -o "\$IFACE" -j ACCEPT 2>/dev/null || ip6tables -A FORWARD -s "\$VPN6" -o "\$IFACE" -j ACCEPT
ip6tables -C FORWARD -d "\$VPN6" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || ip6tables -A FORWARD -d "\$VPN6" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
OCSERV6='$OCSERV6'
ip6tables -t nat -C POSTROUTING -s "\$OCSERV6" -o "\$IFACE" -j MASQUERADE 2>/dev/null || ip6tables -t nat -A POSTROUTING -s "\$OCSERV6" -o "\$IFACE" -j MASQUERADE
ip6tables -C FORWARD -s "\$OCSERV6" -o "\$IFACE" -j ACCEPT 2>/dev/null || ip6tables -A FORWARD -s "\$OCSERV6" -o "\$IFACE" -j ACCEPT
ip6tables -C FORWARD -d "\$OCSERV6" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || ip6tables -A FORWARD -d "\$OCSERV6" -i "\$IFACE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
EOF
fi
chmod 750 /usr/local/sbin/ikev2-manager-firewall
cat > /etc/systemd/system/ikev2-manager-firewall.service <<'EOF'
[Unit]
Description=Persistent routing rules for the IKEv2 VPN
After=ufw.service network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ikev2-manager-firewall
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/forge-connect-accounting.service <<'EOF'
[Unit]
Description=Forge Connect VPN quota and accounting collector
After=strongswan.service freeradius.service wg-quick@wg0.service
Wants=strongswan.service freeradius.service wg-quick@wg0.service
[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/ikev2-manager/accounting_worker.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
PrivateTmp=true
ReadWritePaths=/var/lib/ikev2-manager /etc/swanctl/conf.d /etc/freeradius/3.0/mods-config/files /etc/wireguard
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/forge-connect-telegram.service <<'EOF'
[Unit]
Description=Forge Connect Telegram sales bot
After=network-online.target ikev2-manager.service
Wants=network-online.target
[Service]
Type=simple
User=ikev2-panel
Group=ikev2-panel
WorkingDirectory=/opt/ikev2-manager
ExecStart=/usr/bin/python3 /opt/ikev2-manager/telegram_worker.py
Restart=always
RestartSec=5
UMask=0077
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/ikev2-manager
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
EOF
SSH_PORTS="$(sshd -T 2>/dev/null | awk '$1=="port" {print $2}' | sort -u || true)"
[[ -n "$SSH_PORTS" ]] || SSH_PORTS='22'
for port in $SSH_PORTS; do ufw allow "$port/tcp" >/dev/null; done
ufw allow 500,4500/udp >/dev/null
ufw allow 51820/udp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 8443/tcp >/dev/null
ufw allow 8443/udp >/dev/null
ufw route allow in on "$IFACE" out on "$IFACE" from "$VPN4" >/dev/null
ufw route allow from "$OCSERV4" to any >/dev/null
if [[ "$IPV6" == 1 ]]; then ufw route allow from "$OCSERV6" to any >/dev/null; fi
ufw route allow in on wg0 out on "$IFACE" from 10.88.0.0/24 >/dev/null
if [[ "$IPV6" == 1 ]]; then ufw route allow in on wg0 out on "$IFACE" from fd88:2026:10::/64 >/dev/null; fi
if [[ "$IPV6" == 1 ]]; then ufw route allow in on "$IFACE" out on "$IFACE" from "$VPN6" >/dev/null; fi
if ! ufw status | grep -q '^Status: active'; then ufw --force enable >/dev/null; fi
systemctl daemon-reload
systemctl enable --now ufw.service ikev2-manager-firewall.service wg-quick@wg0.service

echo '[8/11] Starting strongSwan…'
systemctl enable --now strongswan.service
swanctl --load-all >/dev/null

echo '[9/11] Configuring HTTPS and the web front end…'
cat > /etc/nginx/conf.d/ikev2-manager-rate.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=ikev2_login:10m rate=6r/m;
EOF
cat > /etc/nginx/sites-available/ikev2-manager <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/www/html; default_type text/plain; try_files \$uri =404; }
    location / { return 404; }
}
EOF
ln -s /etc/nginx/sites-available/ikev2-manager /etc/nginx/sites-enabled/ikev2-manager
if [[ -L /etc/nginx/sites-enabled/default ]]; then rm -f /etc/nginx/sites-enabled/default; fi
nginx -t
systemctl enable --now nginx
if [[ -n "$EMAIL" ]]; then
  certbot certonly --webroot --webroot-path /var/www/html -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive
else
  certbot certonly --webroot --webroot-path /var/www/html -d "$DOMAIN" --agree-tos --non-interactive --register-unsafely-without-email
fi

cat > /etc/nginx/sites-available/ikev2-manager <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location ^~ /.well-known/acme-challenge/ { root /var/www/html; default_type text/plain; try_files \$uri =404; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:ikev2tls:10m;
    ssl_session_timeout 10m;
    server_tokens off;
    add_header Strict-Transport-Security "max-age=15552000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'" always;
    root /opt/ikev2-manager/web/dist;
    index index.html;
    client_max_body_size 64k;
    location = /api/login {
        limit_req zone=ikev2_login burst=5 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:15151;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:15151;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
    location / { try_files \$uri \$uri/ /index.html; }
    location ~ /\. { deny all; }
}
EOF
cat >> /etc/nginx/sites-available/ikev2-manager <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    return 444;
}
EOF
echo '[10/12] Configuring OpenConnect (ocserv)…'
OCSERV_V6=''
if [[ "$IPV6" == 1 ]]; then OCSERV_V6="ipv6-network = $OCSERV6"; fi
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
ipv4-network = $OCSERV4
$OCSERV_V6
route = default
dns = 1.1.1.1
dns = 1.0.0.1
disconnect-script = /usr/local/sbin/forge-connect-ocserv-accounting
EOF
chmod 640 /etc/ocserv/ocserv.conf
ocserv -t -c /etc/ocserv/ocserv.conf
systemctl enable --now ocserv.service

cat > /etc/letsencrypt/renewal-hooks/deploy/ikev2-manager-reload-nginx <<'EOF'
#!/bin/sh
systemctl reload nginx
systemctl reload-or-restart ocserv
EOF
chmod 750 /etc/letsencrypt/renewal-hooks/deploy/ikev2-manager-reload-nginx

echo '[10/11] Installing the least-privilege management service…'
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

if [[ -n "$RESTORE_FILE" ]]; then
  install -o ikev2-panel -g ikev2-panel -m 600 "$RESTORE_TMP/data/panel.sqlite3" /var/lib/ikev2-manager/panel.sqlite3
  install -o root -g root -m 600 "$RESTORE_TMP/data/ca-private-key.pem" /etc/swanctl/private/ikev2-ca-key.pem
  install -o root -g root -m 644 "$RESTORE_TMP/data/ca-root.pem" /etc/swanctl/x509ca/ikev2-root-ca.pem
  install -o root -g ikev2-panel -m 640 "$RESTORE_TMP/data/ca-root.pem" /var/lib/ikev2-manager/server-ca.pem
  chown ikev2-panel:ikev2-panel /var/lib/ikev2-manager/panel.sqlite3; chmod 600 /var/lib/ikev2-manager/panel.sqlite3
else
  SETUP_TOKEN="$(openssl rand -hex 24)"
  printf '%s\n' "$SETUP_TOKEN" > /etc/ikev2-manager/setup-token
  chown root:ikev2-panel /etc/ikev2-manager/setup-token; chmod 440 /etc/ikev2-manager/setup-token
fi

systemctl daemon-reload
systemctl enable --now ikev2-manager.service
nginx -t
systemctl reload nginx
sleep 1
if [[ "$(systemctl is-active ikev2-manager.service)" != active || "$(systemctl is-active strongswan.service)" != active || "$(systemctl is-active ocserv.service)" != active ]]; then
  echo 'One or more services did not start. Inspect: journalctl -u ikev2-manager -u strongswan -u ocserv -n 100' >&2; exit 1
fi

echo '[11/11] Synchronizing VPN users…'
if [[ -n "$RESTORE_FILE" ]]; then
  python3 - <<'PY' | /usr/local/sbin/ikev2-panel-helper sync-users >/dev/null
import json, sqlite3
db=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
print(json.dumps([{'username':u,'password':p,'maxConnections':m,'protocols':[x for x in protocols.split(',') if x in ('ikev2','ocserv')]} for u,p,m,protocols in db.execute("SELECT username,vpn_password,max_connections,protocols FROM vpn_users WHERE enabled=1 AND (instr(','||protocols||',',',ikev2,')>0 OR instr(','||protocols||',',',ocserv,')>0) ")]))
PY
else
  printf '[]' | /usr/local/sbin/ikev2-panel-helper sync-users >/dev/null
fi
python3 - <<'PY' | /usr/local/sbin/ikev2-panel-helper sync-wireguard >/dev/null
import json,sqlite3
c=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
print(json.dumps([{'publicKey':k,'address':a} for k,a in c.execute('SELECT public_key,assigned_ip FROM wireguard_peers WHERE revoked=0')]))
PY
swanctl --load-conns >/dev/null
systemctl enable --now forge-connect-accounting.service
systemctl enable --now forge-connect-telegram.service
nginx -t >/dev/null

echo '[10/10] Finished.'
echo
echo "Panel: https://$DOMAIN"
echo "VPN server: $DOMAIN"
if [[ "$IPV6" == 1 ]]; then echo 'IPv6: enabled'; else echo 'IPv6: skipped (no working public IPv6 route detected)'; fi
echo 'Protocols: IKEv2, WireGuard (UDP 51820) and OpenConnect (TCP/UDP 8443).'
if [[ -n "$RESTORE_FILE" ]]; then
  echo 'Existing admin account, VPN users, audit history and CA identity were restored.'
else
  echo 'One-time setup code (enter it on the first page to create the admin account):'
  echo "$SETUP_TOKEN"
fi
echo 'Save the setup code / backup password securely. The web process is limited to localhost behind HTTPS Nginx.'
