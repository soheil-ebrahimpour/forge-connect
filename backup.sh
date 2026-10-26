#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$(id -u)" -ne 0 ]]; then echo 'Run with sudo: sudo ./backup.sh [output.enc]' >&2; exit 1; fi
OUT="${1:-$PWD/ikev2-backup-$(date -u +%Y%m%d-%H%M%S).enc}"
TMP="$(mktemp -d /tmp/ikev2-backup.XXXXXX)"
trap 'rm -rf -- "$TMP"; unset PASSWORD CONFIRM 2>/dev/null || true' EXIT
[[ -f /var/lib/ikev2-manager/panel.sqlite3 ]] || { echo 'VPN Manager database was not found.' >&2; exit 1; }
[[ -f /etc/swanctl/private/ikev2-ca-key.pem && -f /etc/swanctl/x509ca/ikev2-root-ca.pem ]] || { echo 'VPN CA files were not found.' >&2; exit 1; }
read -r -s -p 'Set an encryption password (at least 14 characters): ' PASSWORD; echo
read -r -s -p 'Confirm password: ' CONFIRM; echo
[[ ${#PASSWORD} -ge 14 && "$PASSWORD" == "$CONFIRM" ]] || { echo 'Password is too short or the entries do not match.' >&2; exit 1; }
mkdir "$TMP/data"; chmod 700 "$TMP/data"
python3 - "$TMP/data/panel.sqlite3" <<'PY'
import sqlite3,sys
source=sqlite3.connect('/var/lib/ikev2-manager/panel.sqlite3')
target=sqlite3.connect(sys.argv[1])
source.backup(target)
target.close(); source.close()
PY
install -m 600 /etc/swanctl/private/ikev2-ca-key.pem "$TMP/data/ca-private-key.pem"
install -m 600 /etc/swanctl/x509ca/ikev2-root-ca.pem "$TMP/data/ca-root.pem"
install -m 644 /etc/ikev2-manager/domain "$TMP/data/domain.txt"
tar -czf "$TMP/data.tar.gz" -C "$TMP/data" panel.sqlite3 ca-private-key.pem ca-root.pem domain.txt
printf '%s' "$PASSWORD" > "$TMP/pass"; chmod 600 "$TMP/pass"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 -in "$TMP/data.tar.gz" -out "$OUT" -pass "file:$TMP/pass"
chmod 600 "$OUT"
echo "Encrypted backup created: $OUT"
echo 'It contains the VPN account database and CA private key. Store it securely off-server.'
