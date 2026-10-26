# Forge Connect

پنل وب دوزبانه برای راه‌اندازی و مدیریت یک سرویس شخصی IKEv2 VPN مبتنی بر strongSwan. رابط کاربری با React/Vite ساخته شده و فونت‌های فارسی و انگلیسی را همراه خود دارد. API با Python/Flask و SQLite استاندارد پایتون اجرا می‌شود؛ روی سرور نیازی به نصب Node.js یا سرویس جداگانهٔ پایگاه داده نیست.

**Languages / زبان‌ها:** [فارسی](#فارسی) · [English](#english)

## فارسی

### امکانات

- نصب strongSwan و VPN مبتنی بر IKEv2 با ورود EAP-MSCHAPv2
- ساخت گواهی سرور و CA ریشه برای اعتماد دستگاه‌های کاربران
- NAT برای IPv4 و فعال‌سازی IPv6 در صورت وجود مسیر عمومی IPv6 روی VPS
- تنظیم UFW با حفظ پورت SSH و باز کردن پورت‌های VPN و وب
- راه‌اندازی Nginx، گواهی HTTPS و تمدید خودکار آن با Certbot
- پنل React دوزبانهٔ فارسی (RTL) و انگلیسی (LTR)، با فونت‌های محلی Vazirmatn و Inter
- ساخت، غیرفعال‌کردن، فعال‌سازی مجدد، تغییر رمز و حذف کاربران VPN
- مشاهده و قطع نشست‌های فعال، مشاهدهٔ رویدادهای مدیریتی و دانلود گواهی CA
- انتخاب نام و رمز مدیر هنگام راه‌اندازی اولیه و تغییر آن از پنل
- پایگاه دادهٔ SQLite و بکاپ رمزگذاری‌شده برای انتقال حساب‌ها و هویت CA به VPS دیگر

برنامهٔ وب فقط روی `127.0.0.1:15151` گوش می‌دهد و Nginx درگاه عمومی HTTPS است. برنامه با کاربر سیستمی محدود اجرا می‌شود و برای عملیات محدود strongSwan از یک helper کوچک با دسترسی کنترل‌شده استفاده می‌کند.

### پیش‌نیازها

- VPS تازه با Ubuntu Server 24.04 LTS و دسترسی root
- رکورد DNS نوع A که به IPv4 عمومی VPS اشاره کند
- دسترسی ورودی TCP پورت‌های 80 و 443 و UDP پورت‌های 500 و 4500
- اگر ارائه‌دهنده فایروال یا Security Group جداگانه دارد، همین پورت‌ها باید آنجا هم باز شوند

نصب‌کننده عمداً روی نصب موجود strongSwan یا سایت Nginx دیگری اجرا نمی‌شود تا پیکربندی قبلی را بازنویسی نکند. نصب بسته‌های سیستم، گواهی اولیه و سرویس‌ها در اولین راه‌اندازی با اسکریپت انجام می‌شود؛ مدیریت حساب‌های روزمره از پنل است.

### نصب اولیه

آرشیو را روی VPS کپی و استخراج کنید، سپس در پوشهٔ پروژه اجرا کنید:

```bash
sudo bash ./install.sh
```

نصب‌کننده دامنه و ایمیل اختیاری گواهی را می‌پرسد، DNS را بررسی می‌کند و strongSwan، فایروال، Nginx، HTTPS و پنل را آماده می‌کند. در پایان یک کد یک‌بارمصرف نمایش داده می‌شود. نشانی HTTPS چاپ‌شده را باز کنید، کد را وارد کنید و نام کاربری و رمز مدیر را بسازید. کد پس از ثبت موفق مدیر مصرف می‌شود.

می‌توانید دامنه و ایمیل را هم از متغیر محیطی بدهید:

```bash
sudo VPN_DOMAIN=vpn.example.com ACME_EMAIL=admin@example.com bash ./install.sh
```

### کارهای پنل وب

بعد از نصب اولیه، از پنل برای مدیریت کاربران VPN، فعال/غیرفعال‌کردن حساب‌ها، بازنشانی رمز، قطع نشست، تغییر مشخصات مدیر، مشاهدهٔ وضعیت و گزارش فعالیت و دانلود گواهی CA استفاده کنید. رمز جدید VPN فقط هنگام ساخت یا بازنشانی نمایش داده می‌شود؛ آن را همان موقع ذخیره کنید.

برای افزودن دامنهٔ جدید یا انتقال سرویس به VPS تازه، همچنان باید DNS و دسترسی شبکهٔ ارائه‌دهنده را تنظیم کنید. جابه‌جایی سرور از مسیر بکاپ/بازیابی توضیح داده شده است. پنل فعلی ویرایش آزاد تنظیمات سیستم‌عامل یا فایروال ارائه‌دهنده را انجام نمی‌دهد.

### اتصال دستگاه‌ها

برای هر کاربر، دامنهٔ VPN، نام کاربری و رمز ساخته‌شده را ارسال کنید. گواهی `ikev2-root-ca.pem` را از پنل دانلود و روی دستگاه به‌عنوان CA مورداعتماد نصب کنید. پروتکل IKEv2 با EAP-MSCHAPv2 برای Windows، Android با strongSwan VPN Client، iOS و macOS قابل استفاده است.

حداقل طول رمز کاربران VPN دوازده نویسه و حداقل طول رمز مدیر چهارده نویسه است. به‌دلیل نیاز EAP-MSCHAPv2، رمز VPN در پایگاه دادهٔ محدودشده و فایل اعتبارنامهٔ strongSwan به‌شکل قابل‌بازیابی نگهداری می‌شود؛ رمز مدیر با scrypt و salt هش می‌شود.

### بکاپ و انتقال به VPS دیگر

روی VPS فعلی بکاپ رمزگذاری‌شده بسازید:

```bash
sudo bash ./backup.sh /root/forge-connect-backup.enc
```

یک عبارت عبور قوی انتخاب کنید و فایل رمزگذاری‌شده را به‌صورت امن از سرور خارج کنید. بکاپ شامل پایگاه دادهٔ حساب‌ها و کلید خصوصی CA است؛ هر دو را محرمانه نگه دارید.

روی VPS تازهٔ Ubuntu 24.04:

1. رکورد A دامنه را به IPv4 سرور جدید تغییر دهید و منتظر انتشار DNS بمانید.
2. بستهٔ پروژه و فایل بکاپ را به سرور جدید منتقل کنید.
3. اجرا کنید: `sudo bash ./install.sh --restore /path/to/forge-connect-backup.enc` و عبارت عبور بکاپ را وارد کنید.

بازیابی، مدیر، کاربران، گزارش فعالیت و هویت CA را نگه می‌دارد و برای دامنه گواهی سرور تازه‌ای صادر می‌کند. اگر گواهی CA قبلی روی دستگاه‌ها مورداعتماد است، نیازی به نصب مجدد آن نیست.

### فرمان‌های عیب‌یابی

```bash
sudo systemctl status ikev2-manager strongswan nginx
sudo journalctl -u ikev2-manager -u strongswan -u nginx -n 100 --no-pager
sudo swanctl --list-sas
sudo ufw status verbose
```

پایگاه داده در `/var/lib/ikev2-manager/panel.sqlite3` قرار دارد و مجوز فایل آن `0600` است. تنظیمات فایروال VPS در پنل ارائه‌دهنده باید جداگانه بررسی شود.

### ساخت رابط React برای توسعه

Node.js فقط برای ساخت رابط کاربری در محیط توسعه لازم است؛ روی VPS نصب نمی‌شود:

```bash
npm ci
npm run build
```

خروجی در `web/dist/` ساخته می‌شود و اسکریپت نصب همان خروجی را روی سرور منتشر می‌کند.

## English

### Overview

Forge Connect is a bilingual web panel for deploying and managing a self-hosted IKEv2 VPN based on strongSwan. The interface uses React/Vite and bundles Persian and English fonts locally. Its API uses Python/Flask and Python's standard SQLite module, so the VPS needs neither Node.js nor a separate database server.

### Features

- strongSwan IKEv2 with EAP-MSCHAPv2 authentication
- Server certificate and root CA generation
- IPv4 NAT and optional IPv6 when the VPS has a working public IPv6 route
- UFW rules that preserve the SSH port and open VPN/web ports
- Nginx, HTTPS certificates, and automatic renewal with Certbot
- Persian RTL and English LTR React panel with bundled Vazirmatn and Inter fonts
- Create, disable, re-enable, reset passwords, and delete VPN users
- View and revoke active sessions, review admin events, and download the CA certificate
- One-time first-admin setup and administrator credential changes in the panel
- SQLite database and encrypted backup for moving accounts and CA identity to another VPS

The web app listens only on `127.0.0.1:15151`; Nginx provides the public HTTPS entry point. The app runs as a restricted system user and uses a narrowly scoped helper for required strongSwan operations.

### Requirements

- A fresh Ubuntu Server 24.04 LTS VPS with root access
- A DNS A record pointing to the VPS public IPv4 address
- Inbound TCP ports 80 and 443, and UDP ports 500 and 4500
- If your provider has a separate firewall or security group, allow the same ports there

The installer refuses to overwrite an existing strongSwan setup or another Nginx site. The initial system packages, certificates, and services are configured by the installer; routine account management is done in the web panel.

### First installation

Copy and extract the release archive on the VPS, then run this from the project directory:

```bash
sudo bash ./install.sh
```

The installer asks for the domain and an optional certificate email, checks DNS, and configures strongSwan, the firewall, Nginx, HTTPS, and the panel. It prints a one-time setup code at the end. Open the HTTPS URL, enter the code, and create the administrator username and password. The code is consumed after successful setup.

You can provide the domain and email through environment variables:

```bash
sudo VPN_DOMAIN=vpn.example.com ACME_EMAIL=admin@example.com bash ./install.sh
```

### Web panel operations

Use the panel to create and manage VPN accounts, enable or disable users, reset passwords, revoke sessions, change administrator credentials, review service status and activity, and download the CA certificate. A new VPN password is shown only once when created or reset; save it at that time.

Adding a new domain or moving the service to another VPS still requires updating DNS and the provider's network access. Server migration is covered by the backup/restore workflow. The current panel does not provide unrestricted operating-system or provider-firewall editing.

### Client setup

Give each user the VPN domain, username, and generated password. Download `ikev2-root-ca.pem` from the panel and install it on the device as a trusted CA certificate. IKEv2 with EAP-MSCHAPv2 can be used by Windows, Android with the strongSwan VPN Client, iOS, and macOS.

VPN passwords must be at least 12 characters; administrator passwords must be at least 14 characters. EAP-MSCHAPv2 requires recoverable VPN passwords, so they are stored in the restricted database and strongSwan credentials file. Administrator passwords are salted scrypt hashes.

### Back up and migrate

Create an encrypted backup on the current VPS:

```bash
sudo bash ./backup.sh /root/forge-connect-backup.enc
```

Choose a strong passphrase and copy the encrypted file off-server securely. It contains the account database and CA private key; protect both the file and its passphrase.

On a fresh Ubuntu 24.04 VPS:

1. Point the domain's A record to the new server and wait for DNS propagation.
2. Copy the project release and encrypted backup to the new server.
3. Run `sudo bash ./install.sh --restore /path/to/forge-connect-backup.enc` and enter the backup passphrase.

Restore preserves the administrator, VPN accounts, audit log, and CA identity, then issues a new server certificate for the domain. Devices that already trust the old CA do not need to install it again.

### Troubleshooting commands

```bash
sudo systemctl status ikev2-manager strongswan nginx
sudo journalctl -u ikev2-manager -u strongswan -u nginx -n 100 --no-pager
sudo swanctl --list-sas
sudo ufw status verbose
```

The database is stored at `/var/lib/ikev2-manager/panel.sqlite3` with file mode `0600`. Provider-side firewall rules must be checked separately.

### Build the React interface

Node.js is needed only to build the frontend during development; it is not installed on the VPS:

```bash
npm ci
npm run build
```

The output is written to `web/dist/` and is deployed by the installer.
