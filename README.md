# Online Web Control

لوحة تحكم ويب لأجهزة Enigma2 (بورت **7070**) + بلجن لتشغيلها وإيقافها من قائمة الرسيفر.

## التثبيت بأمر واحد (على الرسيفر)

```sh
wget -qO- https://raw.githubusercontent.com/YOUR_USER/OnlineWebControl/main/install.sh | sh
```

الرسيفر هيعمل ريستارت للواجهة تلقائياً بعد التثبيت.

## التثبيت بملف ipk

```sh
wget -O /tmp/owc.ipk https://raw.githubusercontent.com/YOUR_USER/OnlineWebControl/main/dist/enigma2-plugin-extensions-onlinewebcontrol_all.ipk
opkg install /tmp/owc.ipk
killall -9 enigma2
```

أو انسخ الملف من `dist/` للرسيفر بـ FTP وثبّته من قائمة البلجنات.

## الاستخدام

1. من قائمة البلجنات افتح **Online Web Control**.
2. الزر الأخضر **تشغيل**، الأحمر **إيقاف**، الأصفر **تشغيل تلقائي**، الأزرق **تحديث**.
3. افتح من المتصفح: `http://IP-الرسيفر:7070`
4. بيانات الدخول الافتراضية: `admin` / `admin` (غيّرها من أول ملف `plugin/online_web_control.py`).

## الإعدادات (أول `plugin/online_web_control.py`)

| الإعداد | الوظيفة |
|---|---|
| `AUTH_USER` / `AUTH_PASS` | حماية الدخول (فاضي = بدون حماية) |
| `SUPPORT_URL` / `SITE_URL` / `STORE_URL` | روابط الأزرار السفلية |
| `PANEL_UPDATE_URL` | رابط زر «تحديث اللوحة» (مضبوط على هذا الريبو) |
| `XSTREAMITY_URL` / `XKLASS_URL` | سكربت تثبيت البلجن (فاضي = `opkg install`) |

## هيكل الريبو

```
plugin/            كود البلجن واللوحة (هنا تتم كل التعديلات)
dist/              ملف ipk الجاهز
docs/              ملف الشرح PDF والبوست
install.sh         أمر التثبيت
build_ipk.sh       بناء ipk جديد
setup.sh           ضبط اسم حساب GitHub في الملفات
VERSION            رقم الإصدار
```

## تحديث الإصدار

1. عدّل الملفات داخل `plugin/`.
2. غيّر الرقم في `VERSION` وسجّل التغيير في `CHANGELOG.md`.
3. شغّل `./build_ipk.sh` ثم ارفع كل شيء على GitHub:

```sh
git add -A && git commit -m "v1.1" && git push
```

الرسيفر بيتحدث بأمر التثبيت نفسه، أو من زر «تحديث اللوحة» داخل الصفحة.

## المتطلبات

- Python 3 على الرسيفر.
- تيرمنال اللوحة بصلاحيات root، فغيّر بيانات الدخول قبل ما تفتح البورت خارج الشبكة.
