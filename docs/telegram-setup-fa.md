# راه‌اندازی سرور و ربات تلگرام — نسخهٔ Android

تاریخ راهنما: ۱۴ نوامبر ۲۰۲۶. این راهنمای عملیاتی است، نه گزارش استقرار انجام‌شده.
هیچ توکن واقعی، دامنهٔ متعلق به شما یا VPS در اختیار این اجرا نبوده است.

## ۱. معماری و چیزی که واقعاً باید میزبانی شود

```text
اپ Android ── HTTPS ── درگاه TLS مالک ── nginx داخلی ── FastAPI ── PostgreSQL
                                │                         │
                                └── /telegram/webhook     ├── فایل‌های PDF/PNG
                                         │                │
                                    ورکر مستقل تلگرام ─────
                                         │
                                   Telegram Bot API
```

**تلگرام کد پایتون این پروژه را اجرا یا میزبانی نمی‌کند.** فقط پیام و فایل را از طریق
Bot API منتقل می‌کند. API، پایگاه داده و ورکر باید روی VPS، سرور Docker یا رایانش ابری
تحت کنترل شما باشند. Self-hosted Bot API server هم میزبان منطق این اپ نیست و لازم نیست.
کلاینت وب لغو شده؛ nginx موجود فقط درگاه API و وب‌هوک است، نه میزبان فایل‌های وب.

پیش‌نیاز پیشنهادی: Linux با دسترسی مدیر، Docker Engine و Compose plugin، دامنهٔ واقعی
با DNS درست، reverse proxy دارای گواهی معتبر HTTPS روی پورت ۴۴۳، و BotFather.
منابع را با بار واقعی اندازه‌گیری کنید؛ عدد ظرفیت تضمین‌شده‌ای در این ریپو وجود ندارد.
خرید سرویس، تغییر DNS و دریافت گواهی در این اجرا انجام نشده است.

## ۲. ساخت ربات و دریافت توکن

1. در حساب تلگرام مالک، گفت‌وگوی رسمی **BotFather** را باز کنید و `/newbot` بفرستید.
2. نام نمایشی و username منحصربه‌فرد که به `bot` ختم می‌شود انتخاب کنید.
3. توکن تحویلی را فقط در secret manager یا `.env` خصوصی سرور نگه دارید؛ در چت پشتیبانی،
   اپ اندروید، Git، تصویر صفحه یا دستور دارای خروجی عمومی قرار ندهید.
4. ربات را برای کاربر آزمایشی در دسترس قرار دهید. pairing فقط در **چت خصوصی** پذیرفته
   می‌شود؛ گروه/کانال پذیرفته نیست. کاربر باید ابتدا چت را شروع کند تا ربات بتواند پاسخ دهد.
5. اگر توکن افشا شد، در BotFather آن را revoke/rotate کنید، مقدار سرور را عوض و ورکر را
   مجدداً راه‌اندازی کنید. وب‌هوک متعلق به توکن قبلی جایگزین تنظیمات توکن جدید نمی‌شود.

## ۳. تنظیم محرمانهٔ محیط

روی ماشین امن و پوشهٔ ریپو:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/init-environment.py
chmod 600 .env
```

اسکریپت `.env` موجود را بازنویسی نمی‌کند و رمزهای تولیدشده را چاپ نمی‌کند. سپس با ویرایشگر
روی سرور، `TELEGRAM_BOT_TOKEN` را با توکن BotFather و `TELEGRAM_WEBHOOK_URL` را با دامنهٔ
واقعی خود پر کنید. از نشانی‌های `example` به‌عنوان دامنهٔ عملیاتی استفاده نکنید.

| متغیر | محل مصرف | توضیح |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL/Compose | رمز پایگاه داده؛ مقدار نمونه را استفاده نکنید |
| `JWT_SECRET` | API | کلید تصادفی حداقل ۳۲ کاراکتر برای نشست‌ها |
| `SECRET_ENCRYPTION_KEY` | API | کلید معتبر Fernet برای رمزنگاری کلید provider؛ جدا از DB پشتیبان بگیرید |
| `TELEGRAM_BOT_TOKEN` | فقط ورکر | توکن رسمی BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | ورکر + ثبت وب‌هوک | secret تصادفی مستقل؛ در header تلگرام برمی‌گردد |
| `TELEGRAM_WORKER_SECRET` | API و ورکر | اعتبار مشترک مسیر داخلی؛ در ورکر به `BACKEND_WORKER_SECRET` نگاشت می‌شود |
| `TELEGRAM_WEBHOOK_URL` | اسکریپت ثبت | `https://DOMAIN/telegram/webhook`، بدون توکن در URL |
| `AI_PROVIDER` | API | پیش‌فرض `disabled`؛ فعال‌سازی نیازمند مجوز/کلید مستقل است |

