# توسعهٔ محلی — Android only

## پیش‌نیاز
Git، Python 3.11+، Docker/Compose، Flutter 3.35.7، Java 21 و Android SDK/NDK مطابق
[راهنمای کلاینت](../apps/client/README.md). وب و Chrome بخشی از گردش کار نیستند.

## API و پایگاه داده
```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
python scripts/init-environment.py       # فقط بار اول؛ مقادیر در خروجی چاپ نمی‌شوند
docker compose up -d db                 # PostgreSQL توسعه روی localhost:5432
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
`.env` در ریشه ساخته می‌شود؛ برای اجرای محلی از ریشه استفاده کنید:
`uvicorn app.main:app --app-dir backend --reload --env-file .env` ممکن است تنظیمات
اپ را منتقل نکند، زیرا Settings فایل `.env` را نسبت به پوشهٔ جاری می‌خواند. روش مطمئن:
`set -a; . ./.env; set +a` سپس اجرای uvicorn از ریشه با `--app-dir backend`.
در PowerShell متغیرها را در محیط فرایند تنظیم کنید؛ فایل رمز را در Git نگذارید.

صحت: `http://localhost:8000/health`. برای emulator اندروید از
`http://10.0.2.2:8000/api/v1/` استفاده کنید، نه localhost گوشی. برای دستگاه فیزیکی،
HTTPS واقعی لازم است؛ HTTP خام را روی اینترنت منتشر نکنید.

## کلاینت
فایل‌های Android از قبل موجودند؛ bootstrap یا تولید مجدد پلتفرم لازم نیست.
```sh
cd apps/client
cp config/api.example.json config/api.json  # نشانی واقعی را تنظیم کنید
flutter pub get
flutter run -d ANDROID_DEVICE_ID --dart-define-from-file=config/api.json
```

## آزمون‌ها
```sh
# از ریشه، پس از فعال‌سازی venv
python -m pytest tests -q
cd backend && python -m pytest -q
cd ../services/telegram-bot && PYTHONPATH=. python -m pytest -q
cd ../../apps/client
flutter analyze --no-fatal-infos
flutter test
```
سه تست PostgreSQL در مجموعهٔ اصلی بدون سامانهٔ جداگانه skip می‌شوند. برای اجرای آن‌ها
فقط روی پایگاه دادهٔ آزمایشگاهی disposable، `ACCEPTANCE_DISPOSABLE_DATABASE=1` و
`DATABASE_URL` مناسب تنظیم شود؛ هرگز روی دادهٔ مشتری اجرا نکنید. CI این آزمون‌ها و
migration upgrade/check/downgrade را روی PostgreSQL جدا اجرا می‌کند.

راهنمای کامل استقرار و ربات: [telegram-setup-fa.md](telegram-setup-fa.md).
هیچ ادعای اجرای Docker، ساخت APK یا ارسال واقعی تلگرام صرفاً بر اساس این دستورات وجود ندارد.
