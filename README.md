# Cabinet Survey AI — Android

برداشت میدانی کابینت با Flutter، فارسی/انگلیسی، ذخیرهٔ آفلاین و API مستقل.

**تصمیم جاری: فقط Android. نسخهٔ وب لغو شده است.** وضعیت محصول پیش‌انتشار است؛
تکمیل بسته‌بندی اندروید به معنی تکمیل همهٔ قابلیت‌های نقشه‌کشی/AI یا تأیید انتشار نیست.

## گزارش فارسی و راه‌اندازی
- [گزارش تحویل، محدودیت‌ها و مسیر انتشار اندروید](docs/android-delivery-fa.md)
- [راهنمای گام‌به‌گام راه‌اندازی ربات تلگرام و سرور](docs/telegram-setup-fa.md)
- [توسعهٔ محلی](docs/local-development.md) و [ساخت Android](apps/client/README.md)

## ساختار
- `apps/client`: کلاینت Flutter فقط برای Android؛ فایل‌های پلتفرم در Git نگهداری می‌شوند.
- `backend`: FastAPI، PostgreSQL، همگام‌سازی، هندسهٔ قطعی و خروجی PDF/PNG.
- `services/telegram-bot`: ورکر مستقل روی سرور تحت کنترل مالک، نه کد میزبانی‌شده در تلگرام.
- `deploy`: PostgreSQL/API/worker و درگاه API/وب‌هوک؛ بدون کلاینت وب.
- `docs`: تصمیم‌ها، قراردادها و سوابق بررسی. گزارش‌های قدیمِ Android/Web صرفاً تاریخی‌اند.

## شروع سریع
```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/init-environment.py  # یک‌بار؛ .env موجود را بازنویسی نمی‌کند
# توکن ربات و دامنهٔ HTTPS واقعی را فقط در .env خصوصی تنظیم کنید.
docker compose --env-file .env -f deploy/compose.yml up --build -d
```

برای APK، Flutter **3.35.7**، Java 21 و Android SDK لازم است. فایل
`apps/client/config/api.example.json` را به `api.json` کپی و نشانی API واقعی را تنظیم کنید؛
سپس `bash scripts/build-android.sh debug`. برای release، امضای مالک و HTTPS الزامی است.
هیچ توکن یا کلید امضایی نباید وارد اپ یا Git شود.

## اصول تغییرناپذیر
اندازه‌ها عدد صحیح میلی‌مترند؛ مقیاس از پیکسل حدس زده نمی‌شود؛ خروجی AI فقط پیشنهاد است؛
تأیید کاربر الزامی است؛ مختصات نهایی را هندسهٔ قطعی تولید می‌کند؛ برداشت آفلاین مستقل از
AI کار می‌کند؛ نقشه و نما از یک مدل مشترک‌اند. سوابق تأیید و منشأ باید حفظ شوند.

[دستورالعمل مشارکت](AGENTS.md) · [نقشهٔ راه مرحله‌ای](docs/development-roadmap.md)