سه اعتبار تلگرام باید **متفاوت** باشند. نام `TELEGRAM_WEBHOOK_SECRET` در تلگرام با
`TELEGRAM_WORKER_SECRET` در FastAPI یکی نیست. header مسیر داخلی فعلاً نام تاریخی
`X-Webhook-Secret` دارد؛ header ورودی تلگرام `X-Telegram-Bot-Api-Secret-Token` است.
فایل `.env` را به image کپی نکنید؛ Compose متغیرهای لازم هر سرویس را صریح می‌دهد.

`DATABASE_URL` نمونه برای اجرای API روی میزبان و `localhost` است. Compose آن را برای
داخل شبکه به `db:5432` بازنویسی می‌کند. رمز تولیدشده hexadecimal است و مشکل escape کردن
URL ندارد؛ در تغییر دستی رمز، کاراکترهای رزروشده را درست encode کنید.

## ۴. HTTPS و اجرای سرویس‌ها

نمونهٔ مسیردهی reverse proxy تحت کنترل مالک (NGINX روی میزبان):

```nginx
server {
    listen 443 ssl;
    server_name api.your-domain.example;
    # certificate/key paths must be the owner's real, valid certificate files.
    ssl_certificate     /PRIVATE_TLS_PATH/fullchain.pem;
    ssl_certificate_key /PRIVATE_TLS_PATH/privkey.pem;
    client_max_body_size 16m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 100s;
    }
}
```

این فقط الگو است: مسیر گواهی، دامنه، تنظیمات TLS و تمدید را خودتان اعمال کنید.
پورت ۴۴۳ باید معتبر و در دسترس تلگرام باشد. درگاه داخلی پروژه عمداً روی
`127.0.0.1:8080` گوش می‌دهد. پورت PostgreSQL، API و worker را عمومی نکنید.
فایروال ورودی را به SSH مدیریتی و HTTPS محدود کنید. مسیرهای internal backend از gateway
عمومی بسته‌اند؛ worker از شبکهٔ داخلی Docker به API می‌رسد.

```sh
# Validate without printing expanded secret values in a support report:
docker compose --env-file .env -f deploy/compose.yml config --quiet
docker compose --env-file .env -f deploy/compose.yml up --build -d
docker compose --env-file .env -f deploy/compose.yml ps
curl --fail https://YOUR_REAL_DOMAIN/health
```

انتظار: `/health` وضعیت `ok` دارد؛ db/api/telegram سالم‌اند. migration در شروع کانتینر API
با `alembic upgrade head` اجرا می‌شود. health فعلی liveness است، نه readiness کامل دیسک،
صف، ظرفیت یا همهٔ وابستگی‌ها. لاگ‌ها:

```sh
docker compose --env-file .env -f deploy/compose.yml logs --tail=100 api telegram
```

خروجی لاگ را قبل از اشتراک‌گذاری بازبینی کنید. درخواست‌های HTTP پر از توکن را ثبت نکنید.

## ۵. ثبت وب‌هوک رسمی

پیاده‌سازی فعلی **webhook** است؛ long polling پیاده‌سازی نشده و نباید هم‌زمان یک poller
دیگر برای همین توکن اجرا شود. اسکریپت رسمی HTTPS را صدا می‌زند و توکن را چاپ نمی‌کند:

```sh
# Load private env in the current shell; do not enable shell tracing.
set -a; . ./.env; set +a
python scripts/configure-telegram.py set
python scripts/configure-telegram.py info
```

`set` آدرس، ingress secret، `allowed_updates=["message"]` و اتصال محدود را ثبت می‌کند؛
صف موجود را دور نمی‌ریزد. `info` تعداد پیام‌های معلق و تاریخ آخرین خطا را نشان می‌دهد.
برای حذف مسیر، `python scripts/configure-telegram.py delete`؛ این هم صف را دور نمی‌ریزد.
در پاسخ خطا، متن خام پاسخ/URL چاپ نمی‌شود تا توکن تصادفاً منتشر نشود.

آدرس ثبت‌شده باید دقیقاً به `/telegram/webhook` روی ورکر برسد، نه مسیر قدیمی FastAPI
که پاسخ 501 می‌دهد. پس از ثبت، `/start` یا پیام راهنما در چت خصوصی بفرستید و دوباره `info`
بگیرید؛ پردازش موفق باید صف معلق را کاهش دهد. خطای گواهی/401/اتصال را پیش از ادامه رفع کنید.

## ۶. اتصال حساب و ارسال فایل از Android

1. APK را با HTTPS API واقعی ساخته و نصب کنید؛ وارد حساب شوید یا ثبت‌نام کنید.
2. در صفحهٔ پروژه‌ها، **Telegram** را بزنید تا کد pairing ده‌دقیقه‌ای و یک‌بارمصرف بگیرید.
3. در چت خصوصی ربات، دقیقاً `/pair CODE` بفرستید. پاسخ موفق: `Account linked...`.
4. در اپ دوباره Telegram را باز کنید؛ وضعیت linked باید نمایش داده شود. کد را در گزارش،
   عکس یا لاگ عمومی نگذارید. درخواست کد جدید، کد قبلی استفاده‌نشده را باطل می‌کند.
