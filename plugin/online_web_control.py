#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Online Web Control - Online4Tech panel for Enigma2 receivers

import os
import re
import sys
import json
import base64
import shutil
import socket
import threading
import subprocess
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ==========================================================
# الإعدادات
# ==========================================================
PORT = int(os.environ.get("ONLINE_WEB_PORT", "7070"))

# لا توجد شاشة تسجيل دخول؛ اللوحة مخصصة للاستخدام داخل الشبكة المحلية فقط.
AUTH_USER = ""
AUTH_PASS = ""

# روابط الأزرار السفلية (حط روابطك هنا)
SUPPORT_URL = "#"
SITE_URL    = "#"
STORE_URL   = "#"

# رابط تحديث اللوحة (ملف السكربت نفسه) - اتركه فارغاً لتعطيل الزر
PANEL_UPDATE_URL = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/plugin/online_web_control.py"

# سكربتات تثبيت البلجنات. لو فاضية بيحاول opkg install
XSTREAMITY_URL = ""
XKLASS_URL     = ""
XSTREAMITY_PKG = "enigma2-plugin-extensions-xstreamity"
XKLASS_PKG     = "enigma2-plugin-extensions-xklass"

OSCAM_SCRIPT_URL = "https://raw.githubusercontent.com/KhaledAli65/emu/main/install_oscam.sh"
NCAM_SCRIPT_URL  = "https://raw.githubusercontent.com/KhaledAli65/emu/main/install_ncam.sh"

TOOLS_URLS = {
    "channels":  "https://github.com/KhaledAli65/Channels/releases/download/Toolscript/TOOL-Khaled_Channels_fullsat.sh",
    "picon_ext": "https://github.com/KhaledAli65/Channels/releases/download/Toolscript/TOOL-KhaledAli_picon_pro.sh",
    "picon_int": "https://github.com/KhaledAli65/Channels/releases/download/Toolscript/TOOL-KhaledSNP_internal.sh",
    "epg":       "https://github.com/KhaledAli65/Channels/releases/download/Toolscript/TOOL-KhaledEpg.sh",
}

PATH_CCCAM_ETC    = "/etc/CCcam.cfg"
PATH_CCCAM_TUXBOX = "/etc/tuxbox/config/CCcam.cfg"
PATH_NCAM_SERVER  = "/etc/tuxbox/config/ncam.server"
PATH_OSCAM_SERVER = "/etc/tuxbox/config/oscam.server"

ENIGMA_DIR = "/etc/enigma2"
IPTV_PLAYLISTS = ["/etc/enigma2/xstreamity/playlists.txt", "/etc/enigma2/xklass/playlists.txt"]

CURRENT_CWD = "/home/root" if os.path.exists("/home/root") else "/"
SELF_PATH = os.path.abspath(__file__)
# ==========================================================


def run(cmd, timeout=180, cwd=None):
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return p.stdout.decode("utf-8", "ignore").strip()
    except subprocess.TimeoutExpired:
        return "⚠️ انتهت المهلة (Timeout)."
    except Exception as e:
        return "❌ خطأ: %s" % e


