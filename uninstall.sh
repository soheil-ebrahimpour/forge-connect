#!/usr/bin/env bash
# Remove a Forge Connect / ikev2-manager install so install.sh can run on a clean host.
set -Eeuo pipefail
IFS=$'\n\t'

if [[ "$(id -u)" -ne 0 ]]; then echo 'Run with sudo: sudo ./uninstall.sh' >&2; exit 1; fi

CONFIRM="${1:-}"
if [[ "$CONFIRM" != "--yes" ]]; then
  echo 'This permanently removes Forge Connect VPN services, panel data, certificates used by the panel, and related configs.'
  echo 'Lets Encrypt certificates for the VPN domain are also removed when present.'
  read -r -p 'Type YES to continue: ' answer
  [[ "$answer" == YES ]] || { echo 'Aborted.'; exit 1; }
fi

DOMAIN=""
[[ -f /etc/ikev2-manager/domain ]] && DOMAIN="$(tr -d '[:space:]' </etc/ikev2-manager/domain)"

echo '[1/6] Stopping services…'
systemctl disable --now ikev2-manager.service forge-connect-accounting.service forge-connect-telegram.service \
  ikev2-manager-firewall.service ocserv.service wg-quick@wg0.service strongswan.service freeradius.service 2>/dev/null || true
systemctl stop nginx.service 2>/dev/null || true

echo '[2/6] Removing systemd units and helpers…'
rm -f /etc/systemd/system/ikev2-manager.service \
  /etc/systemd/system/forge-connect-accounting.service \
  /etc/systemd/system/forge-connect-telegram.service \
  /etc/systemd/system/ikev2-manager-firewall.service \
  /etc/sudoers.d/ikev2-panel \
  /usr/local/sbin/ikev2-panel-helper \
  /usr/local/sbin/forge-connect-ocserv-accounting \
  /etc/letsencrypt/renewal-hooks/deploy/ikev2-manager-reload-nginx
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

echo '[3/6] Removing Nginx site and app files…'
rm -f /etc/nginx/sites-enabled/ikev2-manager /etc/nginx/sites-available/ikev2-manager
rm -rf /opt/ikev2-manager /var/lib/ikev2-manager /etc/ikev2-manager
if id ikev2-panel >/dev/null 2>&1; then userdel ikev2-panel 2>/dev/null || true; fi
groupdel ikev2-panel 2>/dev/null || true

echo '[4/6] Removing VPN / RADIUS / WireGuard / ocserv configs…'
rm -rf /etc/swanctl /etc/strongswan.d/charon/eap-radius.conf
rm -f /etc/ocserv/ocserv.conf
rm -rf /etc/wireguard
# Restore FreeRADIUS users file to a harmless empty state and drop our localhost client override if present.
if [[ -d /etc/freeradius/3.0 ]]; then
  printf '# cleared by forge-connect uninstall\n' > /etc/freeradius/3.0/mods-config/files/authorize
  chown root:freerad /etc/freeradius/3.0/mods-config/files/authorize 2>/dev/null || true
  chmod 640 /etc/freeradius/3.0/mods-config/files/authorize 2>/dev/null || true
fi
rm -f /etc/radcli/radiusclient.conf /etc/radcli/servers

echo '[5/6] Removing TLS certificates issued for the panel domain…'
if [[ -n "$DOMAIN" ]]; then
  certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
  rm -rf "/etc/letsencrypt/live/$DOMAIN" "/etc/letsencrypt/archive/$DOMAIN" "/etc/letsencrypt/renewal/$DOMAIN.conf"
fi

echo '[6/6] Purging packages installed for Forge Connect…'
export DEBIAN_FRONTEND=noninteractive
apt-get purge -y -qq strongswan-swanctl charon-systemd strongswan-pki libcharon-extra-plugins \
  libcharon-extauth-plugins freeradius freeradius-utils wireguard-tools ocserv libradcli4 \
  python3-flask gunicorn 2>/dev/null || true
apt-get autoremove -y -qq 2>/dev/null || true

# Leave nginx/certbot/ufw installed; only drop our site. Re-enable default site if nothing else remains.
if [[ -d /etc/nginx/sites-enabled ]] && [[ -z "$(find /etc/nginx/sites-enabled -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  [[ -f /etc/nginx/sites-available/default && ! -e /etc/nginx/sites-enabled/default ]] && \
    ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default || true
fi
systemctl restart nginx.service 2>/dev/null || true

# Clear UFW rules that mention our VPN interfaces/ports when ufw is active — keep SSH.
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q 'Status: active'; then
  ufw --force delete allow 500/udp 2>/dev/null || true
  ufw --force delete allow 4500/udp 2>/dev/null || true
  ufw --force delete allow 51820/udp 2>/dev/null || true
  ufw --force delete allow 8443/tcp 2>/dev/null || true
  ufw --force delete allow 8443/udp 2>/dev/null || true
fi

echo
echo 'Forge Connect has been removed.'
echo 'The host should now pass install.sh fresh-server checks.'
echo 'Next: copy the release onto the server and run: sudo bash ./install.sh'
