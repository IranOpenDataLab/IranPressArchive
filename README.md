# آرشیو مطبوعات ایران — Iran Press Archive

آرشیو متن‌باز شماره‌های اسکن‌شده روزنامه‌های تاریخی ایران. فایل‌های PDF در همین ریپو نگهداری می‌شوند، دانلود از طریق GitHub Actions (دستی) انجام می‌شود و فهرست پایین صفحه به‌صورت خودکار ساخته می‌شود.

## منابع فعلی

| روزنامه | شناسه | نوع منبع |
|---|---|---|
| توس | `tous` | پوشه گوگل‌درایو |
| جامعه | `jameeh` | پوشه گوگل‌درایو |
| عصر آزادگان | `asr-azadegan` | پوشه گوگل‌درایو |
| نشاط | `neshat` | دنباله ترتیبی (۱۳۷۷: شماره ۱–۲۴، ۱۳۷۸: شماره ۲۵–۱۴۸) |

## نحوه اجرا (بدون نیاز به سیستم شخصی)

تب **Actions** ریپو ← **Fetch Archive** ← **Run workflow**:
- `source`: خالی = همه منابع، یا شناسه یک منبع (مثل `neshat`)
- `dry_run`: فقط گزارش بدون دانلود

لاگ کامل هر خطا (traceback و پاسخ‌های API) در خروجی همان اجرا قابل مشاهده است. فایل‌های جدید بعد از هر اجرا به‌صورت خودکار کامیت و پوش می‌شوند.

اجرای محلی هم ممکن است:

```bash
pip install -r requirements.txt
python fetch.py --dry-run      # گزارش بدون دانلود
python fetch.py --source tous  # فقط یک منبع
python make_index.py           # فقط بازسازی فهرست
```

## ساختار ریپو

```
archive/<id>/          فایل‌های PDF هر نشریه (یک زیرپوشه به ازای هر منبع)
data/manifest.json     منیفست مرکزی: نام، تاریخ، اندازه و sha256 هر فایل
fetch.py               واکشگر: دانلود + ثبت منیفست + بازسازی فهرست
make_index.py          بازسازی مستقل فهرست از روی محتوای archive/
urls.yml               تعریف منابع و ساختار لینک هرکدام
.github/workflows/     ورکفلوی اجرای دستی (Run workflow)
```

## فشرده‌سازی خودکار فایل‌های بزرگ (apdf.io)

