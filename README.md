# Forge Connect

پنل وب دوزبانه برای راه‌اندازی و مدیریت یک سرویس شخصی IKEv2 VPN مبتنی بر strongSwan. رابط کاربری با React/Vite ساخته شده و فونت‌های فارسی و انگلیسی را همراه خود دارد. API با Python/Flask و SQLite استاندارد پایتون اجرا می‌شود؛ روی سرور نیازی به نصب Node.js یا سرویس جداگانهٔ پایگاه داده نیست.

**Languages / زبان‌ها:** [فارسی](#فارسی) · [English](#english)

## فارسی

### امکانات

- نصب strongSwan و IKEv2 با احراز هویت EAP از طریق FreeRADIUS
- WireGuard با ساخت پروفایل جداگانه برای هر دستگاه
- OpenConnect/ocserv با احراز هویت و حسابداری مشترک FreeRADIUS
- ساخت گواهی سرور و CA ریشه برای اعتماد دستگاه‌های کاربران
- NAT برای IPv4 و فعال‌سازی IPv6 در صورت وجود مسیر عمومی IPv6 روی VPS
- تنظیم UFW با حفظ پورت SSH و باز کردن پورت‌های VPN و وب
- راه‌اندازی Nginx، گواهی HTTPS و تمدید خودکار آن با Certbot
- پنل React دوزبانهٔ فارسی (RTL) و انگلیسی (LTR)، با فونت‌های محلی Vazirmatn و Inter
- پورتال جداگانهٔ کاربر برای مشاهدهٔ مصرف واقعی، اعتبار، تغییر رمز، درخواست تمدید و دریافت پروفایل‌ها
- تنظیم حجم مجاز، مدت اعتبار، پروتکل‌ها و سقف اتصال IKEv2 برای هر حساب
- ثبت ترافیک IKEv2، WireGuard و OpenConnect و غیرفعال‌کردن خودکار حساب پس از انقضا یا پایان سهمیه
- ساخت، غیرفعال‌کردن، فعال‌سازی مجدد، تغییر رمز و حذف کاربران VPN
- طرح‌های تمدید، بررسی دستی رسیدها و ربات فروش تلگرام با تحویل خودکار حساب تأییدشده
- راهنمای تصویری فارسی/انگلیسی برای Windows، Android و iOS در پورتال کاربر
- مشاهده و قطع نشست‌های فعال، مشاهدهٔ رویدادهای مدیریتی و دانلود گواهی CA
- انتخاب نام و رمز مدیر هنگام راه‌اندازی اولیه و تغییر آن از پنل
- پایگاه دادهٔ SQLite و بکاپ رمزگذاری‌شده برای انتقال حساب‌ها، CA و کلید WireGuard سرور به VPS دیگر

برنامهٔ وب فقط روی `127.0.0.1:15151` گوش می‌دهد و Nginx درگاه عمومی HTTPS است. برنامه با کاربر سیستمی محدود اجرا می‌شود و برای عملیات محدود strongSwan از یک helper کوچک با دسترسی کنترل‌شده استفاده می‌کند.

### پیش‌نیازها

- VPS تازه با Ubuntu Server 24.04 LTS و دسترسی root
- رکورد DNS نوع A که به IPv4 عمومی VPS اشاره کند
- دسترسی ورودی TCP پورت‌های 80، 443 و 8443؛ UDP پورت‌های 500، 4500، 51820 و 8443
- اگر ارائه‌دهنده فایروال یا Security Group جداگانه دارد، همین پورت‌ها باید آنجا هم باز شوند

نصب‌کننده روی پیکربندی موجود strongSwan، ocserv یا سایت Nginx اجرا نمی‌شود تا تنظیم قبلی را بازنویسی نکند. نصب IKEv2، WireGuard، OpenConnect، forwarding و NAT پایدار IPv4/IPv6 (در صورت وجود IPv6)، UFW، Nginx، HTTPS و پنل در نصب اولیه انجام می‌شود؛ مدیریت روزمره حساب‌ها از پنل است.

### نصب اولیه

آرشیو را روی VPS کپی و استخراج کنید، سپس در پوشهٔ پروژه اجرا کنید:

```bash
sudo bash ./install.sh
```

برای پاک‌سازی کامل نصب قبلی (قبل از نصب مجدد روی همان VPS):

```bash
sudo bash ./uninstall.sh
```

نصب‌کننده دامنه و ایمیل اختیاری گواهی را می‌پرسد، DNS را بررسی می‌کند و strongSwan، فایروال، Nginx، HTTPS و پنل را آماده می‌کند. در پایان یک کد یک‌بارمصرف نمایش داده می‌شود. نشانی HTTPS چاپ‌شده را باز کنید، کد را وارد کنید و نام کاربری و رمز مدیر را بسازید. کد پس از ثبت موفق مدیر مصرف می‌شود.

می‌توانید دامنه و ایمیل را هم از متغیر محیطی بدهید:

```bash
sudo VPN_DOMAIN=vpn.example.com ACME_EMAIL=admin@example.com bash ./install.sh
```

### کارهای پنل وب

بعد از نصب اولیه، مدیر از پنل برای ساخت کاربران و تنظیم سهمیه، اعتبار، پروتکل و سقف نشست استفاده می‌کند. تنظیم فروش تلگرام، کارت پرداخت، طرح‌ها، رسیدها و درخواست‌های تمدید نیز در بخش تنظیمات است. برای هر کاربر نشانی `/portal` و مشخصات اولیه را بفرستید؛ کاربر در آنجا مصرف و اعتبارش را می‌بیند، رمز را تغییر می‌دهد، تمدید می‌خواهد و پروفایل دستگاه می‌گیرد. رمز جدید فقط هنگام ساخت یا بازنشانی نمایش داده می‌شود.

سقف نشست IKEv2 و OpenConnect با Simultaneous-Use در FreeRADIUS و حسابداری نشست اعمال می‌شود. سقف WireGuard در تعداد پروفایل‌های دستگاه حساب اعمال می‌شود؛ WireGuard به‌تنهایی هویت کاربر/دستگاه را در سطح نشست‌هایی مثل RADIUS ارائه نمی‌کند؛ سقف آن شمارندهٔ مشترک با دو پروتکل دیگر نیست.

برای افزودن دامنهٔ جدید یا انتقال سرویس به VPS تازه، همچنان باید DNS و دسترسی شبکهٔ ارائه‌دهنده را تنظیم کنید. جابه‌جایی سرور از مسیر بکاپ/بازیابی توضیح داده شده است. پنل فعلی ویرایش آزاد تنظیمات سیستم‌عامل یا فایروال ارائه‌دهنده را انجام نمی‌دهد.

### اتصال دستگاه‌ها

OpenConnect روی `8443/TCP+UDP` و با مسیر پیش‌فرض full-tunnel تنظیم می‌شود. نصب‌کننده برای poolهای VPN قواعد forwarding و NAT را به‌صورت پایدار می‌سازد و DNS تونل را تنظیم می‌کند؛ اگر VPS مسیر عمومی IPv6 داشته باشد، pool و forwarding/NAT IPv6 نیز فعال می‌شود. بدون IPv6 عمومی روی VPS، تونل فقط IPv4 را پوشش می‌دهد. پورت‌های لازم را در فایروال ارائه‌دهنده هم باز کنید.

در پنل کاربر راهنمای تصویری و پروفایل‌های قابل دریافت قرار دارد. Android فایل `.sswan` را در strongSwan VPN Client وارد می‌کند؛ iPhone فایل `.mobileconfig` را نصب می‌کند؛ Windows فایل `Forge-Connect-Windows.cmd` را با یک دابل‌کلیک (با اجازه Administrator) گواهی CA را در Trusted Root نصب و پروفایل IKEv2 را می‌سازد — بعد فقط رمز VPN را در تنظیمات ویندوز وارد کنید. تصاویر راهنما از مستندات و راهنماهای پلتفرم‌ها هستند و پیوند منبع کنار هر تصویر درج شده است. WireGuard از پنل کاربر برای هر دستگاه یک فایل پیکربندی مستقل می‌سازد؛ آن فایل حاوی کلید خصوصی است و باید مانند رمز محرمانه نگهداری شود.

حداقل طول رمز کاربران VPN چهار نویسه و حداقل طول رمز مدیر چهارده نویسه است. برای احراز هویت IKEv2، رمز VPN در پایگاه دادهٔ محدودشده و فهرست محلی FreeRADIUS به‌شکل قابل‌بازیابی نگهداری می‌شود؛ رمز مدیر با scrypt و salt هش می‌شود. پورت‌های TCP/UDP شمارهٔ 8443 را برای OpenConnect و UDP شمارهٔ 51820 را برای WireGuard علاوه بر فایروال سیستم در پنل شبکهٔ ارائه‌دهندهٔ VPS نیز باز کنید.

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

- strongSwan IKEv2 with EAP authentication through FreeRADIUS
- WireGuard with a separate client profile for each device
- OpenConnect/ocserv with shared FreeRADIUS authentication and accounting
- Server certificate and root CA generation
- IPv4 NAT and optional IPv6 when the VPS has a working public IPv6 route
- UFW rules that preserve the SSH port and open VPN/web ports
- Nginx, HTTPS certificates, and automatic renewal with Certbot
- Persian RTL and English LTR React panel with bundled Vazirmatn and Inter fonts
- User portal for usage, expiry, password changes, renewal requests, and client profiles
- Per-user quota, validity, allowed protocols, and IKEv2 simultaneous-use limits
- IKEv2 and WireGuard traffic accounting with automatic expiry/quota suspension
- Telegram sales bot with plans, manual receipt review, and automatic delivery after approval
- Bilingual illustrated Windows, Android, and iOS connection guides in the user portal
- Create, disable, re-enable, reset passwords, and delete VPN users
- View and revoke active sessions, review admin events, and download the CA certificate
- One-time first-admin setup and administrator credential changes in the panel
- SQLite database and encrypted backup for moving accounts, CA identity, and WireGuard server key to another VPS

The web app listens only on `127.0.0.1:15151`; Nginx provides the public HTTPS entry point. The app runs as a restricted system user and uses a narrowly scoped helper for required strongSwan operations.

### Requirements

- A fresh Ubuntu Server 24.04 LTS VPS with root access
- A DNS A record pointing to the VPS public IPv4 address
- Inbound TCP ports 80, 443, and 8443; UDP ports 500, 4500, 51820, and 8443
- If your provider has a separate firewall or security group, allow the same ports there

The installer refuses to overwrite an existing strongSwan, ocserv, or Nginx site setup. It installs IKEv2, WireGuard, OpenConnect, persistent IPv4/IPv6 forwarding and NAT (when IPv6 is available), UFW rules, Nginx, HTTPS, and the panel. Routine account management is done in the web panel.

### First installation

Copy and extract the release archive on the VPS, then run this from the project directory:

```bash
sudo bash ./install.sh
```

To wipe a previous install on the same VPS before reinstalling:

```bash
sudo bash ./uninstall.sh
```

The installer asks for the domain and an optional certificate email, checks DNS, and configures strongSwan, the firewall, Nginx, HTTPS, and the panel. It prints a one-time setup code at the end. Open the HTTPS URL, enter the code, and create the administrator username and password. The code is consumed after successful setup.

You can provide the domain and email through environment variables:

```bash
sudo VPN_DOMAIN=vpn.example.com ACME_EMAIL=admin@example.com bash ./install.sh
```

### Web panel operations

Use the panel to create accounts and set per-user quota, validity, protocols, and session limits. Configure Telegram sales, plans, payment details, receipt review, and renewal requests from Settings. Give each user the `/portal` address and their initial credentials. Users can view usage and expiry, change their password, request renewal, and download device profiles. A new VPN password is shown only once when created or reset.

IKEv2 and OpenConnect session limits use FreeRADIUS Simultaneous-Use and session accounting. WireGuard limits the number of active device profiles for each account; WireGuard does not expose the same RADIUS-style per-login session model, so its limit is not a shared counter with the other protocols.

Adding a new domain or moving the service to another VPS still requires updating DNS and the provider's network access. Server migration is covered by the backup/restore workflow. The current panel does not provide unrestricted operating-system or provider-firewall editing.

OpenConnect uses `8443/TCP+UDP` with a default full-tunnel route. The installer persists forwarding and NAT rules for the VPN pools and configures tunnel DNS. If the VPS has working public IPv6 routing, an IPv6 pool and IPv6 forwarding/NAT are enabled too. Without public IPv6 on the VPS, the tunnel covers IPv4 only. Provider firewall rules still need to allow the required ports.

### Client setup

The user portal includes illustrated setup guides and downloadable profiles. Android imports the `.sswan` file into strongSwan VPN Client; iPhone installs the `.mobileconfig` profile; Windows downloads `Forge-Connect-Windows.cmd`, which installs the CA into Trusted Root and creates the IKEv2 profile in one elevated double-click — then enter the VPN password in Windows VPN settings. Screenshot sources and platform instructions are linked beside each image. WireGuard creates a separate config file per device in the portal; it contains the private key and must be kept secret.

VPN passwords must be at least 4 characters; administrator passwords must be at least 14 characters. IKEv2 authentication requires recoverable VPN passwords, so they are stored in the restricted database and local FreeRADIUS users file. Administrator passwords are salted scrypt hashes. Also allow TCP and UDP 8443 in the VPS provider firewall for OpenConnect, and UDP 51820 for WireGuard.

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
