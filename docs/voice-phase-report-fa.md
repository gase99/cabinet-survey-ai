# گزارش اجرای فاز برداشت صوتی (PR #2)

**تاریخ:** ۱۴ نوامبر ۲۰۲۶ · **شاخه:** `arena/d880f4a8-cabinet-survey-ai` · **مبنای شروع:** `6b0329389eb3`

این گزارش فقط کارهای واقعاً انجام‌شده و آزموده‌شده را ثبت می‌کند. ادعایی فراتر از
شواهد موجود وجود ندارد.

## ۱. وضعیت ابتدایی
- PR #1 بسته‌شده و ادغام‌نشده بود؛ PR #2 باز و غیر Draft در `6b032938` با ۵ چک سبز.
- `main` صرفاً اسکلت مستندات بود (`ada72ae`) و PR #2 ادامهٔ مستقیم (fast-forward) آن است.
- کار فاز صوت روی همین شاخهٔ PR #2 انجام شد؛ تاریخی بازنویسی نشد و force-push انجام نشد.

## ۲. فایل‌های تغییر یافته/ایجادشده
بک‌اند:
- `backend/app/domain/spoken_measurements.py` (جدید) — تجزیه‌گر قطعی گفتار فارسی.
- `backend/app/ai/speech.py` (جدید) — انتزاع STT مستقل از ارائه‌دهنده.
- `backend/app/ai/provider.py` — `parse_measurements_any` (ادغام برچسب‌دار + گفتاری).
- `backend/app/api/v1/ai.py` — اتصال `parse-text` و تکمیل مسیر صوتی `transcription`.
- `backend/app/services/uploads.py` — اعتبارسنجی صوت با امضای محتوا و محدودیت حجم.
- `backend/app/core/config.py` — تنظیمات `STT_PROVIDER/BASE_URL/API_KEY/MODEL/AUDIO_MAX_BYTES`.
- `backend/app/services/export_service.py` + `backend/app/api/v1/exports.py` — خروجی چنداتاقه.
- `backend/tests/test_spoken_measurements.py` (۲۱ تست)، `test_transcription.py`، `test_export.py`.

کلاینت:
- `apps/client/lib/core/api.dart` — `parseText` با بدنهٔ form-encoded.
- `apps/client/lib/domain/voice.dart` (جدید) — نگاشت پیشنهادها، تشخیص تعارض.
- `apps/client/lib/features/voice_intake.dart` (جدید) — صفحهٔ برداشت صوتی.
- `apps/client/lib/features/workspace.dart` — `editWall` با prefill، جریان `voiceIntake`.
- `apps/client/lib/core/l10n.dart` — رشته‌های فارسی/انگلیسی.
- `apps/client/test/voice_test.dart`, `voice_intake_test.dart` (جدید)، `api_test.dart` (توسعه).

مستندات: `docs/decisions.md` (ADR-007)، `docs/project-status.md`، `docs/local-development.md`،
`CHANGELOG.md`، `.env.example`.

## ۳. پیاده‌سازی‌شده‌ها
- گفتار فارسی محاوره‌ای → پیشنهاد ساخت‌یافته به میلی‌متر (اعداد حرفی، ترکیبی مثل
  «سه متر و بیست سانتی‌متر» → ۳۲۰۰، مقیاس «هزار/میلیون»، اعشار «۳٫۲ متر»، تعیین نوع
  اندازه از زمینه، اصلاح («نه، …»)، تعارض‌ها و ابهام‌ها به‌صورت پرسش؛ هیچ مقداری اختراع
  نمی‌شود و مختصات تولید نمی‌شود).
- STT مستقل از ارائه‌دهنده و fail-closed؛ بدون اعتبارنامه پاسخ 503 روشن + مسیر متنی.
- افشای ارسال بیرونی (`external_transmission` + پیام) در پاسخ آپلود صوتی.
- خروجی PDF/PNG همهٔ اتاق‌ها (رفع محدودیت «فقط اتاق اول») با خطای ۴۰۰/۴۰۹ برچسب‌دار اتاق.
- صفحهٔ برداشت صوتی در کلاینت: تحلیل متن گفتار، کارت پیشنهاد با نقل‌قول گفته‌شده،
  تعارض‌ها برجسته، «اعمال» فقط فرم تأیید-اول موجود را prefill می‌کند
  (`voice_ai`/`needs_review`)؛ اصلاح‌ها از مسیر ویرایش عادی با حفظ تاریخچهٔ بازبینی.
- ضبط صدا روی دستگاه (RECORD_AUDIO) عمداً به فاز بعد موکول شد.

## ۴. نتایج دقیق آزمون
- محلی (پایتون ۳.۱۴، وابستگی‌ها از site-packages): تجزیه‌گر **۲۱/۲۱ پاس**؛
  مجموعهٔ کامل بک‌اند: **127 passed, 3 skipped, 4 failed** — هر ۴ خطا فقط گپ محیطی PNG
  است (`ModuleNotFoundError: No module named '_rl_renderPM'`) که در CI با `rl-renderPM`
  پین‌شده پوشش داده می‌شود؛ شمارش صفحات PDF چنداتاقه (۱۰ صفحه) محلی پاس شد.
- کلاینت/Flutter: ابزار Dart محلی موجود نیست؛ `flutter analyze` و `flutter test` در CI
  (`android-ci`) اجرا می‌شوند. نتایج دقیق این کامیت در بخش CI همین گزارش/وضعیت چک‌ها.

## ۵. وضعیت CI (کامیت `fbb2dd6` → اصلاح `69b4429`)
- در `fbb2dd6` گام `flutter analyze` شکست خورد (خطای `Json` بدون import در تست جدید)؛
  بک‌اند و migration سبز بودند. اصلاح در `69b4429` push شد و نتیجهٔ چک‌های آن کامیت
  ملاک نهایی است.

## ۶. موارد ناتمام و بلاکرها
- **آزمون دستگاه فیزیکی اندروید انجام نشده** (دسترسی به دستگاه وجود نداشت) و همین
  موضوع طبق شرط ادغام، مانع merge است.
- ضبط صدا روی دستگاه، اعتبارنامهٔ واقعی STT، تست زندهٔ Telegram و امضای انتشار: بیرونی/فاز بعد.
- Local-first lifecycle کامل و رمزنگاری در حال استراحت (SQLCipher + Android Keystore): فازهای بعدی.
- ویرایشگر کشیدن/اسنپ کامل، PDF فارسی با شکل‌دهی حروف، undo/redo پایدار: مراحل بعد.

## ۷. وضعیت ادغام
**PR #2 ادغام نشده است.** طبق بند ادغام، عدم پذیرش دستگاه فیزیکی ریسک از دست رفتن داده
یا شکست انتشار دارد؛ ادغام تا پذیرش دستگاه و سبز بودن کامل CI انجام نمی‌شود.