5. پروژه/اتاق/دیوار/اجزا را وارد یا بازبینی کنید؛ تأیید اندازه‌ها الزامی است. سپس Sync کنید.
6. Export بگیرید؛ فرمت PDF/PNG و A4/A3 را انتخاب کنید. سرور فقط دادهٔ واجد شرایط را خروجی
   می‌گیرد. در کنترل Telegram پروژه، خروجی آمادهٔ موجود را صریحاً برای ارسال انتخاب کنید.
7. صف ارسال را worker پردازش می‌کند. PDF و PNG هر دو **document** ارسال می‌شوند تا PNG
   به عکس فشرده تبدیل نشود. دریافت فایل در چت و وضعیت `sent` در
   `/api/v1/telegram/deliveries` را بررسی کنید؛ `queued` به‌معنای تحویل نیست.

برای لغو اتصال، endpoint احراز‌شدهٔ `DELETE /api/v1/telegram/unlink` ارسال‌های pending را
لغو می‌کند. ارسال ήδη.پذیرفته‌شده توسط تلگرام قابل پس گرفتن نیست. UI کامل مدیریت unlink/تلاش
مجدد هنوز محدودیت دارد؛ وضعیت را از API بررسی کنید.

## ۷. آزمون پذیرش واقعی، نه صرفاً mock

با حساب و پروژهٔ ساختگی و مجوز مالک اجرا کنید:

- [ ] گواهی TLS معتبر، مسیر وب‌هوک درست و ingress secret مستقل؛ درخواست بدون secret رد شود.
- [ ] `/pair` موفق، کد منقضی/تکراری رد، گروه رد، نشست‌های کاربران از هم جدا.
- [ ] خروجی تأییدنشده رد؛ PDF و PNG واقعی دریافت و محتوایشان بازبینی شود.
- [ ] restart ورکر باعث گم شدن صف/رسید نشود؛ update تکراری دوباره pair نکند.
- [ ] قطع موقت API/تلگرام retry ایجاد کند؛ پس از پنج تلاش ناموفق send، وضعیت failed گزارش شود.
- [ ] unlink مانع ارسال cachedِ لغوشده شود؛ محدودیت ارسال هم‌زمان پذیرفته شود.
- [ ] فایل خارج از پوشهٔ exports ارسال نشود؛ worker فقط read-only access به خروجی‌ها دارد.
- [ ] backup/restore جداگانه با جلوگیری از ارسال مجدد پیام‌های مشتری آزمایش شود.

تحویل **at-least-once** است: crash بعد از قبول فایل توسط تلگرام و قبل از ذخیرهٔ رسید ممکن
است ارسال تکراری بدهد؛ ادعای exactly-once نکنید. فقط **یک replica** از worker اجرا کنید.

## ۸. عیب‌یابی و نگهداری

| نشانه | بررسی |
|---|---|
| `Pairing failed` | تاریخ/انقضا، کد جدید، اتصال worker به API، تطابق worker secret، لاگ بدون رمز |
| وب‌هوک 401 | secret ثبت‌شده با `TELEGRAM_WEBHOOK_SECRET` ورکر یکسان باشد؛ header عبور کند |
| `last_error_date` / صف مانده | DNS، TLS، فایروال، مسیر gateway و سلامت worker را بررسی کنید |
| `queued` ولی فایل نمی‌رسد | یک worker، حجم مشترک exports، دسترسی فایل، pending/cancel و retry را بررسی کنید |
| `Worker secrets...` | هر سه اعتبار باید تنظیم و حداقل ۲۰ کاراکتر باشند؛ از رمز حدسی استفاده نکنید |
| خطای DB هنگام startup | رمز/URL، سلامت db و migration را بررسی کنید؛ DB مشتری را پاک نکنید |
| اپ متصل نمی‌شود | APK را با API واقعی بسازید؛ emulator آدرس `10.0.2.2`، دستگاه واقعی HTTPS دارد |

حجم‌های PostgreSQL، assets، exports و worker state را پشتیبان بگیرید؛ دسترسی UID 10001،
نگهداری/حذف دادهٔ مشتری و کلید رمزنگاری را مدیریت کنید. جزئیات [operations.md](operations.md).
مانیتورینگ ساختاریافته، malware scanning، retention و بازیابی production هنوز تأیید نشده‌اند.

## ۹. AI اختیاری

برداشت و هندسهٔ محلی بدون AI کار می‌کنند. برای تحلیل آنلاین طرح، مالک باید provider و
هزینه را مجاز کند، `AI_PROVIDER=openai_compatible`، مدل و HTTPS endpoint و کلید سمت سرور
را تنظیم کند؛ ذخیرهٔ کلید از admin به `SECRET_ENCRYPTION_KEY` معتبر نیاز دارد. سپس با طرح
ساختگی، عبارت منبع و ناحیهٔ منبع را بررسی کنید. خروجی همچنان **پیشنهاد** است و وارد کردن
خودکار آن به اندازه‌ها پیاده‌سازی نشده. voice/OCR کامل نیز هنوز تکمیل نیست. کلید را داخل
Android قرار ندهید و درخواست پولی صرفاً برای «تست موفقیت» ارسال نکنید.