def run_detached(cmd, delay=1):
    subprocess.Popen("sleep %d; %s" % (delay, cmd), shell=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def active_emu():
    names = (("oscam", "OSCam"), ("ncam", "NCam"), ("cccam", "CCcam"))
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open("/proc/%s/comm" % pid) as f:
                    comm = f.read().strip().lower()
            except Exception:
                continue
            for key, label in names:
                if key in comm:
                    return label
    except Exception:
        pass
    return None


def get_stats():
    st = {"ip": get_ip(), "port": PORT, "model": "Enigma2", "emu": active_emu()}
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k] = int(v.split()[0])
        total = mem["MemTotal"] / 1024.0
        avail = mem.get("MemAvailable", mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0)) / 1024.0
        used = total - avail
        st["ram_pct"] = int(round(used * 100 / total))
        st["ram_used"] = int(used)
        st["ram_total"] = int(total)
    except Exception:
        pass
    try:
        du = shutil.disk_usage("/")
        st["flash_pct"] = int(round(du.used * 100 / du.total))
        st["flash_free"] = "%.1fG" % (du.free / 1024.0 ** 3)
    except Exception:
        pass
    for p in ("/proc/stb/fp/temp_sensor", "/proc/stb/sensors/temp0/value",
              "/sys/class/thermal/thermal_zone0/temp"):
        try:
            with open(p) as f:
                t = int(f.read().strip().split()[0])
            if t > 1000:
                t //= 1000
            st["temp"] = t
            break
        except Exception:
            continue
    for p in ("/etc/hostname", "/proc/stb/info/model"):
        try:
            with open(p) as f:
                m = f.read().strip()
            if m:
                st["model"] = m
                break
        except Exception:
            continue
    return st


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>online4tech | Web Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 46 46'%3E%3Crect width='46' height='46' rx='11' fill='%23f5b800'/%3E%3Ctext x='23' y='34' text-anchor='middle' font-size='30' font-weight='800' font-family='Arial,sans-serif' fill='%23111'%3E4%3C/text%3E%3C/svg%3E">
<style>
  :root {
    --bg: #090806;
    --card: #12110e;
    --line: #272210;
    --gold: #f2c230;
    --gold-soft: rgba(242,194,48,.12);
    --gold-line: rgba(242,194,48,.32);
    --text: #f4f1e8;
    --muted: #a39d8a;
    --field: #0b0b0a;
  }
  html { background: #090806; }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Cairo', 'Segoe UI', Tahoma, Arial, sans-serif; }
  body { background: radial-gradient(circle at 50% -8%, #1d1807 0%, var(--bg) 52%); background-attachment: fixed; color: var(--text); min-height: 100vh; padding: 14px 12px 30px; }
  .wrap { width: min(100%, 1580px); margin: 0 auto; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .head, .stats, .foot { grid-column: 1 / -1; }
  .head { padding: 14px 18px; }
  .stats { margin: 0; gap: 12px; }
  .card { margin: 0; padding: 16px; min-width: 0; }
  .card-head { margin-bottom: 12px; padding-bottom: 10px; }
  .stack { gap: 9px; }
  .btn { padding: 11px 10px; font-size: .92rem; }
  .field { margin-bottom: 9px; }
  input, textarea { padding: 11px 10px; }
  .console { min-height: 110px; max-height: 260px; }
  @media (max-width: 1100px) {
    .wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .card { padding: 14px; }
  }
  @media (max-width: 640px) {
    body { padding: 8px 8px 18px; }
    .wrap { width: 100%; grid-template-columns: minmax(0, 1fr); gap: 10px; }
    .head, .stats, .foot { grid-column: 1; }
    .head { padding: 12px 10px; border-radius: 14px; }
    .wm { font-size: 1.55rem; }
    .head h1 { font-size: .9rem; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .stat { padding: 9px 10px; }
    .stat .k { font-size: .7rem; }
    .stat .v { font-size: .88rem; }
    .card { border-radius: 14px; padding: 12px; }
    .card-title { font-size: .98rem; }
    .badge { font-size: .62rem; padding: 4px 8px; }
    .btn { padding: 10px 9px; font-size: .88rem; border-radius: 11px; }
    .hint { font-size: .76rem; }
    .console { min-height: 90px; max-height: 220px; font-size: .76rem; }
    .row2 { gap: 8px; }
    .pill { font-size: .86rem; padding: 11px 12px; }
  }
  @media (min-width: 641px) and (max-width: 900px) {
    .wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  .head { text-align: center; background: #0c0b08; border: 1px solid var(--line); border-radius: 18px; padding: 16px 12px 14px; box-shadow: 0 8px 26px rgba(0,0,0,.45); }
  .logo { display: flex; align-items: center; justify-content: center; gap: 11px; direction: ltr; margin-bottom: 10px; }
  .logo svg { flex: none; }
  .wm { font-size: 1.9rem; font-weight: 800; letter-spacing: -.5px; color: var(--text); line-height: 1; }
  .wm b { color: var(--gold); }
  .head h1 { font-size: 1.05rem; color: var(--gold); font-weight: 700; line-height: 1.7; }

  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 14px 0 16px; }
  .stat { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; box-shadow: 0 6px 18px rgba(0,0,0,.35); }
  .stat .k { font-size: .76rem; color: var(--muted); display: flex; justify-content: space-between; gap: 6px; }
  .stat .v { white-space: nowrap; font-size: .95rem; font-weight: 800; margin-top: 6px; direction: ltr; text-align: right; color: var(--gold); }
  .stat .v.ok { color: #34d399; } .stat .v.warn { color: #fbbf24; } .stat .v.bad { color: #f4476b; }

  .card { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 18px 16px; margin-bottom: 16px; box-shadow: 0 8px 26px rgba(0,0,0,.4); }
  .card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }
  .card-title { font-size: 1.1rem; font-weight: 800; color: var(--gold); line-height: 1.6; }
  .badge { font-size: .68rem; font-weight: 700; color: var(--gold); border: 1px solid var(--gold-line); background: var(--gold-soft); border-radius: 20px; padding: 5px 12px; text-align: center; line-height: 1.35; white-space: nowrap; flex: none; direction: ltr; }

  .stack { display: flex; flex-direction: column; gap: 11px; }
  .btn { border: 0; border-radius: 14px; padding: 16px 12px; font-size: .98rem; font-weight: 700; color: #fff; cursor: pointer; width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; text-align: center; line-height: 1.5; box-shadow: 0 4px 14px rgba(0,0,0,.4); transition: filter .15s, transform .1s; }
  .btn:hover { filter: brightness(1.1); }
  .btn:active { transform: scale(.985); }
  .btn:disabled { opacity: .55; cursor: not-allowed; }
  .b-yellow { background: linear-gradient(135deg,#d9a92a,#f4cd4f); color: #1a1400; }
  .b-blue   { background: linear-gradient(135deg,#0a6fa8,#1593d6); }
  .b-red    { background: linear-gradient(135deg,#c20f33,#e8264d); }
  .b-green  { background: linear-gradient(135deg,#0d9468,#17b57d); }
  .b-teal   { background: linear-gradient(135deg,#0e8a7c,#14a691); }
  .b-indigo { background: linear-gradient(135deg,#3b38c4,#5b52e6); }
  .b-violet { background: linear-gradient(135deg,#6d28d9,#8b5cf6); }
  .b-sky    { background: linear-gradient(135deg,#0b7cc0,#1ea0e6); }
  .b-emerald{ background: linear-gradient(135deg,#0a8f5b,#10b06f); }
  .b-rose   { background: linear-gradient(135deg,#c2113a,#e5294f); }
  .b-amber  { background: linear-gradient(135deg,#d97706,#f59e0b); }
  .b-oscam  { background: linear-gradient(135deg,#1e40af,#2f63e0); }
  .b-ncam   { background: linear-gradient(135deg,#6d28d9,#8b5cf6); }
  .b-gray   { background: linear-gradient(135deg,#333335,#48484a); }

  .hint { font-size: .8rem; color: var(--muted); line-height: 1.7; margin: 2px 0 10px; }
  .field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
  .field label { font-size: .82rem; color: var(--text); font-weight: 600; }
  input, textarea { background: var(--field); border: 1px solid #1b1b19; border-radius: 10px; padding: 14px 12px; color: #fff; font-size: .9rem; direction: ltr; text-align: left; width: 100%; }
  input::placeholder, textarea::placeholder { color: #5a5850; }
  input:focus, textarea:focus { outline: 2px solid var(--gold); outline-offset: 0; border-color: var(--gold); }
  textarea { font-family: 'Courier New', monospace; min-height: 84px; resize: vertical; }
  .row2 { display: flex; gap: 11px; }
  .row2 .btn { flex: 1; }

  .console { background: #040404; border: 1px solid #161614; border-radius: 12px; padding: 14px; font-family: 'Courier New', monospace; font-size: .82rem; color: #9be3b9; min-height: 150px; max-height: 340px; overflow-y: auto; direction: ltr; text-align: left; white-space: pre-wrap; line-height: 1.55; }

  .foot { text-align: center; margin-top: 4px; }
  .pill { display: flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none; font-weight: 700; font-size: .95rem; border-radius: 999px; padding: 14px 16px; color: #fff; box-shadow: 0 4px 14px rgba(0,0,0,.4); }
  .pill b { color: var(--gold); }
  .pill-green { background: linear-gradient(135deg,#15803d,#22b455); margin-bottom: 11px; }
  .pill-green b { color: #fff; }
  .pill-dark { flex: 1; background: #171613; border: 1px solid var(--line); }
  .power { color: var(--muted); font-size: .76rem; margin-top: 14px; }
  .power b { color: var(--gold); }
  @media (prefers-reduced-motion: reduce) { .btn { transition: none; } }
</style>
</head>
<body>
<div class="wrap">

  <div class="head">
    <div class="logo" role="img" aria-label="online4tech">
      <svg width="46" height="46" viewBox="0 0 46 46" aria-hidden="true"><rect width="46" height="46" rx="11" fill="#f5b800"/><text x="23" y="34" text-anchor="middle" font-size="30" font-weight="800" font-family="Arial, sans-serif" fill="#111">4</text></svg>
      <span class="wm">online<b>4</b>tech</span>
    </div>
    <h1>لوحة التحكم المتكاملة لجهاز <span id="model">Enigma2</span> - Port %%PORT%%</h1>
  </div>

  <div class="stats">
    <div class="stat"><div class="k"><span>الإيمو النشط</span><span>⚡</span></div><div class="v" id="s_emu">...</div></div>
    <div class="stat"><div class="k"><span>الذاكرة (RAM)</span><span>🧠</span></div><div class="v" id="s_ram">...</div></div>
    <div class="stat"><div class="k"><span>المساحة (Flash)</span><span>💾</span></div><div class="v" id="s_flash">...</div></div>
    <div class="stat"><div class="k"><span>حرارة المعالج</span><span>🌡️</span></div><div class="v" id="s_temp">...</div></div>
  </div>

  <!-- التحكم السريع -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">⚙️ التحكم السريع بالرسيفر واللوحة</span>
      <span class="badge">تحكم<br>فوري</span>
    </div>
    <div class="stack">
      <button class="btn b-yellow" onclick="control('restart_emu','ريستارت الايمو',false)">🔄 ريستارت الايمو</button>
      <button class="btn b-blue"   onclick="control('restart_gui','ريستارت الواجهة',true)">🖥️ ريستارت الواجهة</button>
      <button class="btn b-red"    onclick="control('reboot','ريستارت الرسيفر',true)">⏻ ريستارت الرسيفر</button>
      <button class="btn b-green"  onclick="control('update_panel','تحديث اللوحة',true)">⬇️ تحديث اللوحة</button>
    </div>
  </div>

  <!-- IPTV -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">📺 إدارة اشتراك IPTV وبلجنات التشغيل</span>
      <span class="badge">Online4Tech<br>IPTV</span>
    </div>
    <div class="stack" style="margin-bottom:14px">
      <button class="btn b-indigo" onclick="installPlugin('xstreamity')">📦 تثبيت بلجن XStreamity</button>
      <button class="btn b-violet" onclick="installPlugin('xklass')">🎬 تثبيت بلجن XKlass</button>
    </div>
    <div class="hint">الصق رابط M3U كامل مباشرة (سيقوم بتعبئة الحقول تلقائياً) أو استخدم الرابط الكامل مباشرة.</div>
    <div class="field"><input type="text" id="m3u" placeholder="http://server.com:8080/get.php?username=...&password=..." oninput="parseM3U(this.value)"></div>
    <div class="field"><label>رابط السيرفر (Host URL)</label><input type="text" id="iptv_host" placeholder="http://server.com:8080"></div>
    <div class="field"><label>اسم المستخدم (Username)</label><input type="text" id="iptv_user" placeholder="username"></div>
    <div class="field"><label>كلمة المرور (Password)</label><input type="text" id="iptv_pass" placeholder="password"></div>
    <div class="stack">
      <button class="btn b-yellow" onclick="iptvBouquet()">📡 إضافة ملف القنوات Live / VOD / (Series)</button>
      <button class="btn b-teal"  onclick="iptvSave()">💾 حفظ الاشتراك في XStreamity و XKlass</button>
    </div>
  </div>

  <!-- الإيموهات -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">🚀 تثبيت الإيموهات (Emu) (Scripts)</span>
      <span class="badge">تثبيت<br>تلقائي</span>
    </div>
    <div class="stack">
      <button class="btn b-oscam" onclick="installEmu('oscam')">⚡ تثبيت إيمو OSCam</button>
      <button class="btn b-ncam"  onclick="installEmu('ncam')">🔥 تثبيت إيمو NCam</button>
    </div>
  </div>

  <!-- القنوات والبيكونات -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">📡 القنوات والبيكونات ودليل البرامج</span>
      <span class="badge">Online4Tech<br>Tools</span>
    </div>
    <div class="stack">
      <button class="btn b-sky"     onclick="runTool('channels','تحديث ملف القنوات')">📺 تحديث ملف القنوات</button>
      <button class="btn b-emerald" onclick="runTool('picon_ext','تحديث بيكونات خارجى')">💾 تحديث بيكونات خارجى</button>
      <button class="btn b-violet"  onclick="runTool('picon_int','تحديث بيكونات داخلى')">🖼️ تحديث بيكونات داخلى</button>
      <button class="btn b-rose"    onclick="runTool('epg','دليل البرامج الالكترونى')">🗓️ دليل البرامج الالكترونى</button>
    </div>
  </div>

  <!-- CCcam -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">🔑 بيانات اشتراك CCcam</span>
      <span class="badge">تعبئة<br>ذكية</span>
    </div>
    <div class="hint">لصق سطر السيسكام كاملاً (اختياري - سيقوم بتعبئة الحقول تلقائياً):</div>
    <div class="field"><input type="text" id="raw_cline" placeholder="C: server.example.com 12000 username password" oninput="parseCline(this.value)"></div>
    <div class="field"><label>الهوست (Host / Server)</label><input type="text" id="host" placeholder="example.ddns.net"></div>
    <div class="field"><label>البورت (Port)</label><input type="text" id="port" placeholder="12000"></div>
    <div class="field"><label>اسم المستخدم (User)</label><input type="text" id="user" placeholder="user123"></div>
    <div class="field"><label>كلمة المرور (Password)</label><input type="text" id="pass" placeholder="pass123"></div>
    <div class="stack">
      <button class="btn b-green"  onclick="saveSub('cccam_etc')">📄 حفظ في /etc/CCcam.cfg</button>
      <button class="btn b-teal"   onclick="saveSub('cccam_tuxbox')">📂 حفظ في /etc/tuxbox/config/CCcam.cfg</button>
      <button class="btn b-indigo" onclick="saveSub('ncam_server')">🟣 كتابة ريدر في ncam.server</button>
      <button class="btn b-amber"  onclick="saveSub('oscam_server')">🟠 كتابة ريدر في oscam.server</button>
    </div>
  </div>

  <!-- التيرمنال -->
  <div class="card">
    <div class="card-head">
      <span class="card-title">💻 تيرمنال الأوامر المباشر (Web Shell)</span>
      <span class="badge" id="cwd_badge">المسار:<br>/home/root</span>
    </div>
    <div class="hint">الصق أمراً واحداً أو عدة أوامر (Enter للتنفيذ السريع، أو Shift+Enter لسطر جديد):</div>
    <div class="field"><textarea id="cmd_input" placeholder="opkg update && ls -la /etc/tuxbox/config" onkeydown="handleCmdKey(event)"></textarea></div>
    <div class="row2">
      <button class="btn b-yellow" onclick="runShellCmd()">▶️ تنفيذ الأمر</button>
      <button class="btn b-gray" onclick="clearConsole()">🧹 مسح السجل</button>
    </div>
  </div>

  <!-- السجل -->
  <div class="card">
    <div class="card-head"><span class="card-title">🖥️ سجل العمليات (Console Output)</span></div>
    <div class="console" id="console">Ready... في انتظار تنفيذ الأوامر.</div>
  </div>

  <div class="foot">
    <a class="pill pill-green" href="%%SUPPORT%%" target="_blank" rel="noopener">💬 تواصل مع الدعم الفني - Online4Tech</a>
    <div class="row2">
      <a class="pill pill-dark" href="%%STORE%%" target="_blank" rel="noopener">🛒 متجر <b>Online4Tech</b></a>
      <a class="pill pill-dark" href="%%SITE%%" target="_blank" rel="noopener">🌐 الموقع الرسمي</a>
    </div>
    <div class="power">Powered by <b>Online4Tech</b> · أونلاين4تك للتكنولوجي</div>
  </div>
</div>

<script>
  const READY = 'Ready... في انتظار تنفيذ الأوامر.';
  const $ = id => document.getElementById(id);

  function log(msg, append) {
    const box = $('console');
    if (append && box.textContent && box.textContent !== READY) box.textContent += '\n' + msg;
    else box.textContent = msg;
    box.scrollTop = box.scrollHeight;
  }
  function clearConsole() { $('console').textContent = ''; }
  function setBusy(s) { document.querySelectorAll('button.btn').forEach(b => b.disabled = s); }

  async function api(path, body) {
    const res = await fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {}) });
    return await res.json();
  }

  async function call(path, body, waitMsg) {
    setBusy(true);
    log(waitMsg);
    try { const d = await api(path, body); log(d.output); return d; }
    catch (e) { log('❌ خطأ في الاتصال بالرسيفر: ' + e); }
    finally { setBusy(false); }
  }

  /* الإحصائيات */
  async function loadStats() {
    try {
      const s = await (await fetch('/api/stats')).json();
      if (s.emu) { $('s_emu').textContent = s.emu; $('s_emu').className = 'v ok'; }
      else { $('s_emu').textContent = 'متوقف'; $('s_emu').className = 'v bad'; }
      if (s.model) $('model').textContent = 'Enigma2';
      if (s.ram_pct !== undefined) {
        $('s_ram').textContent = s.ram_pct + '% (' + s.ram_used + '/' + s.ram_total + 'MB)';
        $('s_ram').className = 'v ' + (s.ram_pct > 90 ? 'bad' : s.ram_pct > 75 ? 'warn' : '');
      }
      if (s.flash_pct !== undefined) {
        $('s_flash').textContent = s.flash_pct + '% (' + s.flash_free + ' free)';
        $('s_flash').className = 'v ' + (s.flash_pct > 90 ? 'bad' : s.flash_pct > 75 ? 'warn' : '');
      }
      if (s.temp !== undefined) {
        $('s_temp').textContent = s.temp + '°C';
        $('s_temp').className = 'v ' + (s.temp > 75 ? 'bad' : s.temp > 60 ? 'warn' : '');
      } else { $('s_temp').textContent = '--'; }
    } catch (e) { $('s_emu').textContent = 'غير متصل'; $('s_emu').className = 'v bad'; }
  }
  loadStats(); setInterval(loadStats, 5000);

  /* التحكم السريع */
  async function control(action, label, confirmIt) {
    if (confirmIt && !confirm('تأكيد: ' + label + ' ؟')) return;
    await call('/api/control', { action }, '⏳ جاري تنفيذ: ' + label + ' ...');
  }

  /* IPTV */
  function parseM3U(v) {
    const m = v.trim().match(/^(https?:\/\/[^\/\s]+)\/.*[?&]username=([^&\s]+).*[?&]password=([^&\s]+)/i);
    if (m) { $('iptv_host').value = m[1]; $('iptv_user').value = decodeURIComponent(m[2]); $('iptv_pass').value = decodeURIComponent(m[3]); }
  }
  function iptvData() {
    const host = $('iptv_host').value.trim().replace(/\/+$/, ''), user = $('iptv_user').value.trim(), pass = $('iptv_pass').value.trim();
    if (!host || !user || !pass) { log('⚠️ تنبيه: املأ الرابط واسم المستخدم وكلمة المرور أولاً!'); return null; }
    return { host, user, pass };
  }
  function installPlugin(p) { call('/api/plugin', { plugin: p }, '⏳ جاري تثبيت بلجن ' + p + ' ...\nيرجى الانتظار...'); }
  function iptvSave() { const d = iptvData(); if (d) call('/api/iptv_save', d, '⏳ جاري حفظ الاشتراك...'); }
  function iptvBouquet() { const d = iptvData(); if (d) call('/api/iptv_bouquet', d, '⏳ جاري تحميل القائمة وبناء الباقات (Live / VOD / Series)...\nقد تستغرق دقيقة...'); }

  /* الإيمو والأدوات */
  function installEmu(t) { call('/api/install', { emu: t }, '⏳ جاري تحميل وتنفيذ سكربت تثبيت ' + t.toUpperCase() + ' ...\nيرجى الانتظار...'); }
  function runTool(k, l) { call('/api/tool', { tool: k, label: l }, '⏳ جاري تنفيذ (' + l + ') ...\nيرجى الانتظار...'); }

  /* CCcam */
  function parseCline(v) {
    const p = v.trim().replace(/^C:\s*/i, '').split(/\s+/);
    if (p.length >= 4) { $('host').value = p[0]; $('port').value = p[1]; $('user').value = p[2]; $('pass').value = p[3]; }
  }
  function saveSub(target) {
    const host = $('host').value.trim(), port = $('port').value.trim(), user = $('user').value.trim(), pass = $('pass').value.trim();
    if (!host || !port || !user || !pass) { log('⚠️ تنبيه: يرجى ملء جميع الحقول (Host, Port, User, Password) أولاً!'); return; }
    call('/api/save', { target, host, port, user, pass }, '⏳ جاري كتابة بيانات الاشتراك...');
  }

  /* التيرمنال */
  function handleCmdKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runShellCmd(); } }
  async function runShellCmd() {
    const box = $('cmd_input'), cmd = box.value.trim();
    if (!cmd) { log('⚠️ يرجى لصق أو كتابة أمر لتنفيذه.', true); return; }
    setBusy(true);
    log('$ ' + cmd + '\n⏳ جاري التنفيذ...', true);
    try {
      const d = await api('/api/exec', { cmd });
      if (d.cwd) $('cwd_badge').innerHTML = 'المسار:<br>' + d.cwd.replace(/</g, '&lt;');
      log(d.output, true);
      box.value = '';
    } catch (e) { log('❌ خطأ أثناء تنفيذ الأمر: ' + e, true); }
    setBusy(false);
  }
</script>
</body>
</html>
"""


def write_file(filepath, content, append=False):
    folder = os.path.dirname(filepath)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    mode = "a" if append and os.path.exists(filepath) else "w"
    with open(filepath, mode, encoding="utf-8") as f:
        f.write(content)


def do_control(action):
    if action == "restart_emu":
        out = run("""
if [ -x /etc/init.d/softcam ]; then /etc/init.d/softcam restart;
else
  found=0
  for f in /etc/init.d/softcam.*; do [ -x "$f" ] && "$f" restart && found=1; done
  if [ $found = 0 ]; then
    killall -9 oscam ncam CCcam 2>/dev/null; echo "تم إيقاف الإيمو - لم أجد سكربت تشغيل softcam"
  fi
fi""")
        return "✅ تم ريستارت الإيمو.\n" + out
    if action == "restart_gui":
        run_detached("(command -v systemctl >/dev/null 2>&1 && systemctl restart enigma2) || killall -9 enigma2", 1)
        return "✅ جاري ريستارت الواجهة... انتظر حوالي دقيقة."
    if action == "reboot":
        run_detached("reboot", 2)
        return "✅ جاري إعادة تشغيل الرسيفر... اللوحة هترجع بعد التشغيل."
    if action == "update_panel":
        return do_update_panel()
    return "❌ أمر غير معروف."


def do_update_panel():
    if not PANEL_UPDATE_URL:
        return "⚠️ لم يتم ضبط PANEL_UPDATE_URL في أعلى السكربت."
    try:
        req = urllib.request.Request(PANEL_UPDATE_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        compile(data, "online_web_control.py", "exec")
    except Exception as e:
        return "❌ فشل التحديث (الملف لم يُستبدل):\n%s" % e
    try:
        shutil.copy(SELF_PATH, SELF_PATH + ".bak")
        with open(SELF_PATH, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception as e:
        return "❌ تعذرت كتابة الملف:\n%s" % e
    threading.Timer(1.5, lambda: os.execv(sys.executable, [sys.executable, SELF_PATH])).start()
    return "✅ تم تحديث اللوحة وجاري إعادة تشغيلها... حدّث الصفحة بعد ثواني."


def do_plugin(name):
    url, pkg = (XSTREAMITY_URL, XSTREAMITY_PKG) if name == "xstreamity" else (XKLASS_URL, XKLASS_PKG)
    if url:
        out = run('wget -qO- "%s" | sh' % url, 240)
    else:
        out = run("opkg update && opkg install %s" % pkg, 240)
    return "✅ انتهت عملية تثبيت %s:\n\n%s\n\nأعد تشغيل الواجهة لظهور البلجن." % (name, out or "تم.")


def build_m3u_url(d):
    return "%s/get.php?username=%s&password=%s&type=m3u_plus&output=ts" % (
        d["host"], urllib.parse.quote(d["user"], safe=""), urllib.parse.quote(d["pass"], safe=""))


def do_iptv_save(d):
    url = build_m3u_url(d)
    line = "%s #Online4Tech" % url
    lines = []
    for path in IPTV_PLAYLISTS:
        try:
            existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if url in existing:
                lines.append("• موجود بالفعل: " + path)
                continue
            write_file(path, ("" if not existing or existing.endswith("\n") else "\n") + line + "\n", append=True)
            lines.append("✅ تم الحفظ في: " + path)
        except Exception as e:
            lines.append("❌ %s : %s" % (path, e))
    return "\n".join(lines) + "\n\nالرابط:\n" + url


def do_iptv_bouquet(d):
    url = build_m3u_url(d)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
    except Exception as e:
        return "❌ تعذر تحميل ملف M3U:\n%s" % e
    groups = {"live": [], "vod": [], "series": []}
    name = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            name = line.rsplit(",", 1)[-1].strip().replace(":", "-") or "Channel"
        elif line and not line.startswith("#") and name is not None:
            kind = "vod" if "/movie/" in line else "series" if "/series/" in line else "live"
            groups[kind].append((name, line))
            name = None
    if not any(groups.values()):
        return "⚠️ الملف لا يحتوي قنوات. تأكد من بيانات الاشتراك."
    titles = {"live": "Online4Tech Live", "vod": "Online4Tech VOD", "series": "Online4Tech Series"}
    bq_path = os.path.join(ENIGMA_DIR, "bouquets.tv")
    bq_text = open(bq_path, encoding="utf-8").read() if os.path.exists(bq_path) else "#NAME Bouquets (TV)\n"
    report = []
    for kind, items in groups.items():
        if not items:
            continue
        fname = "userbouquet.online4tech_%s.tv" % kind
        body = ["#NAME %s" % titles[kind]]
        for n, u in items:
            body.append("#SERVICE 4097:0:1:0:0:0:0:0:0:0:%s:%s" % (urllib.parse.quote(u, safe=""), n))
            body.append("#DESCRIPTION %s" % n)
        write_file(os.path.join(ENIGMA_DIR, fname), "\n".join(body) + "\n")
        entry = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % fname
        if fname not in bq_text:
            bq_text = bq_text.rstrip("\n") + "\n" + entry + "\n"
        report.append("✅ %s: %d" % (titles[kind], len(items)))
    write_file(bq_path, bq_text)
    run("wget -qO- 'http://127.0.0.1/web/servicelistreload?mode=2' >/dev/null 2>&1", 15)
    return "\n".join(report) + "\n\nتم إنشاء الباقات. لو لم تظهر اعمل ريستارت للواجهة."


def do_save(p):
    host, port, user, passwd, target = p.get("host"), p.get("port"), p.get("user"), p.get("pass"), p.get("target")
    cline = "C: %s %s %s %s\n" % (host, port, user, passwd)
    reader = (
        "\n[reader]\n"
        "label                         = CCcam_%s\n"
        "protocol                      = cccam\n"
        "device                        = %s,%s\n"
        "user                          = %s\n"
        "password                      = %s\n"
        "inactivitytimeout             = 30\n"
        "group                         = 1\n"
        "cccversion                    = 2.3.2\n"
        "ccckeepalive                  = 1\n"
        "audisabled                    = 1\n" % (host, host, port, user, passwd)
    )
    if target == "cccam_etc":
        write_file(PATH_CCCAM_ETC, cline)
        return "✅ تم حفظ السطر بنجاح في:\n%s\n\nالمحتوى:\n%s" % (PATH_CCCAM_ETC, cline)
    if target == "cccam_tuxbox":
        write_file(PATH_CCCAM_TUXBOX, cline)
        return "✅ تم حفظ السطر بنجاح في:\n%s\n\nالمحتوى:\n%s" % (PATH_CCCAM_TUXBOX, cline)
    if target == "ncam_server":
        write_file(PATH_NCAM_SERVER, reader, append=True)
        return "✅ تم إضافة الريدر بنجاح في:\n%s\n%s" % (PATH_NCAM_SERVER, reader)
    if target == "oscam_server":
        write_file(PATH_OSCAM_SERVER, reader, append=True)
        return "✅ تم إضافة الريدر بنجاح في:\n%s\n%s" % (PATH_OSCAM_SERVER, reader)
    return "❌ مسار غير معروف."


def do_exec(cmd):
    global CURRENT_CWD
    wrapped = "%s ; echo '___CWD___' ; pwd" % cmd
    cwd = CURRENT_CWD if os.path.isdir(CURRENT_CWD) else "/"
    raw = run(wrapped, 180, cwd=cwd)
    if "___CWD___" in raw:
        out, tail = raw.rsplit("___CWD___", 1)
        tail = tail.strip().splitlines()
        if tail and os.path.isdir(tail[-1].strip()):
            CURRENT_CWD = tail[-1].strip()
        raw = out.strip()
    return raw or "✅ تم تنفيذ الأمر (لا يوجد مخرج نصي)."


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth_ok(self):
        if not AUTH_PASS:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(h[6:]).decode("utf-8").partition(":")
                return user == AUTH_USER and pw == AUTH_PASS
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Online Web Control"')
        self.end_headers()
        return False

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if not self._auth_ok():
            return
        if self.path in ("/", "/index.html"):
            page = (HTML_PAGE.replace("%%PORT%%", str(PORT)).replace("%%SUPPORT%%", SUPPORT_URL)
                    .replace("%%SITE%%", SITE_URL).replace("%%STORE%%", STORE_URL))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        elif self.path == "/api/stats":
            self._json(get_stats())
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._auth_ok():
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            p = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            self._json({"output": "❌ بيانات غير صالحة"}, 400)
            return
        try:
            if self.path == "/api/control":
                out = do_control(p.get("action"))
            elif self.path == "/api/plugin":
                out = do_plugin(p.get("plugin"))
            elif self.path == "/api/iptv_save":
                out = do_iptv_save(p)
            elif self.path == "/api/iptv_bouquet":
                out = do_iptv_bouquet(p)
            elif self.path == "/api/install":
                emu = p.get("emu")
                url = OSCAM_SCRIPT_URL if emu == "oscam" else NCAM_SCRIPT_URL
                out = "✅ انتهى تثبيت %s:\n\n%s" % (str(emu).upper(), run('wget -qO- "%s" | sh' % url, 180) or "تم.")
            elif self.path == "/api/tool":
                url = TOOLS_URLS.get(p.get("tool"))
                if not url:
                    self._json({"output": "❌ أداة غير معروفة."}, 400)
                    return
                label = p.get("label") or p.get("tool")
                out = "✅ انتهى تنفيذ (%s):\n\n%s" % (label, run('wget -qO- "%s" | sh' % url, 240) or "تم.")
            elif self.path == "/api/save":
                out = do_save(p)
            elif self.path == "/api/exec":
                cmd = (p.get("cmd") or "").strip()
                if not cmd:
                    self._json({"output": "⚠️ الأمر فارغ.", "cwd": CURRENT_CWD})
                    return
                self._json({"output": do_exec(cmd), "cwd": CURRENT_CWD})
                return
            else:
                self.send_error(404)
                return
            self._json({"output": out})
        except Exception as e:
            self._json({"output": "❌ خطأ: %s" % e})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Online Web Control running on http://%s:%d" % (get_ip(), PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
