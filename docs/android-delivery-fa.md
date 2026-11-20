# گزارش بررسی و تحویل نسخهٔ Android

**تاریخ:** ۱۴ نوامبر ۲۰۲۶
**تصمیم مالک:** مبنا پیاده‌سازی موجود PR #1؛ لغو وب؛ تمرکز بر بسته‌بندی و انتشار Android.
**دامنهٔ توافق‌شده:** فایل‌های پلتفرم، تنظیمات ساخت/امضا، حذف وب، CI و راهنمای ربات؛
نه رفع تمام بلاکرهای محصول که در گزینهٔ بزرگ‌تر پیشنهاد شده بود.

## ۱. نتیجهٔ بررسی اولیه

شاخهٔ شروع این اجرا فقط اسکلت داشت: صفحهٔ نمایشی Flutter، health endpoint و README ربات.
محصول واقعی در PR #1 موجود بود: مشتری/پروژه/اتاق/دیوار/اجزا، SQLite و outbox، همگام‌سازی
نسخه‌دار و تعارض، احراز هویت، هندسهٔ قطعی و golden fixtureها، خروجی PDF/PNG، بررسی
پیشنهاد تصویر AI و worker مستقل تلگرام. کد آن مبنا قرار گرفت؛ PR #1 ادغام یا بسته نشد.

گزارش بازرسی قبلی و نتیجه‌های CI قدیمی در ریپو حفظ شده‌اند، اما بالای گزارش‌های اجرایی
قدیمی برچسب **Historical** خورده است. موفقیت وب یا build یک commit قدیم، شاهد موفقیت
این نسخه یا دستگاه اندروید نیست. تغییر خودسرانهٔ workflow عبور از فازها نیز برگردانده شد؛
توقف برای تأیید مالک در مرز فازها دوباره برقرار است.

## ۲. تغییرات انجام‌شده

### حذف وب در کد و عملیات
- وابستگی SQLite browser/WASM و مسیر `kIsWeb` حذف شد؛ SQLite بومی Android باقی است.
- bootstrap تولید Android/Web و آزمون Chrome/Playwright و ساخت web حذف شد.
- serving باندل وب از Compose حذف شد؛ nginx فقط API/webhook gateway است.
- تنظیمات CORS مرورگر حذف شد؛ اسناد محصول/معماری/تصمیم‌ها Android-only شدند.
- آدرس نسبی `/api/v1/` که متکی به URL صفحهٔ مرورگر بود جای خود را به endpoint صریح داد.
- فرمت تصویر `image/webp` و اصطلاح webhook ربطی به کلاینت وب ندارند و حذف نشده‌اند.

### بسته‌بندی بومی Android
- Gradle/Kotlin، manifest، launcher/splash، wrapper و تنظیمات SDK در Git قرار گرفتند؛
  CI دیگر پوشهٔ Android را هر بار از نو تولید نمی‌کند.
- نسخهٔ ابزار: Flutter 3.35.7، Java 21، Gradle 8.12، AGP 8.9.1، Kotlin 2.1.0؛
  compile/target SDK 36، حداقل Android API 24، NDK تنظیم‌شده توسط Flutter.
- شناسهٔ release `com.cabinetsurvey.client` و debug `com.cabinetsurvey.client.debug`؛
  نسخهٔ اپ `0.2.0+2`، label فارسی/انگلیسی و پشتیبانی RTL.
- امضا از فایل خصوصی `key.properties` یا متغیرهای محیطی خوانده می‌شود. کلید/رمز در Git
  نیست. نبود کلید مالک به امضای debug برای توزیع منجر نمی‌شود؛ اسکریپت release متوقف می‌شود.
- release فقط HTTPS می‌پذیرد و HTTP خام و backup خودکار دادهٔ محلی را می‌بندد. debug
  HTTP را فقط برای میزبان محلی emulator مجاز می‌کند. endpoint پیش‌فرض debug سرور واقعی نیست.
- ذخیرهٔ PDF/PNG به Storage Access Framework بومی منتقل شد: کاربر مقصد را انتخاب می‌کند؛
  لغو انتخاب موفقیت جعلی نیست؛ مجوز گستردهٔ حافظه لازم نیست. camera/gallery از picker
  سیستم استفاده می‌کنند و permission اضافی CAMERA در manifest اعلام نشده است.
- CI برای تحلیل Dart، تست واحد، HTTP/SQLite واقعی روی VM، lint/unit بومی، APK، AAB و
  آزمون emulator با بستن/بازکردن پروسه تنظیم شد. این دروازه‌ها در CI اجرا شدند؛ نتیجهٔ دقیق HEAD در بخش ۵ ثبت شده است.

### راه‌اندازی و مستندات
- اسکریپت ساخت محیط خصوصی بدون چاپ/بازنویسی secret، اسکریپت ساخت APK/AAB و اسکریپت
  ثبت/بررسی/حذف webhook اضافه شد. اعتبار داخلی API/worker از ingress secret تلگرام تفکیک شد.