اگر فایلی از سقف ۱۰۰ مگابایت گیت بزرگ‌تر باشد و کلید API تنظیم شده باشد، URL اصلی فایل به سرویس [apdf.io](https://apdf.io) (ایندپوینت `POST /pdf/file/compress`) فرستاده می‌شود؛ وضعیت job تا تکمیل poll می‌شود و نسخه فشرده دانلود و در آرشیو ذخیره می‌گردد (در منیفست با `compressed: true` علامت می‌خورد). اگر فشرده‌سازی هم نتواند فایل را زیر سقف بیاورد یا خطا بدهد، همان فایل رد می‌شود و کار ادامه می‌یابد.

**تنظیم کلید (لازم):** کلید API هرگز در خود ریپو ذخیره نمی‌شود. در گیت‌هاب: `Settings ← Secrets and variables ← Actions ← New repository secret` با نام `APDF_API_KEY` و مقدار توکن حساب apdf.io. ورکفلو این Secret را به‌صورت متغیر محیطی به اسکریپت می‌دهد.

برای اجرای محلی هم می‌توانید متغیر محیطی بدهید:

```bash
APDF_API_KEY=your-token python fetch.py
```

نکته‌ها و محدودیت‌های سرویس: هر درخواست فشرده‌سازی به‌صورت async اجرا می‌شود (poll با فاصله ۵ ثانیه و مهلت ۲۰ دقیقه برای هر فایل)؛ فایل‌های نتیجه ۶۰ دقیقه روی سرور سرویس می‌مانند و باید بلافاصله دانلود شوند؛ و طبق مستندات، فایل ارسالی به سرویس نباید از ۱۰۰ مگابایت بزرگ‌تر باشد — اگر سرویس روی فایل‌های بزرگ‌تر خطا بدهد، خطای کامل آن در لاگ Workflow دیده می‌شود و فایل رد می‌شود.

## انواع ساختار لینک پشتیبانی‌شده

- **google_drive_folder** — پوشه عمومی درایو (سطح اشتراک: «هر کس که لینک دارد»)
- **google_drive_file** — فایل تکی درایو
- **index_page** — صفحه فهرست لینک؛ با `extensions` و `recursive`
- **url_sequence** — دنباله ترتیبی شماره‌ها؛ با `url_template` (شامل `{year}` و `{issue}`) و `sequences` (بازه سال/شماره) — مناسب ساختارهایی مثل `site.com/dl/paper/1377/1.pdf`
- **direct_files** — فهرست دستی URL فایل‌ها

## تاب‌آوری و محدودیت‌های گیت‌هاب

- خطای یک فایل فقط همان فایل را رها می‌کند؛ دانلود به لینک بعدی می‌رود
- خطای یک منبع فقط همان منبع را رها می‌کند؛ منابع بعدی اجرا می‌شوند
- تلاش مجدد خودکار (۳ بار با فاصله) برای خطاهای شبکه؛ فایل‌های 404 فقط ثبت می‌شوند
- **فایل موجود روی دیسک هرگز دوباره دانلود نمی‌شود** (چک پیش از هر درخواست شبکه‌ای)
- سقف حجم هر فایل دقیقا ۱۰۰ مگابایت (۱۰۰ MiB) است — همان هاردلیمیت گیت‌هاب؛ قابل تنظیم با `max_file_mb`
- بین دانلودها مکث اختیاری (`delay_seconds`) اعمال می‌شود تا سرور منبع فشار نیاورد

## تاریخ شماره‌ها

تاریخ از نام فایل استخراج می‌شود؛ قالب‌های جلالی و میلادی (با جداکننده یا فشرده) تشخیص داده و برای مرتب‌سازی به میلادی تبدیل می‌شوند. برای منابع ترتیبی مثل نشاط، نمایش «سال — شماره» ساخته می‌شود. الگوی اختصاصی با `date_regex` تعریف می‌شود.

## نگهداری در آینده

- منبع حقیقت داده `data/manifest.json` است؛ فهرست README فقط بازتولید آن است
- فهرست README بین نشانگرهای `AUTO-INDEX` ساخته می‌شود؛ متن دستی بیرون از نشانگرها دست نمی‌خورد
- افزودن منبع جدید = فقط یک آیتم در `urls.yml`
- اجرای مجدد امن است؛ فایل‌های قبلی دوباره دانلود نمی‌شوند

---

## فهرست نشریات

<!-- AUTO-INDEX:START -->
### نشاط (`neshat`)

تعداد شماره‌های آرشیوشده: **121**

| تاریخ | عنوان / شماره | فایل |
|---|---|---|
| سال 1378 — شماره 147 | neshat 1378 147 | [دانلود](archive/neshat/neshat_1378_147.pdf) |
| سال 1378 — شماره 146 | neshat 1378 146 | [دانلود](archive/neshat/neshat_1378_146.pdf) |
| سال 1378 — شماره 145 | neshat 1378 145 | [دانلود](archive/neshat/neshat_1378_145.pdf) |
| سال 1378 — شماره 144 | neshat 1378 144 | [دانلود](archive/neshat/neshat_1378_144.pdf) |
| سال 1378 — شماره 143 | neshat 1378 143 | [دانلود](archive/neshat/neshat_1378_143.pdf) |
| سال 1378 — شماره 141 | neshat 1378 141 | [دانلود](archive/neshat/neshat_1378_141.pdf) |
| سال 1378 — شماره 140 | neshat 1378 140 | [دانلود](archive/neshat/neshat_1378_140.pdf) |
| سال 1378 — شماره 139 | neshat 1378 139 | [دانلود](archive/neshat/neshat_1378_139.pdf) |
| سال 1378 — شماره 138 | neshat 1378 138 | [دانلود](archive/neshat/neshat_1378_138.pdf) |
| سال 1378 — شماره 137 | neshat 1378 137 | [دانلود](archive/neshat/neshat_1378_137.pdf) |
| سال 1378 — شماره 135 | neshat 1378 135 | [دانلود](archive/neshat/neshat_1378_135.pdf) |
| سال 1378 — شماره 134 | neshat 1378 134 | [دانلود](archive/neshat/neshat_1378_134.pdf) |
| سال 1378 — شماره 133 | neshat 1378 133 | [دانلود](archive/neshat/neshat_1378_133.pdf) |
| سال 1378 — شماره 132 | neshat 1378 132 | [دانلود](archive/neshat/neshat_1378_132.pdf) |
| سال 1378 — شماره 131 | neshat 1378 131 | [دانلود](archive/neshat/neshat_1378_131.pdf) |
| سال 1378 — شماره 129 | neshat 1378 129 | [دانلود](archive/neshat/neshat_1378_129.pdf) |
| سال 1378 — شماره 128 | neshat 1378 128 | [دانلود](archive/neshat/neshat_1378_128.pdf) |
| سال 1378 — شماره 127 | neshat 1378 127 | [دانلود](archive/neshat/neshat_1378_127.pdf) |
| سال 1378 — شماره 126 | neshat 1378 126 | [دانلود](archive/neshat/neshat_1378_126.pdf) |
| سال 1378 — شماره 125 | neshat 1378 125 | [دانلود](archive/neshat/neshat_1378_125.pdf) |
| سال 1378 — شماره 123 | neshat 1378 123 | [دانلود](archive/neshat/neshat_1378_123.pdf) |
| سال 1378 — شماره 122 | neshat 1378 122 | [دانلود](archive/neshat/neshat_1378_122.pdf) |
| سال 1378 — شماره 121 | neshat 1378 121 | [دانلود](archive/neshat/neshat_1378_121.pdf) |
| سال 1378 — شماره 120 | neshat 1378 120 | [دانلود](archive/neshat/neshat_1378_120.pdf) |
| سال 1378 — شماره 119 | neshat 1378 119 | [دانلود](archive/neshat/neshat_1378_119.pdf) |
| سال 1378 — شماره 117 | neshat 1378 117 | [دانلود](archive/neshat/neshat_1378_117.pdf) |
| سال 1378 — شماره 116 | neshat 1378 116 | [دانلود](archive/neshat/neshat_1378_116.pdf) |
| سال 1378 — شماره 115 | neshat 1378 115 | [دانلود](archive/neshat/neshat_1378_115.pdf) |
| سال 1378 — شماره 114 | neshat 1378 114 | [دانلود](archive/neshat/neshat_1378_114.pdf) |
| سال 1378 — شماره 113 | neshat 1378 113 | [دانلود](archive/neshat/neshat_1378_113.pdf) |
| سال 1378 — شماره 111 | neshat 1378 111 | [دانلود](archive/neshat/neshat_1378_111.pdf) |
| سال 1378 — شماره 110 | neshat 1378 110 | [دانلود](archive/neshat/neshat_1378_110.pdf) |
| سال 1378 — شماره 109 | neshat 1378 109 | [دانلود](archive/neshat/neshat_1378_109.pdf) |
| سال 1378 — شماره 108 | neshat 1378 108 | [دانلود](archive/neshat/neshat_1378_108.pdf) |
| سال 1378 — شماره 105 | neshat 1378 105 | [دانلود](archive/neshat/neshat_1378_105.pdf) |
| سال 1378 — شماره 104 | neshat 1378 104 | [دانلود](archive/neshat/neshat_1378_104.pdf) |
| سال 1378 — شماره 101 | neshat 1378 101 | [دانلود](archive/neshat/neshat_1378_101.pdf) |
| سال 1378 — شماره 99 | neshat 1378 099 | [دانلود](archive/neshat/neshat_1378_099.pdf) |
| سال 1378 — شماره 98 | neshat 1378 098 | [دانلود](archive/neshat/neshat_1378_098.pdf) |
| سال 1378 — شماره 97 | neshat 1378 097 | [دانلود](archive/neshat/neshat_1378_097.pdf) |
| سال 1378 — شماره 96 | neshat 1378 096 | [دانلود](archive/neshat/neshat_1378_096.pdf) |
| سال 1378 — شماره 95 | neshat 1378 095 | [دانلود](archive/neshat/neshat_1378_095.pdf) |
| سال 1378 — شماره 94 | neshat 1378 094 | [دانلود](archive/neshat/neshat_1378_094.pdf) |
| سال 1378 — شماره 93 | neshat 1378 093 | [دانلود](archive/neshat/neshat_1378_093.pdf) |
| سال 1378 — شماره 92 | neshat 1378 092 | [دانلود](archive/neshat/neshat_1378_092.pdf) |
| سال 1378 — شماره 91 | neshat 1378 091 | [دانلود](archive/neshat/neshat_1378_091.pdf) |
| سال 1378 — شماره 90 | neshat 1378 090 | [دانلود](archive/neshat/neshat_1378_090.pdf) |
| سال 1378 — شماره 88 | neshat 1378 088 | [دانلود](archive/neshat/neshat_1378_088.pdf) |
| سال 1378 — شماره 87 | neshat 1378 087 | [دانلود](archive/neshat/neshat_1378_087.pdf) |
| سال 1378 — شماره 86 | neshat 1378 086 | [دانلود](archive/neshat/neshat_1378_086.pdf) |
| سال 1378 — شماره 82 | neshat 1378 082 | [دانلود](archive/neshat/neshat_1378_082.pdf) |
| سال 1378 — شماره 81 | neshat 1378 081 | [دانلود](archive/neshat/neshat_1378_081.pdf) |
| سال 1378 — شماره 80 | neshat 1378 080 | [دانلود](archive/neshat/neshat_1378_080.pdf) |
| سال 1378 — شماره 76 | neshat 1378 076 | [دانلود](archive/neshat/neshat_1378_076.pdf) |
| سال 1378 — شماره 75 | neshat 1378 075 | [دانلود](archive/neshat/neshat_1378_075.pdf) |
| سال 1378 — شماره 74 | neshat 1378 074 | [دانلود](archive/neshat/neshat_1378_074.pdf) |
| سال 1378 — شماره 72 | neshat 1378 072 | [دانلود](archive/neshat/neshat_1378_072.pdf) |
| سال 1378 — شماره 70 | neshat 1378 070 | [دانلود](archive/neshat/neshat_1378_070.pdf) |
| سال 1378 — شماره 69 | neshat 1378 069 | [دانلود](archive/neshat/neshat_1378_069.pdf) |
| سال 1378 — شماره 66 | neshat 1378 066 | [دانلود](archive/neshat/neshat_1378_066.pdf) |
| سال 1378 — شماره 64 | neshat 1378 064 | [دانلود](archive/neshat/neshat_1378_064.pdf) |
| سال 1378 — شماره 63 | neshat 1378 063 | [دانلود](archive/neshat/neshat_1378_063.pdf) |
| سال 1378 — شماره 62 | neshat 1378 062 | [دانلود](archive/neshat/neshat_1378_062.pdf) |
| سال 1378 — شماره 61 | neshat 1378 061 | [دانلود](archive/neshat/neshat_1378_061.pdf) |
| سال 1378 — شماره 60 | neshat 1378 060 | [دانلود](archive/neshat/neshat_1378_060.pdf) |
| سال 1378 — شماره 59 | neshat 1378 059 | [دانلود](archive/neshat/neshat_1378_059.pdf) |
| سال 1378 — شماره 58 | neshat 1378 058 | [دانلود](archive/neshat/neshat_1378_058.pdf) |
| سال 1378 — شماره 57 | neshat 1378 057 | [دانلود](archive/neshat/neshat_1378_057.pdf) |
| سال 1378 — شماره 56 | neshat 1378 056 | [دانلود](archive/neshat/neshat_1378_056.pdf) |
| سال 1378 — شماره 55 | neshat 1378 055 | [دانلود](archive/neshat/neshat_1378_055.pdf) |
| سال 1378 — شماره 54 | neshat 1378 054 | [دانلود](archive/neshat/neshat_1378_054.pdf) |
| سال 1378 — شماره 53 | neshat 1378 053 | [دانلود](archive/neshat/neshat_1378_053.pdf) |
| سال 1378 — شماره 52 | neshat 1378 052 | [دانلود](archive/neshat/neshat_1378_052.pdf) |
| سال 1378 — شماره 51 | neshat 1378 051 | [دانلود](archive/neshat/neshat_1378_051.pdf) |
| سال 1378 — شماره 49 | neshat 1378 049 | [دانلود](archive/neshat/neshat_1378_049.pdf) |
| سال 1378 — شماره 48 | neshat 1378 048 | [دانلود](archive/neshat/neshat_1378_048.pdf) |
| سال 1378 — شماره 47 | neshat 1378 047 | [دانلود](archive/neshat/neshat_1378_047.pdf) |
| سال 1378 — شماره 46 | neshat 1378 046 | [دانلود](archive/neshat/neshat_1378_046.pdf) |
| سال 1378 — شماره 45 | neshat 1378 045 | [دانلود](archive/neshat/neshat_1378_045.pdf) |
| سال 1378 — شماره 44 | neshat 1378 044 | [دانلود](archive/neshat/neshat_1378_044.pdf) |
| سال 1378 — شماره 43 | neshat 1378 043 | [دانلود](archive/neshat/neshat_1378_043.pdf) |
| سال 1378 — شماره 42 | neshat 1378 042 | [دانلود](archive/neshat/neshat_1378_042.pdf) |
| سال 1378 — شماره 41 | neshat 1378 041 | [دانلود](archive/neshat/neshat_1378_041.pdf) |
| سال 1378 — شماره 40 | neshat 1378 040 | [دانلود](archive/neshat/neshat_1378_040.pdf) |
| سال 1378 — شماره 39 | neshat 1378 039 | [دانلود](archive/neshat/neshat_1378_039.pdf) |
| سال 1378 — شماره 38 | neshat 1378 038 | [دانلود](archive/neshat/neshat_1378_038.pdf) |
| سال 1378 — شماره 37 | neshat 1378 037 | [دانلود](archive/neshat/neshat_1378_037.pdf) |
| سال 1378 — شماره 36 | neshat 1378 036 | [دانلود](archive/neshat/neshat_1378_036.pdf) |
| سال 1378 — شماره 35 | neshat 1378 035 | [دانلود](archive/neshat/neshat_1378_035.pdf) |
| سال 1378 — شماره 34 | neshat 1378 034 | [دانلود](archive/neshat/neshat_1378_034.pdf) |
| سال 1378 — شماره 33 | neshat 1378 033 | [دانلود](archive/neshat/neshat_1378_033.pdf) |
| سال 1378 — شماره 32 | neshat 1378 032 | [دانلود](archive/neshat/neshat_1378_032.pdf) |
| سال 1378 — شماره 31 | neshat 1378 031 | [دانلود](archive/neshat/neshat_1378_031.pdf) |
| سال 1378 — شماره 30 | neshat 1378 030 | [دانلود](archive/neshat/neshat_1378_030.pdf) |
| سال 1378 — شماره 29 | neshat 1378 029 | [دانلود](archive/neshat/neshat_1378_029.pdf) |
| سال 1378 — شماره 28 | neshat 1378 028 | [دانلود](archive/neshat/neshat_1378_028.pdf) |
| سال 1378 — شماره 27 | neshat 1378 027 | [دانلود](archive/neshat/neshat_1378_027.pdf) |
| سال 1378 — شماره 26 | neshat 1378 026 | [دانلود](archive/neshat/neshat_1378_026.pdf) |
| سال 1378 — شماره 25 | neshat 1378 025 | [دانلود](archive/neshat/neshat_1378_025.pdf) |
| سال 1377 — شماره 23 | neshat 1377 023 | [دانلود](archive/neshat/neshat_1377_023.pdf) |
| سال 1377 — شماره 22 | neshat 1377 022 | [دانلود](archive/neshat/neshat_1377_022.pdf) |
| سال 1377 — شماره 21 | neshat 1377 021 | [دانلود](archive/neshat/neshat_1377_021.pdf) |
| سال 1377 — شماره 20 | neshat 1377 020 | [دانلود](archive/neshat/neshat_1377_020.pdf) |
| سال 1377 — شماره 19 | neshat 1377 019 | [دانلود](archive/neshat/neshat_1377_019.pdf) |
| سال 1377 — شماره 18 | neshat 1377 018 | [دانلود](archive/neshat/neshat_1377_018.pdf) |
| سال 1377 — شماره 16 | neshat 1377 016 | [دانلود](archive/neshat/neshat_1377_016.pdf) |
| سال 1377 — شماره 15 | neshat 1377 015 | [دانلود](archive/neshat/neshat_1377_015.pdf) |
| سال 1377 — شماره 14 | neshat 1377 014 | [دانلود](archive/neshat/neshat_1377_014.pdf) |
| سال 1377 — شماره 13 | neshat 1377 013 | [دانلود](archive/neshat/neshat_1377_013.pdf) |
| سال 1377 — شماره 12 | neshat 1377 012 | [دانلود](archive/neshat/neshat_1377_012.pdf) |
| سال 1377 — شماره 11 | neshat 1377 011 | [دانلود](archive/neshat/neshat_1377_011.pdf) |
| سال 1377 — شماره 10 | neshat 1377 010 | [دانلود](archive/neshat/neshat_1377_010.pdf) |
| سال 1377 — شماره 9 | neshat 1377 009 | [دانلود](archive/neshat/neshat_1377_009.pdf) |
| سال 1377 — شماره 8 | neshat 1377 008 | [دانلود](archive/neshat/neshat_1377_008.pdf) |
| سال 1377 — شماره 7 | neshat 1377 007 | [دانلود](archive/neshat/neshat_1377_007.pdf) |
| سال 1377 — شماره 6 | neshat 1377 006 | [دانلود](archive/neshat/neshat_1377_006.pdf) |
| سال 1377 — شماره 5 | neshat 1377 005 | [دانلود](archive/neshat/neshat_1377_005.pdf) |
| سال 1377 — شماره 4 | neshat 1377 004 | [دانلود](archive/neshat/neshat_1377_004.pdf) |
| سال 1377 — شماره 3 | neshat 1377 003 | [دانلود](archive/neshat/neshat_1377_003.pdf) |
| سال 1377 — شماره 2 | neshat 1377 002 | [دانلود](archive/neshat/neshat_1377_002.pdf) |
| سال 1377 — شماره 1 | neshat 1377 001 | [دانلود](archive/neshat/neshat_1377_001.pdf) |
<!-- AUTO-INDEX:END -->
