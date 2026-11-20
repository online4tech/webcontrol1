# -*- coding: utf-8 -*-
# يبني docs/guide.pdf (يحتاج: pip install reportlab arabic-reshaper python-bidi)
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white

FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("R", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("B", FD + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("M", FD + "DejaVuSansMono.ttf"))

W, H = 595, 842
MX = 40
GOLD, DARK, GREEN = HexColor("#f5b800"), HexColor("#111111"), HexColor("#3ddc97")
c = canvas.Canvas("guide.pdf", pagesize=(W, H))
c.setTitle("Online Web Control - دليل سريع")
y = H - 40


def sh(t):
    return get_display(arabic_reshaper.reshape(t))


def wrap(t, font, size, maxw):
    words, lines, cur = t.split(" "), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(sh(test), font, size) <= maxw:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def para(t, size=11, font="R", indent=0, color=DARK, gap=17):
    global y
    c.setFillColor(color)
    c.setFont(font, size)
    for ln in wrap(t, font, size, W - 2 * MX - indent):
        c.drawRightString(W - MX - indent, y, sh(ln))
        y -= gap


def heading(t):
    global y
    y -= 10
    c.setFillColor(GOLD)
    c.rect(W - MX - 5, y - 5, 5, 20, stroke=0, fill=1)
    c.setFillColor(DARK)
    c.setFont("B", 14)
    c.drawRightString(W - MX - 14, y, sh(t))
    y -= 26


def step(n, t):
    global y
    c.setFillColor(GOLD)
    c.circle(W - MX - 9, y + 4, 9, stroke=0, fill=1)
    c.setFillColor(DARK)
    c.setFont("B", 10)
    c.drawCentredString(W - MX - 9, y + 1, str(n))
    para(t, indent=26)


def bullet(t):
    global y
    c.setFillColor(GOLD)
    c.circle(W - MX - 4, y + 4, 3, stroke=0, fill=1)
    para(t, indent=16)


def code(lines):
    global y
    h = 14 * len(lines) + 14
    c.setFillColor(DARK)
    c.roundRect(MX, y - h + 12, W - 2 * MX, h, 6, stroke=0, fill=1)
    c.setFillColor(GREEN)
    c.setFont("M", 8)
    yy = y - 6
    for ln in lines:
        c.drawString(MX + 10, yy, ln)
        yy -= 14
    y -= h + 6


# رأس الصفحة
c.setFillColor(DARK)
c.roundRect(MX, y - 74, W - 2 * MX, 90, 8, stroke=0, fill=1)
c.setFillColor(GOLD)
c.rect(MX, y - 74, W - 2 * MX, 3, stroke=0, fill=1)
parts = (("online", white), ("4", GOLD), ("tech", white))
tw = sum(pdfmetrics.stringWidth(p, "B", 26) for p, _ in parts)
bx = W / 2 - (tw + 46) / 2
c.setFillColor(GOLD)
c.roundRect(bx, y - 22, 34, 34, 8, stroke=0, fill=1)
c.setFillColor(DARK)
c.setFont("B", 24)
c.drawCentredString(bx + 17, y - 14, "4")
xx = bx + 46
for ptxt, col in parts:
    c.setFillColor(col)
    c.setFont("B", 26)
    c.drawString(xx, y - 14, ptxt)
    xx += pdfmetrics.stringWidth(ptxt, "B", 26)
c.setFillColor(GOLD)
c.setFont("B", 13)
c.drawCentredString(W / 2, y - 42, "Online Web Control")
c.setFillColor(HexColor("#cfcfcf"))
c.setFont("R", 10)
c.drawCentredString(W / 2, y - 60, sh("لوحة تحكم ويب لرسيفر Enigma2 - بورت 7070"))
y -= 104

heading("التثبيت بأمر واحد")
para("افتح تيرمنال الرسيفر (Telnet / SSH) والصق الأمر. الرسيفر هيعمل ريستارت للواجهة بعد التثبيت:")
code(["wget -qO- https://raw.githubusercontent.com/online4tech/webcontrol1/main/install.sh | sh"])

heading("التثبيت بملف ipk")
step(1, "حمّل ملف الـ ipk من مجلد dist في الريبو.")
step(2, "انسخه إلى /tmp على الرسيفر.")
step(3, "نفّذ الأمرين:")
code(["opkg install /tmp/enigma2-plugin-extensions-onlinewebcontrol_all.ipk", "killall -9 enigma2"])

heading("تشغيل اللوحة")
step(1, "من قائمة البلجنات افتح Online Web Control.")
step(2, "هتلاقي الـ IP والبورت 7070 وحالة التشغيل.")
step(3, "اضغط الزر الأخضر لفتح اللوحة، والأحمر لقفلها (زر OK يبدّل بينهم).")
y -= 2
x = W - MX
for color, label in ((HexColor("#16a34a"), "أخضر: فتح"), (HexColor("#dc2626"), "أحمر: قفل")):
    w = pdfmetrics.stringWidth(sh(label), "B", 9) + 20
    c.setFillColor(color)
    c.roundRect(x - w, y - 5, w, 20, 4, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("B", 9)
    c.drawCentredString(x - w / 2, y + 1, sh(label))
    x -= w + 8
y -= 28

heading("فتح الصفحة")
para("من أي جهاز على نفس الشبكة افتح المتصفح على العنوان التالي:")
code(["http://IP-RECEIVER:7070"])
para("كل التحكم جوه الصفحة. اسم المستخدم وكلمة المرور الافتراضيان: admin / admin")

heading("أقسام الصفحة")
bullet("التحكم السريع: ريستارت الإيمو والواجهة والرسيفر وتحديث اللوحة.")
bullet("IPTV: تثبيت XStreamity و XKlass، لصق رابط M3U، بناء باقات Live / VOD / Series.")
bullet("الإيموهات والقنوات والبيكونات ودليل البرامج.")
bullet("CCcam: لصق السطر وحفظه في الملفات.")
bullet("تيرمنال مباشر وسجل العمليات.")

y -= 8
c.setFillColor(HexColor("#fff6d6"))
c.setStrokeColor(GOLD)
c.roundRect(MX, y - 38, W - 2 * MX, 52, 6, stroke=1, fill=1)
y -= 6
para("مهم: الصفحة فيها تيرمنال بصلاحيات root. غيّر AUTH_USER و AUTH_PASS في أول ملف online_web_control.py، ولا تفتح البورت 7070 على الإنترنت.", size=10, indent=10, gap=15)

c.setFillColor(HexColor("#777777"))
c.setFont("R", 9)
c.drawCentredString(W / 2, 28, "Powered by Online4Tech  |  github.com/online4tech/webcontrol1")
c.save()