- مسیرهای داخلی Telegram در gateway عمومی بسته شدند؛ worker به API داخلی دسترسی دارد.
- [راهنمای کامل ربات و سرور](telegram-setup-fa.md) شامل BotFather، متغیرها، TLS/Compose،
  pairing، ارسال، آزمون، عیب‌یابی، backup و AI اختیاری است.

## ۳. راه‌اندازی سریع Android روی ماشین دارای SDK

این محیط Flutter/Dart/Java/Android SDK/Docker ندارد؛ دستورهای زیر روی ماشین توسعهٔ شماست.
ابتدا API را مطابق [راهنمای عملیاتی](telegram-setup-fa.md) بالا بیاورید.

```sh
cd apps/client
cp config/api.example.json config/api.json
# ویرایش کنید:
# emulator: http://10.0.2.2:8000/api/v1/
# گوشی واقعی: https://YOUR_REAL_DOMAIN/api/v1/
flutter pub get
cd ../..
bash scripts/build-android.sh debug
adb install -r apps/client/build/app/outputs/flutter-apk/app-debug.apk
```

اگر چند دستگاه وصل است، `adb -s SERIAL install -r ...`. ساخت نصب‌شدنی release:

```sh
# فقط روی ماشین امن مالک؛ این فایل نمونه را در Git قرار ندهید.
keytool -genkeypair -keystore /PRIVATE_PATH/cabinet-upload.jks \
  -alias upload -keyalg RSA -keysize 2048 -validity 10000
cp apps/client/android/key.properties.example apps/client/android/key.properties
chmod 600 apps/client/android/key.properties
# مسیر/رمزهای واقعی را در فایل خصوصی وارد کنید، یا متغیرهای زیر را تنظیم کنید:
# ANDROID_KEYSTORE_PATH, ANDROID_KEYSTORE_PASSWORD,
# ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD
bash scripts/build-android.sh release
```

خروجی: `apps/client/build/app/outputs/bundle/release/app-release.aab`.
کلید را آفلاین/در secret manager پشتیبان بگیرید؛ گم شدن آن می‌تواند به‌روزرسانی امضاشده
را دشوار کند. برای Google Play، سیاست‌های جاری کلید/Play App Signing و target SDK را
هنگام انتشار بررسی کنید. انتشار در فروشگاه انجام نشده است.

**Artifact CI برای انتشار نیست:** AAB آن با کلید موقت و دامنهٔ `.invalid` فقط کمپایل
می‌شود تا خطای ساخت پیدا شود. برای نسخهٔ متصل/قابل‌توزیع باید با دامنه و امضای مالک
بازسازی شود. این محدودیت عمداً به‌جای پنهان کردن نبود اطلاعات مالک حفظ شده است.

## ۴. راه‌اندازی ربات — خلاصه

1. در BotFather ربات بسازید و توکن را فقط در `.env` خصوصی سرور قرار دهید.
2. `python scripts/init-environment.py` یک‌بار اجرا و secretهای مستقل را تنظیم کنید؛
   توکن و دامنهٔ HTTPS واقعی را دستی وارد کنید.
3. DNS و TLS مالک را به gateway داخلی `127.0.0.1:8080` متصل کنید.
4. `docker compose --env-file .env -f deploy/compose.yml up --build -d`.
5. env خصوصی را load کنید و `python scripts/configure-telegram.py set` سپس `info` بزنید.
6. در اپ Telegram → کد یک‌بارمصرف؛ در چت خصوصی ربات `/pair CODE`.
7. اندازه‌ها را تأیید/Sync کنید، Export بگیرید و ارسال خروجی موجود را انتخاب کنید.

جزئیات و جدول تفاوت سه secret در [راهنمای ربات](telegram-setup-fa.md).
**کد ربات روی تلگرام host نمی‌شود؛ VPS/Docker متعلق به شما لازم است.**

## ۵. وضعیت آزمون و شواهد

| بررسی | نتیجه در این اجرا |
|---|---|
| نصب تمیز وابستگی‌های Python و `pip check` | موفق؛ ناسازگاری گزارش نشد |
| `backend`: `../.venv/bin/python -m pytest -q` | **101 passed، 3 skipped، 2 warnings** پس از تغییرات |
| worker: `PYTHONPATH=. ../../.venv/bin/python -m pytest -q` | **6 passed، 1 warning**؛ HTTP mock، نه تلگرام واقعی |
| `python -m pytest tests -q` در ریشه | **9 passed**؛ لغو وب، manifest/signing، YAML، تنظیم webhook، عدم افشای توکن و حفظ .env |
| compileall، lint بحرانی Python، XML، shell syntax و diff whitespace | موفق |
| checksum wrapper Gradle | با checksum رسمی Gradle 8.12 تطبیق داده شد |
| Flutter analyze/test، native unit/lint و ساخت APK/AAB | **PASS در GitHub Actions** روی HEAD `1654566c716a4c56a471c390711c4f9cb6dd3ff6`؛ ابزار در sandbox محلی موجود نبود |
| emulator اندروید API 35 | **PASS در CI**؛ ورود آفلاین فارسی، ساخت پروژه، force-stop و بازکردن دوباره با SQLite واقعی |
| گوشی فیزیکی، تعامل picker و دوربین | تأیید نشده؛ emulator جای پذیرش دستگاه فیزیکی را نمی‌گیرد |
| Docker/TLS/وب‌هوک/ارسال واقعی ربات | اجرا نشده؛ توکن/دامنه/سرور ارائه نشده |
| PostgreSQL migration/concurrency و بازیابی disposable | **PASS در CI همان HEAD**؛ upgrade/check/downgrade، هم‌زمانی و بازیابی آزمایشگاهی |

