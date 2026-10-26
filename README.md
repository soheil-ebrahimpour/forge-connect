# Forge Connect

A self-hosted IKEv2 VPN and private web control panel for Ubuntu 24.04 LTS. The web interface is built with React/Vite, ships its fonts locally, and supports Persian (RTL) and English. The server API uses Python/Flask and SQLite from Python's standard library; no separate database server or Node runtime is installed on the VPS.

## What it installs

- strongSwan IKEv2 with EAP-MSCHAPv2 username/password authentication
- RSA server certificate and a client CA certificate
- IPv4 NAT and optional IPv6 NAT when the VPS has a working public IPv6 route
- UFW rules that preserve the configured SSH port and allow IKEv2 plus web traffic
- Nginx reverse proxy, HTTPS certificate, renewal timer, and certificate reload hook
- A private React control panel served at the domain over HTTPS
- SQLite-backed VPN accounts, one-time first-admin setup, administrator credential changes, audit history, and active-session revocation
- Encrypted full-state backup and restore to move users and the CA identity to another VPS

The panel binds only to `127.0.0.1:15151`; Nginx is the only public web entry point. Login requests are rate-limited at Nginx. The app runs as a restricted `ikev2-panel` system user. A small root-owned helper accepts only account synchronization, session listing/revocation, and service status operations.

## Requirements

- A fresh Ubuntu Server 24.04 LTS VPS with root access and a public IPv4 address
- A domain A record resolving to the VPS public IPv4 address
- Inbound TCP 80 and 443 reachable for HTTPS and ACME validation
- Inbound UDP 500 and 4500 reachable for IKEv2
- Enough memory and disk for strongSwan, Nginx, Python, and Certbot

If the domain is behind a DNS proxy, HTTP validation must still reach this server. If the VPS provider has a separate firewall/security-group page, allow the same ports there. The installer does not change provider-side firewall rules.

## Install on a new VPS

Copy the release archive to the server, unpack it, then run:

```bash
sudo bash ./install.sh
```

The installer asks for the domain and optional certificate email. It checks DNS, installs the operating system packages, configures strongSwan/NAT/UFW/Nginx/HTTPS, and starts the panel. At the end it prints a one-time setup code. Open the shown HTTPS address, enter that code, and choose the administrator username and password. The code is consumed after the first successful setup.

You can also provide the domain/email using environment variables:

```bash
sudo VPN_DOMAIN=vpn.example.com ACME_EMAIL=admin@example.com bash ./install.sh
```

The first-run setup code is shown in the terminal; keep it private until you create the administrator account.

## Panel features

- Persian and English interface with RTL/LTR layout and locally bundled Vazirmatn/Inter fonts
- Overview cards for VPN health, users, and active connections
- Create, disable, re-enable, reset-password, and delete VPN users
- Disconnect active sessions after disabling, deleting, or resetting a user's password
- Reveal a new/generated VPN password only once after create/reset
- Download the CA certificate needed by client devices
- Change the panel administrator username and password; changing credentials invalidates previous sessions
- View recent management actions

New VPN passwords must be at least 12 characters. Administrator passwords must be at least 14 characters. Credentials are not returned by the users-list API.

## Client setup

Share the domain, VPN username, and password with each user. A client must trust the downloaded `ikev2-root-ca.pem` certificate before connecting. The service uses IKEv2/IPsec with EAP-MSCHAPv2. Windows, Android strongSwan VPN Client, iOS, and macOS native clients can use this authentication mode.

## Back up and migrate to another VPS

Create an encrypted backup on the current VPS:

```bash
sudo bash ./backup.sh /root/nova-vpn-backup.enc
```

Choose a strong backup password and copy the encrypted file off the server. It contains the SQLite account database (including VPN secrets) and the CA private key, so protect both the file and password.

On a fresh Ubuntu 24.04 VPS:

1. Point the domain's A record to the new VPS and wait for DNS propagation.
2. Copy this release archive and the encrypted backup to the new VPS.
3. Run `sudo ./install.sh --restore /path/to/nova-vpn-backup.enc` and enter the backup password.

Restore keeps the panel administrator, VPN user accounts, audit log, and CA identity. It issues a new server certificate for the domain. Users can keep trusting the same CA certificate; the domain must resolve to the new VPS, and client profiles should use that domain.

## Useful operations

```bash
sudo systemctl status ikev2-manager strongswan nginx
sudo journalctl -u ikev2-manager -u strongswan -u nginx -n 100 --no-pager
sudo swanctl --list-sas
sudo ufw status verbose
```

The panel's SQLite database is `/var/lib/ikev2-manager/panel.sqlite3`. It is protected with mode `0600`. EAP-MSCHAPv2 requires the server to recover the user's password for strongSwan, so VPN passwords are stored in the restricted database and generated strongSwan credentials file. Admin passwords are stored as salted scrypt hashes.

## Build the React bundle (development only)

Node is needed only to build the bundled React application, not on the target VPS:

```bash
npm ci
npm run build
```

The build output is written to `web/dist/` and included in the release archive.
