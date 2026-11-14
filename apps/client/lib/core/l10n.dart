import 'package:flutter/widgets.dart';

const translations = <String,String>{
  'Document saved':'سند ذخیره شد',
  'Cabinet Survey AI':'برداشت کابینت', 'Sign in':'ورود', 'Register':'ثبت‌نام',
  'Email':'ایمیل', 'Password':'رمز عبور', 'Name':'نام',
  'Capture offline':'برداشت آفلاین', 'Projects':'پروژه‌ها', 'Search':'جستجو',
  'New project':'پروژه جدید', 'Title':'عنوان', 'Notes':'یادداشت', 'Save':'ذخیره',
  'Cancel':'انصراف', 'Rooms':'اتاق‌ها', 'Add room':'افزودن اتاق',
  'Walls':'دیوارها', 'Add wall':'افزودن دیوار', 'Label':'برچسب',
  'Length (mm)':'طول (میلی‌متر)', 'Height (mm)':'ارتفاع (میلی‌متر)',
  'Start X (mm)':'ایکس شروع (میلی‌متر)', 'Start Y (mm)':'وای شروع (میلی‌متر)',
  'End X (mm)':'ایکس پایان (میلی‌متر)', 'End Y (mm)':'وای پایان (میلی‌متر)',
  'Elements':'اجزا', 'Add element':'افزودن جزء', 'Kind':'نوع',
  'Offset (mm)':'فاصله از ابتدا (میلی‌متر)', 'Width (mm)':'عرض (میلی‌متر)',
  'Sill (mm)':'ارتفاع از کف (میلی‌متر)', 'Plan':'پلان', 'Elevation':'نمای دیوار',
  'Sync':'همگام‌سازی', 'Sign out':'خروج', 'Pending changes':'تغییرات ارسال‌نشده',
  'Archive':'بایگانی', 'Restore':'بازگردانی', 'Camera':'دوربین', 'Gallery':'گالری',
  'Photos':'عکس‌ها', 'Review':'بازبینی', 'Approve':'تأیید', 'Undo':'واگرد',
  'Redo':'بازانجام', 'Export':'خروجی', 'Keep server':'پذیرش نسخه سرور',
  'Conflicts':'تعارض‌ها', 'Required':'الزامی', 'Working…':'در حال انجام…',
  'Offline device workspace':'فضای محلی دستگاه',
  'Local preview — not a certified drawing':'پیش‌نمایش محلی — نقشه تأییدشده نیست',
  'No projects yet':'هنوز پروژه‌ای ثبت نشده', 'No walls yet':'هنوز دیواری ثبت نشده',
  'Customer name':'نام مشتری', 'Phone':'تلفن', 'Address':'نشانی',
  'AI candidates require review; no dimensions are inferred from pixels.':
    'پیشنهادهای هوش مصنوعی نیاز به بازبینی دارند؛ هیچ ابعادی از پیکسل‌ها استنباط نمی‌شود.',
  'Select a wall to edit its measurements':'برای ویرایش اندازه‌ها یک دیوار را انتخاب کنید',
};
String tr(BuildContext context, String text) =>
    Localizations.localeOf(context).languageCode == 'fa' ? translations[text] ?? text : text;