برای جمع‌آوری شواهد **همان HEAD جاری** پس از اجرای CI:
`python scripts/check-head-ci.py gase99/cabinet-survey-ai docs/evidence/android-head-checks.json`.
این اسکریپت دیگر نتیجهٔ PR #1 را جایگزین برنچ جاری نمی‌کند. شواهد همان HEAD کد در
[`evidence/android-head-checks.json`](evidence/android-head-checks.json) ثبت شده: هر پنج job موفق.
این فایل گزارش، بعد از آن commit مستندسازی شده و نباید به‌عنوان SHA اجرای دوبارهٔ CI معرفی شود.

اجرای موفق کد `1654566`:
- [Android APK/AAB و emulator](https://github.com/gase99/cabinet-survey-ai/actions/runs/43606213998)
- [Backend و PostgreSQL](https://github.com/gase99/cabinet-survey-ai/actions/runs/43606214171)
- [Worker](https://github.com/gase99/cabinet-survey-ai/actions/runs/43606214046)

Artifact عمومی CI: `android-ci-builds-not-for-publication`، حجم گزارش‌شده ۱۱۸٬۳۹۶٬۹۸۰ بایت،
انقضا ۱۲ فوریهٔ ۲۰۲۷. در لینک execution بالا قابل دریافت است؛ فایل باینری بزرگ وارد Git نشده.
خطاهای واقعیِ پیداشده در مسیر ساخت اصلاح شدند: colon بدون quote در YAML، محل درست
`includeSubdomains` روی تک‌تک domainها، و optional Play Core در R8. هیچ lint detector یا
warning عمومی برای سبز کردن CI غیرفعال نشد؛ قاعدهٔ R8 فقط Play Core استفاده‌نشده را پوشش می‌دهد.

## ۶. آنچه هنوز تکمیل یا تأیید نشده است

این تحویل packaging را کامل می‌کند، اما محصول را release-ready اعلام نمی‌کند:

- برداشت آفلاین، ورود دستی، preview و بخش‌های اساسی backend موجودند؛ import خودکار
  candidate AI، crop/perspective/OCR، voice، ویرایشگر کامل drag/snapping و undo پایدار ناقص‌اند.
- همگام‌سازی دستی است؛ انتقال مهمان به حساب، sync عکس/حذف، tombstone و reconnect پس‌زمینه کامل نیست.
- خروجی سرور فعلاً اتاق اول را انتخاب می‌کند؛ شکل‌دهی فونت فارسی و مقیاس چاپ فیزیکی تأیید نشده.
  از preview محلی برای ساخت قطعهٔ حساس بدون بررسی نقشه استفاده نکنید.
- auto-approval برخی ورودهای دستی، mutation دادهٔ approved، audit/history کامل و کنترل‌های
  concurrency/rest طبق گزارش بازرسی نیاز به بازبینی محصول دارند؛ در دامنهٔ انتخاب‌شده رفع نشدند.
- SQLite و عکس‌های محلی رمزنگاری نشده‌اند؛ backup اندروید غیرفعال شده ولی امنیت دستگاه
  فیزیکی/اشتراکی را تضمین نمی‌کند. secure storage فقط از credential نشست محافظت می‌کند.
- rate limit بعضی مسیرها، retention/cleanup، malware scan، readiness/structured logging،
  lockfile کامل ابزارها و آزمون امنیت مستقل هنوز کار دارند.
- worker تک‌replica و at-least-once است؛ لغو ارسال، ارسال در جریان را پس نمی‌گیرد.
- هاست واقعی، کلید امضای مالک، توکن ربات، مجوز provider پولی و پذیرش دستگاه/فروشگاه لازم است.

**جمع‌بندی:** وب از مسیر جاری حذف شده، ساخت Android و آزمون پایهٔ emulator در CI موفق است
و راهنمای ربات آماده شده است. مرحلهٔ بعد پذیرش روی دستگاه فیزیکی، امضا/هاست مالک و استقرار واقعی است؛ رفع بلاکرهای
محصول بالا فاز جداگانه‌ای است که مطابق دستورالعمل ریپو به تأیید شما نیاز دارد.
