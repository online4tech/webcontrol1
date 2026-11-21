#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Online Web Control - Online4Tech panel for Enigma2 receivers

import os
import re
import sys
import json
import base64
import shutil
import tempfile
import time
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
SUPPORT_URL = "https://m.me/ahmad.m.romeh"
SITE_URL    = "https://online4tech.github.io/online4Tech/"
STORE_URL   = "https://sllr.co/online4tech"

# رابط تحديث اللوحة (ملف السكربت نفسه) - اتركه فارغاً لتعطيل الزر
PANEL_UPDATE_URL = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/plugin/online_web_control.py"
CATALOG_URL = "https://raw.githubusercontent.com/online4tech/Chanal-List/main/control-center/data/catalog.json"

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

CURRENT_CWD = "/home/root" if os.path.exists("/home/root") else "/"
SELF_PATH = os.path.abspath(__file__)

# صور اللوجو: تتحمّل مرة واحدة من GitHub وتتحفظ محلياً على الرسيفر لسرعة الفتح
BRAND_ASSETS_DIR = os.path.join(os.path.dirname(SELF_PATH), "assets")
BRAND_ASSETS = {
    "banner.png": "https://raw.githubusercontent.com/online4tech/webcontrol1/main/assets/o4t-main-logo.png",
    "icon.png":   "https://raw.githubusercontent.com/online4tech/webcontrol1/main/assets/o4t-icon.png",
}
# ==========================================================


def get_brand_asset(filename):
    url = BRAND_ASSETS.get(filename)
    if not url:
        return None
    # Use the PNGs bundled with the plugin first, so branding works offline.
    bundled_name = {
        "banner.png": "o4t-main-logo.png",
        "icon.png": "o4t-icon.png",
    }.get(filename, filename)
    local_path = os.path.join(BRAND_ASSETS_DIR, bundled_name)
    try:
        if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            with open(local_path, "rb") as f:
                return f.read()
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Online4Tech-WebControl"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read(5 * 1024 * 1024)
        if data:
            try:
                os.makedirs(BRAND_ASSETS_DIR, exist_ok=True)
                tmp_path = local_path + ".tmp"
                with open(tmp_path, "wb") as f:
                    f.write(data)
                os.replace(tmp_path, local_path)
            except Exception:
                pass
            return data
    except Exception:
        return None
    return None


def prefetch_brand_assets():
    for name in BRAND_ASSETS:
        get_brand_asset(name)


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
    st = {"ip": get_ip(), "port": PORT, "model": "Enigma2", "emu": active_emu(),
          "python": "%d.%d.%d" % sys.version_info[:3]}
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
<link rel="icon" type="image/png" sizes="128x128" href="/assets/icon.png">
<link rel="apple-touch-icon" href="/assets/icon.png">
<style>
  :root {
    --bg: #071321;
    --card: #101f30;
    --line: #24415a;
    --gold: #55d7ff;
    --gold-soft: rgba(85,215,255,.10);
    --gold-line: rgba(85,215,255,.30);
    --text: #f4f8fc;
    --muted: #a8bfd0;
    --field: #091827;
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
  .brand-banner-wrap { display: flex; justify-content: center; align-items: center; margin-bottom: 8px; }
  .brand-banner-img { display: block; width: min(420px, 88%); max-height: 115px; height: auto; object-fit: contain; filter: drop-shadow(0 6px 18px rgba(0,170,255,.22)); }
  @media (max-width: 640px) { .brand-banner-img { width: min(290px, 92%); max-height: 88px; } }
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

  .brand-tagline { color: #e4c65d; font-size: 1rem; font-weight: 800; letter-spacing: .4px; margin: -3px 0 8px; text-shadow: 0 0 18px rgba(228,198,93,.18); }
  .footer-title { color: #d9bd68; font-size: 1.12rem; font-weight: 800; margin: 0 0 12px; }
  .contact-links, .store-links { justify-content: center; gap: 12px; margin-bottom: 12px; }
  .contact-links .pill, .store-links .pill { flex: 1; min-width: 0; }
  .contact-links .pill { min-height: 58px; border: 1px solid rgba(255,255,255,.12); }
  .contact-links svg { width: 27px; height: 27px; flex: none; }
  .contact-whatsapp { background: linear-gradient(135deg,#087e50,#16a66b); }
  .contact-facebook { background: linear-gradient(135deg,#174d9c,#2878dc); }
  .contact-links span { display: flex; flex-direction: column; align-items: center; line-height: 1.45; }
  .contact-links b { color: #fff; font-size: .88rem; }
  @media (max-width: 640px) {
    .brand-tagline { font-size: .9rem; margin-bottom: 7px; }
    .contact-links, .store-links { gap: 8px; }
    .contact-links .pill { padding: 10px 7px; font-size: .82rem; }
    .contact-links svg { width: 23px; height: 23px; }
  }

  .foot { text-align: center; margin-top: 4px; }
  .pill { display: flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none; font-weight: 700; font-size: .95rem; border-radius: 999px; padding: 14px 16px; color: #fff; box-shadow: 0 4px 14px rgba(0,0,0,.4); }
  .pill b { color: var(--gold); }
  .pill-green { background: linear-gradient(135deg,#15803d,#22b455); margin-bottom: 11px; }
  .pill-green b { color: #fff; }
  .pill-dark { flex: 1; background: #171613; border: 1px solid var(--line); }
  .power { color: var(--muted); font-size: .76rem; margin-top: 14px; }
  .power b { color: var(--gold); }
  @media (prefers-reduced-motion: reduce) { .btn { transition: none; } }

  /* Online4Tech unified layout refresh */
  .wrap {
    width: min(100%, 1480px);
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    align-items: start;
  }
  .head, .stats, .foot { grid-column: 1 / -1; }
  .head {
    padding: 22px 24px;
    border-radius: 22px;
    border-color: rgba(242,194,48,.24);
    background: linear-gradient(135deg, #151b22 0%, #0c1117 70%);
  }
  .logo { margin-bottom: 12px; }
  .wm { letter-spacing: .2px; }
  .head h1 { color: #c7d1da; font-size: 1rem; }
  .stats {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin: 0;
  }
  .stat {
    min-width: 0;
    padding: 15px 17px;
    border-radius: 17px;
    background: linear-gradient(145deg, #17212a, #10171e);
    border-color: #263541;
  }
  .card {
    margin: 0;
    min-width: 0;
    padding: 20px;
    border-radius: 20px;
    border-color: #293844;
    background: linear-gradient(145deg, #151e26, #10171e);
    box-shadow: 0 10px 28px rgba(0,0,0,.28);
    overflow: hidden;
  }
  .card-head {
    min-height: 52px;
    margin-bottom: 17px;
    padding-bottom: 13px;
    border-color: #2a3945;
  }
  .card-title { color: #f0c84a; }
  .badge {
    color: #e8c65a;
    background: rgba(242,194,48,.08);
    border-color: rgba(242,194,48,.25);
  }
  .card .stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 11px;
  }
  .card .stack > .btn:only-child { grid-column: 1 / -1; }
  .btn { min-width: 0; padding: 12px 10px; border-radius: 12px; }
  .field { min-width: 0; }
  input, textarea { border-color: #2a3945; background: #0b1117; }
  .console-card { grid-column: 1 / -1; }
  .console {
    min-height: 130px;
    max-height: 260px;
    border-color: #273742;
    background: #080d12;
    border-radius: 14px;
  }
  .foot { margin-top: 2px; }
  .pill-dark { border-color: #2b3944; background: #141e27; }
  .power { color: #9aa8b4; }
  @media (max-width: 900px) {
    .wrap { gap: 13px; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .card { padding: 15px; }
  }
  @media (max-width: 640px) {
    body { padding: 9px 9px 20px; }
    .wrap { width: 100%; grid-template-columns: minmax(0, 1fr); gap: 11px; }
    .head, .stats, .foot, .console-card { grid-column: 1; }
    .head { padding: 17px 12px; }
    .wm { font-size: 1.65rem; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
    .stat { padding: 11px; }
    .card { padding: 14px; border-radius: 16px; }
    .card-head { min-height: 44px; margin-bottom: 13px; }
    .card-title { font-size: .98rem; }
    .card .stack { gap: 8px; }
    .btn { padding: 10px 8px; font-size: .84rem; }
    .console { min-height: 100px; max-height: 210px; }
    .row2 { gap: 8px; }
  }

  /* Online4Tech desktop: calm, full-width vertical layout */
  body {
    padding: 22px clamp(14px, 2.5vw, 38px) 34px;
    background: #0b1015;
    color: #e8edf2;
  }
  .wrap {
    width: 100%;
    max-width: 1500px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
    align-items: stretch;
  }
  .head, .stats, .foot, .card, .console-card, .quick-card {
    grid-column: 1 / -1;
    width: 100%;
    min-width: 0;
  }
  .head {
    padding: 25px 28px;
    background: #111a22;
    border: 1px solid #293744;
    border-radius: 18px;
    box-shadow: none;
  }
  .wm { font-size: 2rem; }
  .head h1 { color: #aebdca; font-size: 1rem; }
  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin: 0;
  }
  .stat {
    min-width: 0;
    padding: 16px 18px;
    background: #121c25;
    border: 1px solid #293744;
    border-radius: 14px;
    box-shadow: none;
  }
  .stat .k { color: #9eacb8; }
  .stat .v { color: #d9bd68; }
  .card {
    display: block;
    margin: 0;
    padding: 22px 24px;
    background: #121b23;
    border: 1px solid #2a3945;
    border-radius: 16px;
    box-shadow: none;
    overflow: visible;
  }
  .card-head {
    min-height: 0;
    margin-bottom: 18px;
    padding-bottom: 13px;
    border-bottom: 1px solid #2b3944;
  }
  .card-title { color: #d9bd68; font-size: 1.08rem; }
  .badge {
    color: #c8b778;
    background: #1b252d;
    border-color: #394653;
  }
  .card .stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .btn {
    min-width: 0;
    min-height: 46px;
    padding: 11px 14px;
    border-radius: 10px;
    background: #263744;
    color: #e8edf2;
    box-shadow: none;
    font-size: .92rem;
    font-weight: 700;
  }
  .btn:hover { filter: brightness(1.12); }
  .b-yellow, .b-amber { background: #79652e; color: #fff8df; }
  .b-blue, .b-sky, .b-indigo, .b-oscam { background: #294b63; color: #edf7ff; }
  .b-green, .b-emerald, .b-teal { background: #285b50; color: #edfff8; }
  .b-red, .b-rose { background: #70404a; color: #fff1f3; }
  .b-violet, .b-ncam { background: #4b4566; color: #f5f1ff; }
  .b-gray { background: #303b44; color: #e7edf2; }
  .hint { color: #a4b0ba; }
  .field label { color: #dce4ea; }
  input, textarea {
    color: #edf2f6;
    background: #0c1319;
    border: 1px solid #34434f;
    border-radius: 10px;
  }
  input:focus, textarea:focus {
    outline: 1px solid #b99b4b;
    border-color: #b99b4b;
  }
  .console {
    min-height: 150px;
    max-height: 320px;
    color: #b8d9c8;
    background: #090f14;
    border: 1px solid #2b3944;
    border-radius: 12px;
  }
  .foot { margin-top: 2px; }
  .pill {
    box-shadow: none;
    border-radius: 10px;
  }
  .pill-green { background: #285b50; }
  .pill-dark { background: #18232c; border: 1px solid #34434f; }
  .power { color: #8998a4; }
  @media (max-width: 900px) {
    body { padding: 14px 12px 24px; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .card { padding: 18px; }
  }
  @media (max-width: 640px) {
    body { padding: 9px 8px 18px; }
    .wrap { gap: 11px; }
    .head { padding: 16px 12px; }
    .wm { font-size: 1.55rem; }
    .head h1 { font-size: .84rem; }
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .stat { padding: 10px; }
    .card { padding: 13px; border-radius: 13px; }
    .card-head { margin-bottom: 13px; }
    .card .stack { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .btn { min-height: 42px; padding: 9px 7px; font-size: .82rem; }
    .row2 { gap: 8px; }
    .console { min-height: 100px; max-height: 220px; }
  }


  /* Online4Tech glass dashboard layout */
  body {
    padding: 22px clamp(14px, 2.4vw, 36px) 34px;
    background:
      radial-gradient(ellipse at 12% 0%, rgba(34,105,145,.17), transparent 34%),
      radial-gradient(ellipse at 88% 12%, rgba(180,145,65,.10), transparent 30%),
      #080e14;
    color: #edf3f8;
  }
  .wrap {
    width: 100%;
    max-width: 1640px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: minmax(0,1fr) minmax(0,1fr);
    grid-template-areas:
      "head head"
      "stats stats"
      "quick channels"
      "emu iptv"
      "cccam iptv"
      "terminal console"
      "foot foot";
    gap: 18px;
    align-items: stretch;
  }
  .head { grid-area: head; }
  .stats { grid-area: stats; }
  .head, .stats { grid-column: 1 / -1; }
  .head { background: rgba(17,28,38,.82); border: 1px solid rgba(126,166,190,.24); box-shadow: 0 12px 34px rgba(0,0,0,.25); }
  .stats { grid-template-columns: repeat(4,minmax(0,1fr)); gap: 13px; margin: 0; }
  .stat, .card {
    background: linear-gradient(145deg, rgba(25,42,55,.88), rgba(13,24,34,.92));
    border: 1px solid rgba(133,165,185,.22);
    box-shadow: 0 12px 30px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.035);
    backdrop-filter: blur(12px);
  }
  .stat { border-radius: 15px; }
  .card {
    min-width: 0;
    width: 100%;
    margin: 0;
    padding: 20px;
    border-radius: 18px;
    overflow: hidden;
  }
  .quick-card { grid-area: quick; }
  .channels-card { grid-area: channels; }
  .emu-card { grid-area: emu; }
  .iptv-card { grid-area: iptv; }
  .cccam-card { grid-area: cccam; }
  .terminal-card { grid-area: terminal; }
  .console-card { grid-area: console; }
  .foot { grid-area: foot; }
  .card-head {
    min-height: 0;
    margin-bottom: 15px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(142,171,190,.18);
  }
  .card-title { color: #e2c878; font-size: 1.04rem; }
  .badge {
    color: #d9c98f;
    background: rgba(208,177,91,.09);
    border: 1px solid rgba(208,177,91,.25);
  }
  .card .stack {
    display: grid;
    grid-template-columns: repeat(2,minmax(0,1fr));
    gap: 10px;
  }
  .quick-card .stack { max-width: 680px; margin: 0 auto; }
  .channels-card .stack { max-width: 720px; margin: 0 auto; }
  .btn {
    min-width: 0;
    min-height: 44px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,.12);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.17), 0 5px 14px rgba(0,0,0,.22);
    font-size: .9rem;
    font-weight: 700;
    transition: transform .16s ease, filter .16s ease, box-shadow .16s ease;
  }
  .btn:hover { filter: brightness(1.13); box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 7px 19px rgba(0,0,0,.3); }
  .btn:active { transform: translateY(1px); }
  .b-yellow, .b-amber { background: linear-gradient(135deg,#9b792f,#c5a64e); color: #fff9e8; }
  .b-blue, .b-sky, .b-indigo, .b-oscam { background: linear-gradient(135deg,#245878,#347da4); color: #f2faff; }
  .b-green, .b-emerald, .b-teal { background: linear-gradient(135deg,#216b5c,#32947b); color: #f0fff9; }
  .b-red, .b-rose { background: linear-gradient(135deg,#813e4b,#b45766); color: #fff4f5; }
  .b-violet, .b-ncam { background: linear-gradient(135deg,#514c79,#7770a7); color: #f8f6ff; }
  .b-gray { background: linear-gradient(135deg,#394954,#53616b); color: #f4f7f9; }
  .hint { color: #a9bac6; }
  .field label { color: #dce7ee; }
  input, textarea {
    color: #f1f6fa;
    background: rgba(5,13,20,.72);
    border: 1px solid rgba(135,166,187,.25);
    border-radius: 11px;
  }
  input:focus, textarea:focus { outline: 1px solid #bca45f; border-color: #bca45f; }
  .console {
    min-height: 280px;
    max-height: 420px;
    background: rgba(4,10,15,.82);
    border: 1px solid rgba(135,166,187,.22);
    border-radius: 13px;
    color: #b9dfcb;
  }
  .terminal-card, .console-card { height: 100%; }
  .terminal-card textarea { min-height: 190px; }
  .foot { margin-top: 0; }
  .pill { box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 6px 18px rgba(0,0,0,.2); }
  .pill-green { background: linear-gradient(135deg,#216b5c,#32947b); }
  .pill-dark { background: rgba(23,38,49,.92); border: 1px solid rgba(135,166,187,.22); }
  .power { color: #91a4b1; }
  @media (max-width: 980px) {
    body { padding: 14px 12px 24px; }
    .wrap {
      grid-template-columns: minmax(0,1fr);
      grid-template-areas:
        "head"
        "stats"
        "quick"
        "channels"
        "emu"
        "cccam"
        "iptv"
        "terminal"
        "console"
        "foot";
      gap: 13px;
    }
    .head, .stats { grid-column: 1; }
    .stats { grid-template-columns: repeat(2,minmax(0,1fr)); }
    .console { min-height: 180px; max-height: 300px; }
  }
  @media (max-width: 640px) {
    body { padding: 9px 8px 18px; }
    .wrap { gap: 10px; }
    .head { padding: 16px 12px; }
    .wm { font-size: 1.55rem; }
    .head h1 { font-size: .84rem; }
    .card { padding: 13px; border-radius: 14px; }
    .card-head { margin-bottom: 12px; }
    .card-title { font-size: .94rem; }
    .card .stack { gap: 8px; }
    .btn { min-height: 41px; padding: 9px 7px; font-size: .8rem; }
    .stat { padding: 10px; }
    .console { min-height: 140px; max-height: 230px; }
    .terminal-card textarea { min-height: 130px; }
    .row2 { gap: 8px; }
  }


  /* Compact subscription fields: keep paste/import fields full width */
  .compact-fields {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    align-items: end;
  }
  .compact-fields .field { min-width: 0; margin-bottom: 10px; gap: 4px; }
  .compact-fields .field label { font-size: .76rem; }
  .compact-fields input { min-width: 0; padding: 9px 10px; min-height: 40px; font-size: .84rem; }
  .cccam-fields { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  @media (max-width: 980px) {
    .cccam-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 640px) {
    .compact-fields, .cccam-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .compact-fields .field { margin-bottom: 7px; }
    .compact-fields input { padding: 8px; min-height: 38px; font-size: .8rem; }
  }

  .terminal-tools { display:flex; gap:9px; flex-wrap:wrap; margin: 0 0 11px; }
  .terminal-tools .btn { flex:1; min-width:150px; }
  .catalog-overlay[hidden] { display:none !important; }
  .catalog-overlay {
    position:fixed; inset:0; z-index:9999; display:flex; align-items:center; justify-content:center;
    padding:16px; background:rgba(2,8,13,.78); backdrop-filter:blur(8px);
  }
  .catalog-dialog {
    width:min(920px,100%); max-height:min(82vh,760px); display:flex; flex-direction:column;
    padding:18px; border:1px solid rgba(208,177,91,.34); border-radius:18px;
    background:linear-gradient(145deg,#17232d,#0d151c); box-shadow:0 24px 70px rgba(0,0,0,.55);
  }
  .catalog-dialog .card-head { margin-bottom:12px; }
  .catalog-toolbar { display:flex; gap:9px; align-items:center; margin-bottom:12px; }
  .catalog-toolbar input { flex:1; min-width:0; }
  .catalog-shortcuts { display:flex; flex-wrap:wrap; gap:7px; margin:0 0 12px; }
  .catalog-shortcuts .btn { flex:1; min-width:145px; min-height:38px; padding:7px 9px; font-size:.8rem; }
  .catalog-layout { display:grid; grid-template-columns:190px minmax(0,1fr); gap:12px; min-height:0; overflow:hidden; }
  .catalog-categories { display:flex; flex-direction:column; gap:7px; overflow:auto; max-height:52vh; }
  .catalog-category {
    border:1px solid rgba(135,166,187,.2); border-radius:10px; padding:9px 10px;
    color:#dce7ee; background:rgba(5,13,20,.55); text-align:right; cursor:pointer; font:inherit;
  }
  .catalog-category.active { border-color:rgba(208,177,91,.55); background:rgba(208,177,91,.13); color:#f0d98e; }
  .catalog-results { overflow:auto; max-height:52vh; display:flex; flex-direction:column; gap:8px; padding-inline-end:3px; }
  .catalog-item {
    border:1px solid rgba(135,166,187,.18); border-radius:11px; padding:10px 12px;
    background:rgba(5,13,20,.48); color:#e8edf2; text-align:right; cursor:pointer;
  }
  .catalog-item:hover { border-color:rgba(208,177,91,.55); background:rgba(208,177,91,.08); }
  .catalog-item b { display:block; color:#e6ce83; margin-bottom:3px; }
  .catalog-item small { display:block; color:#a9bac6; line-height:1.55; }
  .catalog-note { color:#d5bd78; font-size:.78rem; line-height:1.65; margin-top:10px; }
  .catalog-empty { color:#a9bac6; padding:18px 10px; text-align:center; }
  @media (max-width:640px) {
    .catalog-dialog { padding:12px; max-height:88vh; }
    .catalog-shortcuts .btn { min-width:calc(50% - 7px); font-size:.74rem; }
    .catalog-layout { grid-template-columns:1fr; grid-template-rows:auto minmax(180px,1fr); }
    .catalog-categories { flex-direction:row; max-height:none; overflow-x:auto; padding-bottom:5px; }
    .catalog-category { white-space:nowrap; }
    .catalog-results { max-height:42vh; }
    .catalog-toolbar { flex-wrap:wrap; }
    .catalog-toolbar input { flex-basis:100%; }
  }

  /* Online4Tech official brand palette and supplied logo assets */
  :root { --bg:#071321; --card:#101f30; --line:#24415a; --gold:#55d7ff; --gold-soft:rgba(85,215,255,.10); --gold-line:rgba(85,215,255,.30); --text:#f4f8fc; --muted:#a8bfd0; --field:#091827; }
  html, body { background:#071321 !important; color:#f4f8fc; }
  body { background:radial-gradient(circle at 50% -10%, #153b58 0%, #071321 58%) !important; }
  .head { background:linear-gradient(135deg,#102b43,#081827) !important; border-color:#2c5b79 !important; }
  .brand-banner-wrap { margin:0 auto 8px; }
  .brand-banner-img { width:min(460px,92%); max-height:132px; object-fit:contain; filter:drop-shadow(0 8px 22px rgba(0,189,242,.20)); }
  .head h1, .card-title, .stat .v, .badge, .power b, .pill b { color:#55d7ff !important; }
  .card, .stat { background:linear-gradient(145deg,#12263a,#0d1b2a) !important; border-color:#29465e !important; }
  .card-head { border-color:#29465e !important; }
  .badge { background:rgba(85,215,255,.09) !important; border-color:rgba(85,215,255,.32) !important; }
  input, textarea { background:#081725 !important; border-color:#29465e !important; }
  input:focus, textarea:focus { outline-color:#55d7ff !important; border-color:#55d7ff !important; }
  .console { background:#050e17 !important; border-color:#29465e !important; }
  .pill-dark { background:#102337 !important; border-color:#29465e !important; }
  .brand-tagline, .footer-title { color:#55d7ff !important; }
  @media(max-width:640px) { .brand-banner-img { width:min(330px,94%); max-height:96px; } }
  /* Online4Tech header: preserve the complete original logo without clipping. */
  .head { background:#081A31 !important; padding:18px 16px 16px !important; overflow:visible !important; }
  .brand-banner-wrap { width:100%; min-height:0; margin:0 auto 10px !important; padding:0 8px; overflow:visible !important; }
  .brand-banner-img { width:min(560px,96%) !important; max-width:100% !important; max-height:none !important; height:auto !important; object-fit:contain !important; object-position:center center !important; }
  @media(max-width:640px) {
    .head { padding:14px 8px !important; }
    .brand-banner-img { width:min(420px,98%) !important; max-height:none !important; }
  }

  /* Online4Tech desktop compact density pass — preserve existing grid and visual identity */
  @media (min-width: 981px) {
    html { font-size: 14px; }
    body { padding: 10px clamp(12px, 1.5vw, 24px) 18px !important; }
    .wrap {
      max-width: 1480px !important;
      gap: 11px !important;
      grid-template-columns: minmax(0,1fr) minmax(0,1fr) !important;
      align-items: start !important;
    }
    .head { padding: 10px 16px 9px !important; border-radius: 15px !important; }
    .brand-banner-wrap { margin-bottom: 3px !important; }
    .brand-banner-img { width: min(390px, 78%) !important; max-height: 76px !important; }
    .head h1 { font-size: .88rem !important; line-height: 1.35 !important; }
    .stats { gap: 9px !important; }
    .stat { padding: 8px 12px !important; border-radius: 12px !important; }
    .stat .k { font-size: .70rem !important; }
    .stat .v { font-size: .88rem !important; margin-top: 3px !important; }
    .card { padding: 12px 14px !important; border-radius: 14px !important; }
    .card-head { margin-bottom: 9px !important; padding-bottom: 7px !important; }
    .card-title { font-size: .96rem !important; line-height: 1.4 !important; }
    .badge { padding: 3px 8px !important; font-size: .62rem !important; }
    .card .stack { gap: 7px !important; }
    .btn { min-height: 36px !important; padding: 7px 9px !important; font-size: .82rem !important; line-height: 1.35 !important; border-radius: 9px !important; }
    .hint { font-size: .72rem !important; line-height: 1.45 !important; margin: 1px 0 6px !important; }
    .field { gap: 3px !important; margin-bottom: 7px !important; }
    .field label { font-size: .74rem !important; }
    input, textarea { padding: 8px 9px !important; font-size: .82rem !important; border-radius: 8px !important; }
    .compact-fields { gap: 7px !important; }
    .compact-fields .field { margin-bottom: 6px !important; }
    .compact-fields input { min-height: 34px !important; padding: 6px 8px !important; }
    .row2 { gap: 7px !important; }
    .terminal-tools { gap: 7px !important; margin-bottom: 7px !important; }
    .terminal-tools .btn { min-width: 110px !important; }
    .terminal-card textarea { min-height: 112px !important; }
    .console { min-height: 112px !important; max-height: 190px !important; padding: 9px 11px !important; font-size: .74rem !important; line-height: 1.4 !important; }
    .foot { margin-top: 0 !important; }
    .pill { padding: 9px 12px !important; font-size: .84rem !important; }
    .power { font-size: .68rem !important; margin-top: 8px !important; }
    .footer-title { font-size: .96rem !important; margin-bottom: 7px !important; }
    .contact-links, .store-links { gap: 8px !important; margin-bottom: 7px !important; }
    .contact-links .pill { min-height: 42px !important; }
    .contact-links svg { width: 21px !important; height: 21px !important; }
  }
  @media (min-width: 641px) and (max-width: 980px) {
    body { padding: 12px 12px 20px !important; }
    .wrap { gap: 12px !important; }
    .head { padding: 14px 16px !important; }
    .brand-banner-img { width: min(430px, 88%) !important; max-height: 100px !important; }
    .card { padding: 14px !important; }
    .card-head { margin-bottom: 11px !important; padding-bottom: 8px !important; }
    .btn { min-height: 40px !important; padding: 8px 9px !important; font-size: .86rem !important; }
    .console { min-height: 140px !important; max-height: 240px !important; }
  }

  /* ==========================================================
     Online4Tech Landing Layout — full-screen responsive refresh
     Visual-only overrides: preserve markup, IDs, handlers and API.
     ========================================================== */
  :root {
    --o4t-navy: #071426;
    --o4t-panel: #10243a;
    --o4t-panel-2: #142d47;
    --o4t-line: rgba(117, 183, 224, .22);
    --o4t-cyan: #55d7ff;
    --o4t-blue: #168bd0;
    --o4t-white: #f4f9ff;
    --o4t-muted: #a9bfd2;
    --gold: var(--o4t-cyan);
  }
  html, body { min-height:100%; background:var(--o4t-navy) !important; }
  body {
    padding:clamp(12px,1.35vw,24px) !important;
    background:
      radial-gradient(ellipse at 12% 0%, rgba(20,126,183,.24), transparent 34%),
      radial-gradient(ellipse at 90% 14%, rgba(18,76,128,.2), transparent 30%),
      linear-gradient(145deg,#071426 0%,#091a2c 52%,#071321 100%) !important;
  }
  .wrap {
    width:100% !important;
    max-width:1920px !important;
    min-height:calc(100vh - 36px);
    margin:0 auto !important;
    display:grid !important;
    grid-template-columns:repeat(12,minmax(0,1fr)) !important;
    grid-auto-flow:row dense;
    gap:clamp(12px,1.15vw,20px) !important;
    align-content:start;
    align-items:stretch !important;
  }
  .head, .stats, .foot { grid-column:1 / -1 !important; }
  .head {
    min-height:clamp(170px,18vh,230px);
    display:grid !important;
    grid-template-columns:minmax(0,1.1fr) minmax(320px,.9fr);
    align-items:center;
    gap:24px;
    text-align:right !important;
    padding:clamp(22px,3vw,42px) clamp(22px,3.2vw,52px) !important;
    border:1px solid rgba(85,215,255,.26) !important;
    border-radius:26px !important;
    background:
      radial-gradient(circle at 14% 50%,rgba(18,151,209,.16),transparent 32%),
      linear-gradient(112deg,#102b46 0%,#0b1e33 54%,#0a192b 100%) !important;
    box-shadow:0 18px 48px rgba(0,0,0,.28), inset 0 1px rgba(255,255,255,.04);
    position:relative;
    overflow:hidden !important;
  }
  .head:before {
    content:"";
    position:absolute;
    width:340px;height:340px;
    border:1px solid rgba(85,215,255,.09);
    border-radius:50%;
    inset-inline-start:-110px;top:-180px;
    box-shadow:0 0 0 32px rgba(85,215,255,.025),0 0 0 68px rgba(85,215,255,.018);
    pointer-events:none;
  }
  .brand-banner-wrap {
    grid-column:1;grid-row:1;
    width:100%;min-height:0;
    justify-content:flex-start !important;
    margin:0 !important;padding:0 !important;
    position:relative;z-index:1;
  }
  .brand-banner-img {
    width:min(100%,620px) !important;
    max-width:100% !important;
    max-height:150px !important;
    height:auto !important;
    object-fit:contain !important;
    object-position:right center !important;
    filter:drop-shadow(0 10px 26px rgba(0,174,239,.22));
  }
  #o4t_fallback_logo { grid-column:1;grid-row:1; }
  .head h1 {
    grid-column:2;grid-row:1;
    align-self:center;
    margin:0 !important;
    max-width:620px;
    color:var(--o4t-white) !important;
    font-size:clamp(1.2rem,2vw,2rem) !important;
    font-weight:800 !important;
    line-height:1.7 !important;
    text-align:right;
    position:relative;z-index:1;
  }
  .head h1:after {
    content:"إدارة ومتابعة وتحكم كامل في خدمات الرسيفر من لوحة واحدة";
    display:block;
    margin-top:8px;
    max-width:540px;
    color:#a9c5da;
    font-size:clamp(.82rem,1vw,1rem);
    font-weight:500;
    line-height:1.8;
  }
  .stats {
    display:grid !important;
    grid-template-columns:repeat(4,minmax(0,1fr)) !important;
    gap:clamp(10px,1vw,16px) !important;
    margin:0 !important;
  }
  .stat {
    min-height:94px;
    display:flex;flex-direction:column;justify-content:center;
    padding:16px 20px !important;
    border-radius:18px !important;
    border:1px solid var(--o4t-line) !important;
    background:linear-gradient(145deg,rgba(20,48,74,.96),rgba(12,31,50,.96)) !important;
    box-shadow:0 10px 26px rgba(0,0,0,.2),inset 0 1px rgba(255,255,255,.035);
  }
  .stat .k {font-size:.82rem !important;color:#b8cddd !important}
  .stat .v {font-size:clamp(1rem,1.35vw,1.35rem) !important;color:var(--o4t-cyan) !important}
  .card {
    grid-column:span 4;
    min-width:0;
    height:100%;
    padding:clamp(17px,1.55vw,25px) !important;
    border:1px solid var(--o4t-line) !important;
    border-radius:21px !important;
    background:linear-gradient(145deg,rgba(19,43,66,.97),rgba(11,28,46,.98)) !important;
    box-shadow:0 12px 32px rgba(0,0,0,.22),inset 0 1px rgba(255,255,255,.035) !important;
    transition:border-color .18s ease,transform .18s ease,box-shadow .18s ease;
  }
  .card:hover {
    border-color:rgba(85,215,255,.42) !important;
    box-shadow:0 16px 36px rgba(0,0,0,.27),0 0 22px rgba(25,151,207,.055) !important;
  }
  .quick-card {grid-column:span 4}
  .iptv-card {grid-column:span 8}
  .emu-card,.channels-card,.cccam-card {grid-column:span 4}
  .terminal-card {grid-column:span 8}
  .console-card {grid-column:span 4}
  .card-head {
    min-height:48px;
    margin-bottom:16px !important;
    padding-bottom:12px !important;
    border-color:rgba(117,183,224,.19) !important;
  }
  .card-title {font-size:clamp(1rem,1.15vw,1.18rem) !important;color:#8fe2ff !important}
  .badge {
    color:#8fe2ff !important;
    background:rgba(45,166,220,.1) !important;
    border-color:rgba(85,215,255,.28) !important;
    padding:6px 11px !important;
  }
  .card .stack {gap:10px !important}
  .btn {
    min-height:44px;
    padding:10px 13px !important;
    border:1px solid rgba(255,255,255,.055) !important;
    border-radius:12px !important;
    font-size:.9rem !important;
    box-shadow:0 5px 14px rgba(0,0,0,.18) !important;
  }
  .btn:hover {filter:brightness(1.12);transform:translateY(-1px)}
  .field label,.hint {color:#b0c5d6 !important}
  input,textarea {
    border:1px solid rgba(117,183,224,.22) !important;
    border-radius:11px !important;
    background:#08192a !important;
    color:#f5faff !important;
  }
  input:focus,textarea:focus {outline:2px solid rgba(85,215,255,.5) !important}
  .console {
    min-height:190px !important;max-height:340px !important;
    padding:16px !important;
    border:1px solid rgba(85,215,255,.18) !important;
    border-radius:14px !important;
    background:#06111d !important;
  }
  .foot {
    padding:24px clamp(14px,2vw,28px) 12px;
    margin:0 !important;
    border:1px solid rgba(117,183,224,.15);
    border-radius:20px;
    background:linear-gradient(120deg,rgba(16,39,61,.8),rgba(9,26,43,.82));
  }
  .footer-title {color:#8fe2ff !important}
  .pill-dark {background:#102a43 !important;border-color:rgba(117,183,224,.2) !important}
  .power {color:#a9bfd2 !important}
  @media (min-width:1500px) {
    .wrap {gap:20px !important}
    .card {padding:25px 27px !important}
    .btn {min-height:48px;font-size:.96rem !important}
    .console {min-height:230px !important}
  }
  @media (min-width:641px) and (max-width:1100px) {
    .wrap {grid-template-columns:repeat(2,minmax(0,1fr)) !important}
    .head,.stats,.foot {grid-column:1 / -1 !important}
    .head {grid-template-columns:1fr;min-height:0;gap:12px;text-align:center !important}
    .brand-banner-wrap {justify-content:center !important}
    .brand-banner-img {width:min(520px,88%) !important;object-position:center !important}
    .head h1 {grid-column:1;grid-row:auto;text-align:center;max-width:none}
    .head h1:after {margin-inline:auto}
    .stats {grid-template-columns:repeat(4,minmax(0,1fr)) !important}
    .quick-card,.iptv-card,.emu-card,.channels-card,.cccam-card,.terminal-card,.console-card {grid-column:span 1}
    .iptv-card,.terminal-card {grid-column:1 / -1}
  }
  @media (max-width:640px) {
    body {padding:9px !important}
    .wrap {width:100% !important;min-height:0;grid-template-columns:minmax(0,1fr) !important;gap:11px !important}
    .head,.stats,.foot,.card {grid-column:1 !important}
    .head {display:flex !important;flex-direction:column;gap:8px;min-height:0;padding:17px 12px !important;text-align:center !important}
    .brand-banner-wrap {justify-content:center !important}
    .brand-banner-img {width:min(100%,390px) !important;max-height:100px !important;object-position:center !important}
    .head h1 {font-size:1rem !important;text-align:center;line-height:1.5 !important}
    .head h1:after {font-size:.78rem;margin:5px auto 0}
    .stats {grid-template-columns:repeat(2,minmax(0,1fr)) !important;gap:8px !important}
    .stat {min-height:76px;padding:10px 12px !important}
    .stat .k {font-size:.68rem !important}
    .stat .v {font-size:.82rem !important;white-space:normal}
    .card {padding:14px !important;border-radius:16px !important}
    .card-head {min-height:40px;margin-bottom:12px !important;padding-bottom:9px !important}
    .card-title {font-size:.92rem !important}
    .card .stack {gap:8px !important}
    .btn {min-height:42px;padding:9px 8px !important;font-size:.82rem !important}
    .console {min-height:130px !important;max-height:230px !important}
    .foot {padding:18px 10px 10px}
  }
  @media (prefers-reduced-motion:reduce) {
    .card,.btn {transition:none !important}
  }

</style>
</head>
<body>
<div class="wrap">

  <div class="head">
    <div class="brand-banner-wrap">
      <img class="brand-banner-img" src="/assets/banner.png" alt="Online4Tech — خليك دايما اونلاين" onerror="this.style.display='none';document.getElementById('o4t_fallback_logo').style.display='block';">
    </div>
    <div id="o4t_fallback_logo" style="display:none">
      <div class="logo" role="img" aria-label="Online4Tech">
        <span class="wm">online<b>4</b>tech</span>
      </div>
      <div class="brand-tagline">خليك دايما اونلاين</div>
    </div>
    <h1>ONLINE TECHNOLOGY · لوحة التحكم المتكاملة</h1>
  </div>

  <div class="stats">
    <div class="stat"><div class="k"><span>الإيمو النشط</span><span>⚡</span></div><div class="v" id="s_emu">...</div></div>
    <div class="stat"><div class="k"><span>الذاكرة (RAM)</span><span>🧠</span></div><div class="v" id="s_ram">...</div></div>
    <div class="stat"><div class="k"><span>المساحة (Flash)</span><span>💾</span></div><div class="v" id="s_flash">...</div></div>
    <div class="stat"><div class="k"><span>حرارة المعالج</span><span>🌡️</span></div><div class="v" id="s_temp">...</div></div>
  </div>

  <!-- التحكم السريع -->
  <div class="card quick-card">
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
  <div class="card iptv-card">
    <div class="card-head">
      <span class="card-title">📺 إدارة اشتراك IPTV وبلجنات التشغيل</span>
      <span class="badge">Online4Tech<br>IPTV</span>
    </div>
    <div class="stack" style="margin-bottom:14px">
      <button class="btn b-indigo" onclick="installPlugin('xstreamity')">📦 تثبيت بلجن XStreamity</button>
      <button class="btn b-violet" onclick="installPlugin('xklass')">🎬 تثبيت بلجن XKlass</button>
      <button class="btn b-emerald" onclick="installPlugin('ajpanel')">🧰 تثبيت بلجن AJPanel</button>
      <button class="btn b-sky" onclick="installPlugin('jedimakerxtream')">🚀 تثبيت بلجن JediMakerXtream</button>
    </div>
    <div class="hint">الصق رابط M3U كامل مباشرة (سيقوم بتعبئة الحقول تلقائياً) أو استخدم الرابط الكامل مباشرة.</div>
    <div class="field"><input type="text" id="m3u" placeholder="http://server.com:8080/get.php?username=...&password=..." oninput="parseM3U(this.value)"></div>
    <div class="compact-fields iptv-fields">
      <div class="field"><label>رابط السيرفر (Host URL)</label><input type="text" id="iptv_host" placeholder="http://server.com:8080"></div>
      <div class="field"><label>اسم المستخدم (Username)</label><input type="text" id="iptv_user" placeholder="username"></div>
      <div class="field"><label>كلمة المرور (Password)</label><input type="text" id="iptv_pass" placeholder="password"></div>
    </div>
    <div class="stack">
      <button class="btn b-yellow" onclick="iptvBouquet()">📡 إضافة ملف القنوات Live / VOD / (Series)</button>
      <button class="btn b-teal"  onclick="iptvSave()">💾 حفظ الاشتراك في الإضافات المكتشفة</button>
    </div>
  </div>

  <!-- الإيموهات -->
  <div class="card emu-card">
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
  <div class="card channels-card">
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
  <div class="card cccam-card">
    <div class="card-head">
      <span class="card-title">🔑 إضافة سيرفر CCcam / Reader</span>
      <span class="badge">تعبئة<br>ذكية</span>
    </div>
    <div class="hint">لصق سطر السيسكام كاملاً (اختياري - سيقوم بتعبئة الحقول تلقائياً):</div>
    <div class="field"><input type="text" id="raw_cline" placeholder="C: server.example.com 12000 username password" oninput="parseCline(this.value)"></div>
    <div class="compact-fields cccam-fields">
      <div class="field"><label>الهوست (Host / Server)</label><input type="text" id="host" placeholder="example.ddns.net"></div>
      <div class="field"><label>البورت (Port)</label><input type="text" id="port" placeholder="12000"></div>
      <div class="field"><label>اسم المستخدم (User)</label><input type="text" id="user" placeholder="user123"></div>
      <div class="field"><label>كلمة المرور (Password)</label><input type="text" id="pass" placeholder="pass123"></div>
    </div>
    <div class="stack">
      <button class="btn b-green"  onclick="saveSub('cccam_etc')">📄 حفظ في /etc/CCcam.cfg</button>
      <button class="btn b-teal"   onclick="saveSub('cccam_tuxbox')">📂 حفظ في /etc/tuxbox/config/CCcam.cfg</button>
      <button class="btn b-indigo" onclick="saveSub('ncam_server')">🟣 كتابة ريدر في ncam.server</button>
      <button class="btn b-amber"  onclick="saveSub('oscam_server')">🟠 كتابة ريدر في oscam.server</button>
    </div>
  </div>

  <!-- التيرمنال -->
  <div class="card terminal-card">
    <div class="card-head">
      <span class="card-title">💻 تيرمنال الأوامر المباشر (Web Shell)</span>
      <span class="badge" id="cwd_badge">المسار:<br>/home/root</span>
    </div>
    <div class="hint">الصق أمراً واحداً أو عدة أوامر (Enter للتنفيذ السريع، أو Shift+Enter لسطر جديد):</div>
    <div class="terminal-tools">
      <button class="btn b-violet" type="button" onclick="openCommandLibrary()">📚 مكتبة الأوامر</button>
      <button class="btn b-gray" type="button" onclick="refreshCommandLibrary()">🔄 تحديث المكتبة</button>
    </div>
    <div class="field"><textarea id="cmd_input" placeholder="opkg update && ls -la /etc/tuxbox/config" onkeydown="handleCmdKey(event)"></textarea></div>
    <div class="row2">
      <button class="btn b-yellow" onclick="runShellCmd()">▶️ تنفيذ الأمر</button>
      <button class="btn b-gray" onclick="clearConsole()">🧹 مسح السجل</button>
    </div>
  </div>

  <!-- السجل -->
  <div class="card console-card">
    <div class="card-head"><span class="card-title">🖥️ سجل العمليات (Console Output)</span></div>
    <div class="console" id="console">Ready... في انتظار تنفيذ الأوامر.</div>
  </div>

  <div class="catalog-overlay" id="catalog_modal" hidden onclick="if(event.target===this)closeCommandLibrary()">
    <section class="catalog-dialog" role="dialog" aria-modal="true" aria-labelledby="catalog_title">
      <div class="card-head">
        <span class="card-title" id="catalog_title">📚 مكتبة أوامر Online4Tech</span>
        <button class="btn b-gray" type="button" style="width:auto;min-width:42px" onclick="closeCommandLibrary()">✕</button>
      </div>
      <div class="catalog-toolbar">
        <input id="catalog_search" type="search" placeholder="ابحث عن بلجن أو سكين أو قمر..." oninput="renderCommandLibrary()">
        <button class="btn b-gray" type="button" style="width:auto" onclick="refreshCommandLibrary()">↻ تحديث المكتبة</button>
      </div>
      <div class="catalog-shortcuts">
        <button class="btn b-blue" type="button" onclick="refreshAndSelectCatalog('picons')">🛰️ تحديث صور القنوات</button>
        <button class="btn b-teal" type="button" onclick="showMissingLibraries()">📚 المكتبات الناقصة</button>
        <button class="btn b-gray" type="button" onclick="showPackageIndexes()">🔄 تحديث فهارس الحزم</button>
        <button class="btn b-amber" type="button" onclick="refreshAndSelectCatalog('images')">🖼️ تحديث قائمة صور الأنظمة</button>
        <button class="btn b-indigo" type="button" onclick="selectCatalogCategory('channels')">📡 ملفات القنوات</button>
      </div>
      <div class="catalog-layout">
        <nav class="catalog-categories" id="catalog_categories" aria-label="تصنيفات المكتبة"></nav>
        <div class="catalog-results" id="catalog_results"><div class="catalog-empty">اضغط تحديث المكتبة لتحميل الأوامر.</div></div>
      </div>
      <div class="catalog-note" id="catalog_note">اختيار أي عنصر يضيف الأمر إلى مربع التيرمنال فقط؛ لن يتم التنفيذ إلا بعد الضغط على «تنفيذ الأمر».</div>
    </section>
  </div>

  <div class="foot">
    <div class="footer-title">تواصل معانا</div>
    <div class="row2 contact-links">
      <a class="pill contact-whatsapp" href="https://wa.me/201006699169" target="_blank" rel="noopener" aria-label="تواصل واتساب">
        <svg viewBox="0 0 32 32" aria-hidden="true"><path fill="currentColor" d="M16 .8A15 15 0 0 0 3.1 23.5L1 31l7.7-2A15.1 15.1 0 1 0 16 .8Zm0 27.4a12.3 12.3 0 0 1-6.3-1.7l-.5-.3-4.6 1.2 1.2-4.5-.3-.5A12.3 12.3 0 1 1 16 28.2Zm6.8-9.2c-.4-.2-2.3-1.1-2.7-1.2-.4-.1-.6-.2-.9.2-.3.4-1 1.2-1.2 1.5-.2.3-.5.3-.9.1-.4-.2-1.7-.6-3.2-2-1.2-1.1-2-2.4-2.2-2.8-.2-.4 0-.6.2-.8l.6-.7c.2-.2.3-.4.4-.7.1-.3 0-.5 0-.7-.1-.2-.9-2.1-1.2-2.8-.3-.7-.6-.6-.9-.6h-.8c-.3 0-.7.1-1.1.5-.4.4-1.4 1.3-1.4 3.2s1.4 3.7 1.6 4c.2.3 2.8 4.3 6.8 6 .9.4 1.6.6 2.1.7.9.3 1.8.2 2.4.1.8-.1 2.3-.9 2.6-1.8.3-.9.3-1.6.2-1.8-.1-.2-.4-.3-.8-.5Z"/></svg>
        <span>واتساب <b dir="ltr">01006699169</b></span>
      </a>
      <a class="pill contact-facebook" href="%%SUPPORT%%" target="_blank" rel="noopener" aria-label="تواصل عبر ماسنجر">
        <svg viewBox="0 0 32 32" aria-hidden="true"><path fill="currentColor" d="M16 2C8.1 2 2 7.8 2 15c0 4 1.9 7.5 5 9.8V30l4.8-2.6c1.3.4 2.7.6 4.2.6 7.9 0 14-5.8 14-13S23.9 2 16 2Zm1.4 17.5-3.6-3.8-7 3.8 7.7-8.2 3.7 3.8 6.9-3.8-7.7 8.2Z"/></svg>
        <span>فيسبوك / ماسنجر</span>
      </a>
    </div>
    <div class="row2 store-links">
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
  async function iptvSave() {
    const d = iptvData();
    if (!d) return;
    try {
      const response = await fetch('/api/iptv_detect');
      const result = await response.json();
      const plugins = (result.plugins || []);
      const usable = plugins;
      if (!usable.length) {
        log('⚠️ لم يتم اكتشاف أي إضافة IPTV مدعومة ومثبتة. ثبّت الإضافة أولاً أو راجع مسارها.');
        return;
      }
      const menu = usable.map((item, index) =>
        (index + 1) + ') ' + item.name + (item.ready ? ' — ' + item.path : ' — غير جاهز')
      ).join('\n');
      const answer = prompt('اختار الإضافات المطلوب حفظ الاشتراك فيها بكتابة الأرقام مفصولة بفاصلة:\n\n' + menu + '\n\nXC Plugin سيظهر للتنبيه فقط ولن يتم استبدال إعداداته.');
      if (!answer) return;
      const targets = answer.split(',').map(value => parseInt(value.trim(), 10) - 1)
        .filter(index => Number.isInteger(index) && index >= 0 && index < usable.length)
        .map(index => usable[index].id);
      if (!targets.length) { log('⚠️ لم يتم اختيار رقم صحيح.'); return; }
      call('/api/iptv_save', { ...d, targets }, '⏳ جاري حفظ الاشتراك في الإضافات المختارة...');
    } catch (error) {
      log('❌ تعذر اكتشاف إضافات IPTV: ' + error);
    }
  }
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

  /* مكتبة أوامر Online4Tech - لا تنفذ الأوامر تلقائياً */
  let commandCatalog = null;
  let catalogGroups = {};
  let activeCatalogCategory = 'plugins';
  let receiverPythonVersion = '';

  function catalogEscape(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function collectCatalogItems(node, trail, out) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node.tools)) {
      node.tools.forEach(item => {
        const command = String(item.install || '').trim();
        if (command) out.push({
          name: item.name || 'عنصر بدون اسم',
          description: item.description || '',
          command,
          path: item.path || '',
          category: trail.join(' / ')
        });
      });
    }
    if (node.subcategories && typeof node.subcategories === 'object') {
      Object.keys(node.subcategories).forEach(key => collectCatalogItems(node.subcategories[key], trail.concat(key), out));
    }
  }
  function buildCatalogGroups(data) {
    const root = data && data.main ? data.main : data;
    const specs = [
      ['panels','لوحات الإضافات',root.panels],
      ['plugins','البلجنات',root.plugins],
      ['skins','الاسكينات',root.skins],
      ['picons','البايكونات',root.picons],
      ['channels','ملفات القنوات والأقمار',root.channels],
      ['tools','الأدوات والصيانة',root.tools],
      ['feeds','المكتبات والـ Feeds',root.feeds],
      ['images','صور الأنظمة',root.images],
      ['bootlogos','شعارات الإقلاع',root.bootlogos],
      ['spinners','شاشات التحميل',root.spinners]
    ];
    const groups = {};
    specs.forEach(([id,label,node]) => {
      const items = [];
      collectCatalogItems(node, [label], items);
      if (items.length) groups[id] = {label,items};
    });
    return groups;
  }
  function isLibraryCompatible(item) {
    const match = item.name.match(/Libraries[_ -]*(\d+\.\d+)/i);
    if (!match || !receiverPythonVersion) return true;
    return receiverPythonVersion.indexOf(match[1]) === 0;
  }
  async function refreshCommandLibrary(openAfter) {
    const status = $('catalog_results');
    if (status) status.innerHTML = '<div class="catalog-empty">⏳ جاري تحميل وتحديث المكتبة من GitHub...</div>';
    try {
      const response = await fetch('/api/catalog?refresh=' + Date.now(), {cache:'no-store'});
      const payload = await response.json();
      if (!response.ok || !payload.catalog) throw new Error(payload.error || 'تعذر قراءة ملف المكتبة');
      commandCatalog = payload.catalog;
      catalogGroups = buildCatalogGroups(commandCatalog);
      try {
        const stats = await (await fetch('/api/stats')).json();
        receiverPythonVersion = stats.python || '';
      } catch (e) {}
      if (!catalogGroups[activeCatalogCategory]) activeCatalogCategory = Object.keys(catalogGroups)[0] || 'plugins';
      renderCommandLibrary();
      if (openAfter) $('catalog_modal').hidden = false;
      const total = Object.values(catalogGroups).reduce((sum, group) => sum + group.items.length, 0);
      log('✅ تم تحديث مكتبة الأوامر: ' + total + ' أمر متاح.', true);
    } catch (error) {
      if (status) status.innerHTML = '<div class="catalog-empty">❌ فشل تحديث المكتبة: ' + catalogEscape(error.message) + '</div>';
      log('❌ تعذر تحديث مكتبة الأوامر: ' + error.message, true);
    }
  }
  function openCommandLibrary() {
    $('catalog_modal').hidden = false;
    $('catalog_search').value = '';
    if (commandCatalog) renderCommandLibrary();
    else refreshCommandLibrary(true);
  }
  function closeCommandLibrary() { $('catalog_modal').hidden = true; }
  async function refreshAndSelectCatalog(id) {
    activeCatalogCategory = id;
    $('catalog_search').value = '';
    await refreshCommandLibrary();
    renderCommandLibrary();
  }
  function showMissingLibraries() {
    activeCatalogCategory = 'feeds';
    $('catalog_search').value = 'Libraries';
    renderCommandLibrary();
  }
  function showPackageIndexes() {
    activeCatalogCategory = 'tools';
    $('catalog_search').value = 'تحديث فهارس الحزم';
    renderCommandLibrary();
  }
  function selectCatalogCategory(id) {
    activeCatalogCategory = id;
    $('catalog_search').value = '';
    renderCommandLibrary();
  }
  function selectCatalogCommand(category, index) {
    const group = catalogGroups[category];
    const item = group && group.items[index];
    if (!item) return;
    if (category === 'images' || category === 'bootlogos') {
      if (!confirm('تنبيه مهم: هذا الأمر مرتبط بملفات صورة/إقلاع وقد يغيّر ملفات النظام أو صورة الرسيفر. تأكد من الموديل والتوافق وخذ نسخة احتياطية. هل تريد وضع الأمر في التيرمنال؟')) return;
    }
    if (/Libraries[_ -]*\d+\.\d+/i.test(item.name) && !isLibraryCompatible(item)) {
      alert('إصدار المكتبة لا يطابق Python الموجود على الرسيفر (' + (receiverPythonVersion || 'غير معروف') + ').');
      return;
    }
    $('cmd_input').value = item.command;
    closeCommandLibrary();
    $('cmd_input').focus();
    log('📌 تم وضع أمر (' + item.name + ') في مربع التيرمنال. راجعه قبل التنفيذ.', true);
  }
  function renderCommandLibrary() {
    const cats = $('catalog_categories'), results = $('catalog_results');
    if (!cats || !results) return;
    cats.innerHTML = Object.keys(catalogGroups).map(id => {
      const group = catalogGroups[id];
      let count = group.items.filter(item => id !== 'feeds' || isLibraryCompatible(item) || !/Libraries[_ -]*\d+\.\d+/i.test(item.name)).length;
      return '<button type="button" class="catalog-category ' + (id === activeCatalogCategory ? 'active' : '') + '" data-category="' + id + '" onclick="selectCatalogCategory(this.dataset.category)">' +
        catalogEscape(group.label) + ' <small>(' + count + ')</small></button>';
    }).join('');
    const group = catalogGroups[activeCatalogCategory];
    if (!group) { results.innerHTML = '<div class="catalog-empty">لا توجد أوامر في هذا القسم.</div>'; return; }
    const query = ($('catalog_search').value || '').trim().toLowerCase();
    const items = group.items.filter(item => {
      if (activeCatalogCategory === 'feeds' && /Libraries[_ -]*\d+\.\d+/i.test(item.name) && !isLibraryCompatible(item)) return false;
      return !query || (item.name + ' ' + item.description + ' ' + item.category).toLowerCase().includes(query);
    });
    if (!items.length) {
      const isLibGroup = activeCatalogCategory === 'feeds' && /libraries|مكتبات/i.test(query);
      results.innerHTML = '<div class="catalog-empty">' +
        (isLibGroup && receiverPythonVersion ? 'لا توجد حزمة مكتبات مسجلة في الكتالوج متوافقة مع Python ' + catalogEscape(receiverPythonVersion) + '. لم نعرض مكتبات 3.12 على جهاز Python 3.13.' : 'لا توجد نتائج مطابقة.') +
        '</div>';
      return;
    }
    results.innerHTML = items.map(item => {
      const index = group.items.indexOf(item);
      return '<button type="button" class="catalog-item" data-category="' + activeCatalogCategory + '" data-index="' + index + '" onclick="selectCatalogCommand(this.dataset.category, Number(this.dataset.index))">' +
        '<b>' + catalogEscape(item.name) + '</b><small>' + catalogEscape(item.description) + '</small></button>';
    }).join('');
    const note = $('catalog_note');
    if (note) note.textContent = activeCatalogCategory === 'images'
      ? 'صور الأنظمة: أوامر قد تغيّر نظام الرسيفر. تأكد من موديل الجهاز والتوافق قبل نقل الأمر إلى التيرمنال. الاختيار لا ينفّذ الأمر.'
      : activeCatalogCategory === 'feeds'
        ? 'المكتبات والـ Feeds: يتم إخفاء حزم Python غير المطابقة لإصدار Python المكتشف على الرسيفر. الاختيار يملأ التيرمنال فقط.'
        : 'اختيار أي عنصر يضيف الأمر إلى مربع التيرمنال فقط؛ لن يتم التنفيذ إلا بعد الضغط على «تنفيذ الأمر».';
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
    plugins = {
        "xstreamity": {
            "label": "XStreamity", "url": XSTREAMITY_URL,
            "pkg": XSTREAMITY_PKG,
        },
        "xklass": {
            "label": "XKlass", "url": XKLASS_URL,
            "pkg": XKLASS_PKG,
        },
        "ajpanel": {
            "label": "AJPanel",
            "url": "https://gitlab.com/eliesat/extensions/-/raw/main/ajpanel/ajpanel.sh",
        },
        "jedimakerxtream": {
            "label": "JediMakerXtream",
            "url": "https://gitlab.com/eliesat/extensions/-/raw/main/jedimakerxtream/jedimakerxtream.sh",
        },
    }
    plugin = plugins.get(name)
    if not plugin:
        return "❌ بلجن غير معروف."
    url, pkg = plugin.get("url", ""), plugin.get("pkg", "")
    if url:
        out = run('wget -qO- "%s" | sh' % url, 300)
    elif pkg:
        out = run("opkg update && opkg install %s" % pkg, 300)
    else:
        return "❌ لم يتم ضبط مصدر تثبيت %s." % plugin["label"]
    return "✅ انتهت عملية تثبيت %s:\n\n%s\n\nأعد تشغيل الواجهة لظهور البلجن." % (plugin["label"], out or "تم.")


def build_m3u_url(d):
    return "%s/get.php?username=%s&password=%s&type=m3u_plus&output=ts" % (
        d["host"], urllib.parse.quote(d["user"], safe=""), urllib.parse.quote(d["pass"], safe=""))


PICON_ARCHIVES = {
    "picon_ext": "https://github.com/online4tech/online4Tech/releases/download/online4tech-picons-picon/picon.zip",
    "picon_int": "https://github.com/KhaledAli65/picon/archive/refs/heads/main.zip",
}


def _mount_unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def discover_writable_storage(min_free_mb=100):
    candidates = {}
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as handle:
            mounts = [line.split() for line in handle if len(line.split()) >= 3]
    except Exception:
        mounts = []
    excluded_fs = {"rootfs", "tmpfs", "ramfs", "proc", "sysfs", "devtmpfs", "overlay", "squashfs"}
    for fields in mounts:
        device, mountpoint, fs_type = fields[0], _mount_unescape(fields[1]), fields[2]
        if not mountpoint.startswith("/media/") or fs_type.lower() in excluded_fs:
            continue
        try:
            real_path = os.path.realpath(mountpoint)
            if not os.path.isdir(real_path) or real_path == "/":
                continue
            stats = os.statvfs(real_path)
            free_mb = (stats.f_bavail * stats.f_frsize) // (1024 * 1024)
            if free_mb < min_free_mb or not os.access(real_path, os.W_OK):
                continue
            current = candidates.get(real_path)
            if current is None or free_mb > current["free_mb"]:
                candidates[real_path] = {
                    "path": real_path, "mountpoint": mountpoint,
                    "device": device, "filesystem": fs_type, "free_mb": free_mb
                }
        except Exception:
            continue
    # /media/hdd may be a symlink to a real mount such as /media/mmcblk1p5.
    for alias in ("/media/hdd", "/media/usb"):
        try:
            real_path = os.path.realpath(alias)
            if real_path in candidates:
                candidates[real_path]["aliases"] = sorted(set(candidates[real_path].get("aliases", []) + [alias]))
        except Exception:
            pass
    return sorted(candidates.values(), key=lambda item: item["free_mb"], reverse=True)


def _picon_archive_members(archive, flatten):
    all_files = [item for item in archive.infolist() if not item.is_dir()]
    picon_files = []
    for item in all_files:
        name = item.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if "picon" in [part.lower() for part in parts]:
            index = [part.lower() for part in parts].index("picon")
            relative = parts[index + 1:]
            if relative and relative[-1].lower().endswith((".png", ".svg", ".jpg", ".webp")):
                picon_files.append((item, "/".join(relative[-1:] if flatten else relative)))
    if picon_files:
        return picon_files
    image_files = []
    for item in all_files:
        name = item.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if parts and parts[-1].lower().endswith((".png", ".svg", ".jpg", ".webp")):
            image_files.append((item, parts[-1] if flatten else parts[-1]))
    return image_files


def _inspect_picon_archive(archive_path, flatten=False):
    import zipfile
    with zipfile.ZipFile(archive_path, "r") as archive:
        selected = _picon_archive_members(archive, flatten)
        if not selected:
            raise RuntimeError("ملف ZIP لا يحتوي على صور بيكونات معروفة.")
        return len(selected), sum(item.file_size for item, relative in selected)


def _safe_extract_picons(archive_path, destination, flatten=False):
    import zipfile
    os.makedirs(destination, exist_ok=True)
    total = 0
    count = 0
    with zipfile.ZipFile(archive_path, "r") as archive:
        selected = _picon_archive_members(archive, flatten)
        if not selected:
            raise RuntimeError("ملف ZIP لا يحتوي على صور بيكونات معروفة.")
        for item, relative in selected:
            normalized = os.path.normpath(relative)
            if normalized.startswith("..") or os.path.isabs(normalized):
                continue
            target = os.path.join(destination, normalized)
            if os.path.commonpath([os.path.realpath(destination), os.path.realpath(os.path.dirname(target))]) != os.path.realpath(destination):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(item, "r") as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            try:
                os.chmod(target, 0o644)
            except Exception:
                pass
            total += item.file_size
            count += 1
    if count == 0:
        raise RuntimeError("لم يتم استخراج أي ملف بيكونات صالح.")
    return count, total


def _replace_directory_safely(staging, target):
    import time
    backup = target + ".online4tech-backup-" + str(int(time.time()))
    moved_old = False
    if os.path.lexists(target):
        os.rename(target, backup)
        moved_old = True
    try:
        os.rename(staging, target)
    except Exception:
        if moved_old and not os.path.lexists(target):
            os.rename(backup, target)
        raise
    return backup if moved_old else ""


def do_picon_update(kind):
    if kind not in PICON_ARCHIVES:
        return "❌ نوع تحديث البيكونات غير معروف."
    external = kind == "picon_ext"
    storages = discover_writable_storage(100)
    if external and not storages:
        return "⚠️ لم يتم العثور على هارد أو فلاشة صالحة بمساحة فارغة لا تقل عن 100MB. لم يتم تغيير أي ملف."
    if external:
        storage = storages[0]
        base_dir = storage["path"]
        target = os.path.join(base_dir, "picon")
        display_target = storage["mountpoint"]
    else:
        base_dir = "/usr/share/enigma2"
        target = os.path.join(base_dir, "picon")
        display_target = "الذاكرة الداخلية"
        if not os.path.isdir(base_dir) or not os.access(base_dir, os.W_OK):
            return "❌ مجلد Enigma2 الداخلي غير قابل للكتابة. لم يتم إجراء أي تغيير."
    try:
        os.makedirs(base_dir, exist_ok=True)
        work_dir = tempfile.mkdtemp(prefix=".online4tech-picon-", dir=base_dir if external else "/tmp")
        archive_path = os.path.join(work_dir, "picons.zip")
        staging = os.path.join(base_dir, ".picon-online4tech-new-" + str(os.getpid()))
        if os.path.exists(staging):
            shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        request = urllib.request.Request(PICON_ARCHIVES[kind], headers={"User-Agent": "Online4Tech-Control-Center"})
        with urllib.request.urlopen(request, timeout=45) as response:
            content_length = int(response.headers.get("Content-Length") or 0)
            if external and content_length:
                stats = os.statvfs(base_dir)
                free_bytes = stats.f_bavail * stats.f_frsize
                if free_bytes < content_length + (30 * 1024 * 1024):
                    raise RuntimeError("المساحة المتاحة على وحدة التخزين لا تكفي لتنزيل الأرشيف بأمان.")
            with open(archive_path, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    if external:
                        stats = os.statvfs(base_dir)
                        if (stats.f_bavail * stats.f_frsize) < (20 * 1024 * 1024):
                            raise RuntimeError("تم إيقاف التنزيل لحماية آخر 20MB من مساحة وحدة التخزين.")
        archive_size = os.path.getsize(archive_path)
        if archive_size < 100:
            raise RuntimeError("ملف البيكونات الذي تم تنزيله فارغ أو غير صالح.")
        count, expanded_size = _inspect_picon_archive(archive_path, flatten=external)
        needed_mb = (expanded_size // (1024 * 1024)) + 30
        stats = os.statvfs(base_dir)
        free_mb = (stats.f_bavail * stats.f_frsize) // (1024 * 1024)
        if free_mb < needed_mb:
            raise RuntimeError("المساحة غير كافية قبل فك الضغط. المطلوب تقريباً %dMB والمتاح %dMB." % (needed_mb, free_mb))
        count, expanded_size = _safe_extract_picons(archive_path, staging, flatten=external)
        if external:
            backup = _replace_directory_safely(staging, target)
            link_path = "/usr/share/enigma2/picon"
            link_parent = os.path.dirname(link_path)
            if not os.path.isdir(link_parent):
                if backup and os.path.isdir(backup) and not os.path.lexists(target):
                    os.rename(backup, target)
                raise RuntimeError("مسار ربط البيكونات الداخلي غير موجود.")
            temporary_link = link_path + ".online4tech-new"
            old_link_backup = ""
            old_link_value = os.readlink(link_path) if os.path.islink(link_path) else ""
            try:
                if os.path.lexists(temporary_link):
                    os.unlink(temporary_link)
                os.symlink(target, temporary_link)
                if os.path.lexists(link_path) and not os.path.islink(link_path):
                    old_link_backup = link_path + ".online4tech-old-" + str(int(time.time()))
                    os.rename(link_path, old_link_backup)
                os.replace(temporary_link, link_path)
            except Exception:
                if os.path.lexists(temporary_link):
                    os.unlink(temporary_link)
                if old_link_backup and os.path.lexists(old_link_backup) and not os.path.lexists(link_path):
                    os.rename(old_link_backup, link_path)
                elif old_link_value and not os.path.lexists(link_path):
                    os.symlink(old_link_value, link_path)
                if backup and os.path.isdir(backup):
                    failed_new = target + ".online4tech-failed-" + str(int(time.time()))
                    if os.path.lexists(target):
                        os.rename(target, failed_new)
                    if not os.path.lexists(target):
                        os.rename(backup, target)
                raise
            result = "✅ تم تحديث البيكونات على وحدة التخزين: %s" % display_target
            result += "\nالمسار الفعلي: %s" % target
            if backup:
                result += "\nتم الاحتفاظ بالنسخة السابقة في: %s" % backup
            if old_link_backup:
                result += "\nتم الاحتفاظ بمجلد الربط القديم في: %s" % old_link_backup
            result += "\nتم ربط /usr/share/enigma2/picon بالمسار الجديد."
        else:
            backup = _replace_directory_safely(staging, target)
            result = "✅ تم تحديث البيكونات داخلياً في: %s" % target
            if backup:
                result += "\nتم الاحتفاظ بالنسخة السابقة في: %s" % backup
        return result + "\nعدد الصور: %d | الحجم بعد الفك: %dMB\nلم يتم حذف النسخة القديمة أو إعادة تشغيل Enigma2." % (count, expanded_size // (1024 * 1024))
    except Exception as error:
        try:
            if "staging" in locals() and os.path.isdir(staging):
                shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            pass
        return "❌ فشل تحديث البيكونات دون حذف النسخة السابقة:\n%s" % error
    finally:
        try:
            if "work_dir" in locals():
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def read_enigma_settings():
    values = {}
    try:
        with open("/etc/enigma2/settings", "r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                line = raw.strip()
                if line.startswith("config.plugins.") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
    except Exception:
        pass
    return values


def plugin_directory_exists(name):
    candidates = (
        "/usr/lib/enigma2/python/Plugins/Extensions/" + name,
        "/usr/lib64/enigma2/python/Plugins/Extensions/" + name,
        "/usr/lib/python/Plugins/Extensions/" + name,
    )
    return next((path for path in candidates if os.path.isdir(path)), "")


def discover_iptv_plugins():
    settings = read_enigma_settings()
    found = []

    xstreamity_dir = plugin_directory_exists("XStreamity")
    if xstreamity_dir:
        location = settings.get("config.plugins.XStreamity.location", "/etc/enigma2/xstreamity")
        filename = os.path.basename(settings.get("config.plugins.XStreamity.playlist_name", "playlists.txt"))
        if not filename.lower().endswith(".txt"):
            filename = "playlists.txt"
        found.append({
            "id": "xstreamity", "name": "XStreamity",
            "path": os.path.join(location, filename),
            "ready": os.path.isdir(location) and os.access(location, os.W_OK),
            "note": "ملف القوائم المحدد في إعدادات الإضافة"
        })

    xklass_dir = plugin_directory_exists("XKlass")
    if xklass_dir:
        location = settings.get("config.plugins.XKlass.location", "/etc/enigma2/xklass")
        found.append({
            "id": "xklass", "name": "XKlass",
            "path": os.path.join(location, "playlists.txt"),
            "ready": os.path.isdir(location) and os.access(location, os.W_OK),
            "note": "ملف القوائم المحدد في إعدادات الإضافة"
        })

    jedi_dir = plugin_directory_exists("JediMakerXtream")
    if jedi_dir:
        location = settings.get("config.plugins.JediMakerXtream.location", "/etc/enigma2/jediplaylists/")
        found.append({
            "id": "jedimakerxtream", "name": "Jedi Maker Xtream",
            "path": os.path.join(location, "playlists.txt"),
            "ready": os.path.isdir(location) and os.access(location, os.W_OK),
            "note": "ملف playlists.txt الخاص بالإضافة"
        })

    xc_dir = plugin_directory_exists("XCplugin")
    if xc_dir:
        location = settings.get("config.plugins.XCplugin.pthxmlfile", "/etc/enigma2/xc")
        found.append({
            "id": "xcplugin", "name": "XC Plugin",
            "path": os.path.join(location, "xc_e2_plugin.xml"),
            "ready": os.path.isdir(location) and os.access(location, os.W_OK),
            "supported": False,
            "note": "ملف XML واحد وإعداد سيرفر واحد؛ الحفظ التلقائي قد يستبدل الاشتراك الحالي"
        })
    return found


def do_iptv_save(d, targets):
    url = build_m3u_url(d)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(d.get("name") or "Online4Tech").strip())[:32] or "Online4Tech"
    line = "%s #Online4Tech_%s" % (url, safe_name)
    detected = {item["id"]: item for item in discover_iptv_plugins()}
    lines = []
    if not isinstance(targets, list) or not targets:
        return "⚠️ لم يتم اختيار أي إضافة للحفظ."
    for target in targets:
        item = detected.get(str(target))
        if not item:
            lines.append("⚠️ تم تجاهل إضافة غير مثبتة أو غير معروفة: " + str(target))
            continue
        if not item.get("supported", True):
            lines.append("⚠️ %s: لم يتم الحفظ بأمان. %s" % (item["name"], item["note"]))
            continue
        path = item["path"]
        folder = os.path.dirname(path)
        try:
            if not os.path.isdir(folder):
                lines.append("⚠️ %s: مجلد القوائم غير موجود: %s" % (item["name"], folder))
                continue
            if not os.access(folder, os.W_OK):
                lines.append("❌ %s: لا توجد صلاحية كتابة في %s" % (item["name"], folder))
                continue
            existing = ""
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    existing = handle.read()
            if url in existing:
                lines.append("• الاشتراك موجود بالفعل في %s: %s" % (item["name"], path))
                continue
            with open(path, "a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(line + "\n")
            lines.append("✅ تم حفظ الاشتراك في %s: %s" % (item["name"], path))
        except Exception as error:
            lines.append("❌ %s: %s" % (item["name"], error))
    return "\n".join(lines) + "\n\nلم يتم حذف أو استبدال أي اشتراك سابق.\nالرابط: " + url


def do_iptv_bouquet(d):
    url = build_m3u_url(d)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        playlist = urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "ignore")
    except Exception as e:
        return "❌ تعذر تحميل ملف M3U:\n%s" % e

    def attr_value(line, key):
        match = re.search(r'(?:^|[\s,])%s="([^"]*)"' % re.escape(key), line, re.I)
        return match.group(1).strip() if match else ""

    def clean_name(value, fallback="غير مصنف"):
        value = re.sub(r"[\r\n\t]+", " ", str(value or ""))
        value = re.sub(r"\s+", " ", value).strip()
        value = value.replace("|", "-").replace(":", "-")
        return value[:180] or fallback

    def classify(stream_url, group):
        path = urllib.parse.urlparse(stream_url).path.lower()
        if re.search(r"/movie(?:/|$)", path):
            return "movie"
        if re.search(r"/series(?:/|$)", path):
            return "series"
        if re.search(r"/live(?:/|$)", path):
            return "live"
        hint = (group or "").lower()
        if any(x in hint for x in ("series", "مسلسل", "مسلسلات")):
            return "series"
        if any(x in hint for x in ("movie", "movies", "film", "vod", "فيلم", "افلام", "أفلام", "مسرح")):
            return "movie"
        return "live"

    def episode_parts(title, series_hint=""):
        title = clean_name(title, "حلقة")
        patterns = (
            re.compile(r"^(.*?)\s*[-_. ]*\bS(\d{1,2})\s*E(\d{1,3})\b.*$", re.I),
            re.compile(r"^(.*?)\s*[-_. ]*\b(\d{1,2})x(\d{1,3})\b.*$", re.I),
            re.compile(r"^(.*?)\s*[-_. ]*(?:الموسم|موسم)\s*(\d+)\s*(?:الحلقة|حلقة)\s*(\d+).*$", re.I),
        )
        for pattern in patterns:
            match = pattern.match(title)
            if match:
                show = clean_name(match.group(1), series_hint or "مسلسل")
                return show, int(match.group(2)), int(match.group(3))
        # بعض المزودين يضعون اسم المسلسل في tvg-name أو group-title.
        show = clean_name(series_hint or title, "مسلسل")
        return show, 9999, 9999

    entries = []
    current = None
    pending_group = ""
    for raw_line in playlist.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTGRP:"):
            pending_group = clean_name(line.split(":", 1)[1], "")
            continue
        if line.startswith("#EXTINF:"):
            display = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            current = {
                "name": clean_name(display, "بدون اسم"),
                "group": clean_name(attr_value(line, "group-title") or pending_group, "غير مصنف"),
                "tvg_name": clean_name(attr_value(line, "tvg-name"), ""),
            }
            pending_group = ""
            continue
        if line.startswith("#") or current is None:
            continue
        kind = classify(line, current["group"])
        item = {
            "kind": kind,
            "name": current["name"],
            "url": line,
            "category": current["group"],
        }
        if kind == "series":
            item["show"], item["season"], item["episode"] = episode_parts(
                current["name"], current["tvg_name"]
            )
        entries.append(item)
        current = None

    if not entries:
        return "⚠️ ملف الاشتراك اتحمّل، لكنه لا يحتوي عناصر M3U قابلة للتحويل."

    # أنشئ ملفات مفضلات فرعية بأسماء ثابتة مبنية على hash لتفادي مشاكل أسماء الملفات العربية.
    import hashlib

    prefix = "userbouquet.online4tech_"

    def file_key(value):
        return hashlib.md5(value.encode("utf-8")).hexdigest()[:12]

    def service_lines(items):
        result = []
        for item in items:
            title = clean_name(item["name"], "بدون اسم")
            stream = urllib.parse.quote(item["url"], safe="")
            result.append("#SERVICE 4097:0:1:0:0:0:0:0:0:0:%s:%s" % (stream, title))
            result.append("#DESCRIPTION %s" % title)
        return result

    generated = {}
    top_sections = []

    # Live: المفضلة الرئيسية تحتوي مفضلة مستقلة لكل تصنيف.
    live_categories = {}
    for item in entries:
        if item["kind"] == "live":
            live_categories.setdefault(item["category"], []).append(item)
    if live_categories:
        root_name = prefix + "live.tv"
        root_lines = ["#NAME Online4Tech Live"]
        for category in sorted(live_categories, key=lambda x: x.casefold()):
            child = prefix + "live_" + file_key(category) + ".tv"
            generated[child] = ["#NAME Live - " + clean_name(category)] + service_lines(live_categories[category])
            root_lines.append('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % child)
        generated[root_name] = root_lines
        top_sections.append(root_name)

    # Movie: مفضلة رئيسية، ثم تصنيفات، وكل فيلم/مسرحية عنصر مستقل باسمه.
    movie_categories = {}
    for item in entries:
        if item["kind"] == "movie":
            movie_categories.setdefault(item["category"], []).append(item)
    if movie_categories:
        root_name = prefix + "movie.tv"
        root_lines = ["#NAME Online4Tech Movie"]
        for category in sorted(movie_categories, key=lambda x: x.casefold()):
            child = prefix + "movie_" + file_key(category) + ".tv"
            generated[child] = ["#NAME Movie - " + clean_name(category)] + service_lines(movie_categories[category])
            root_lines.append('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % child)
        generated[root_name] = root_lines
        top_sections.append(root_name)

    # Series: كل مسلسل له مفضلة باسمه، والحلقات مرتبة بالموسم ثم رقم الحلقة.
    series_shows = {}
    for item in entries:
        if item["kind"] == "series":
            series_shows.setdefault(item["show"], []).append(item)
    if series_shows:
        root_name = prefix + "series.tv"
        root_lines = ["#NAME Online4Tech Series"]
        for show in sorted(series_shows, key=lambda x: x.casefold()):
            child = prefix + "series_" + file_key(show) + ".tv"
            episodes = sorted(
                series_shows[show],
                key=lambda x: (x["season"], x["episode"], x["name"].casefold())
            )
            generated[child] = ["#NAME " + clean_name(show)] + service_lines(episodes)
            root_lines.append('#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % child)
        generated[root_name] = root_lines
        top_sections.append(root_name)

    # اكتب المفضلات الجديدة أولاً، ثم حدّث قائمة TV مع الحفاظ على كل مفضلات المستخدم الأخرى.
    try:
        os.makedirs(ENIGMA_DIR, exist_ok=True)
        for filename, lines in generated.items():
            write_file(os.path.join(ENIGMA_DIR, filename), "\n".join(lines) + "\n")

        bq_path = os.path.join(ENIGMA_DIR, "bouquets.tv")
        old_bouquets = open(bq_path, encoding="utf-8").read() if os.path.exists(bq_path) else "#NAME Bouquets (TV)\n"
        kept_lines = [
            line for line in old_bouquets.splitlines()
            if prefix not in line
        ]
        if not kept_lines:
            kept_lines = ["#NAME Bouquets (TV)"]
        for filename in top_sections:
            kept_lines.append(
                '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
            )
        write_file(bq_path, "\n".join(kept_lines) + "\n")

        # امسح فقط ملفات Online4Tech القديمة التي لم تعد ضمن التوليد الحالي.
        for filename in os.listdir(ENIGMA_DIR):
            if filename.startswith(prefix) and filename.endswith(".tv") and filename not in generated:
                try:
                    os.remove(os.path.join(ENIGMA_DIR, filename))
                except Exception:
                    pass
    except Exception as e:
        return "❌ حصل خطأ أثناء إنشاء المفضلات:\n%s" % e

    run("wget -qO- 'http://127.0.0.1/web/servicelistreload?mode=2' >/dev/null 2>&1", 15)
    counts = {
        "live": sum(1 for x in entries if x["kind"] == "live"),
        "movie": sum(1 for x in entries if x["kind"] == "movie"),
        "series": sum(1 for x in entries if x["kind"] == "series"),
    }
    return (
        "✅ تم إنشاء مفضلات Online4Tech بنجاح:\n"
        "📡 Live: %d قناة في %d تصنيف\n"
        "🎬 Movie: %d فيلم/مسرحية في %d تصنيف\n"
        "📺 Series: %d حلقة في %d مسلسل\n\n"
        "تم تحديث المفضلات القديمة الخاصة بـ Online4Tech فقط، مع الحفاظ على باقي مفضلات الرسيفر."
        % (
            counts["live"], len(live_categories),
            counts["movie"], len(movie_categories),
            counts["series"], len(series_shows),
        )
    )


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
        clean_path = self.path.split("?", 1)[0]
        if clean_path in ("/", "/index.html"):
            page = (HTML_PAGE.replace("%%PORT%%", str(PORT)).replace("%%SUPPORT%%", SUPPORT_URL)
                    .replace("%%SITE%%", SITE_URL).replace("%%STORE%%", STORE_URL))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        elif clean_path in ("/assets/banner.png", "/assets/icon.png"):
            data = get_brand_asset(os.path.basename(clean_path))
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=31536000")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
        elif self.path.startswith("/api/catalog"):
            try:
                req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "Online4Tech-ControlCenter"})
                with urllib.request.urlopen(req, timeout=25) as response:
                    raw_catalog = response.read(3 * 1024 * 1024 + 1)
                if len(raw_catalog) > 3 * 1024 * 1024:
                    raise ValueError("ملف المكتبة أكبر من الحد المسموح.")
                catalog = json.loads(raw_catalog.decode("utf-8"))
                if not isinstance(catalog, dict):
                    raise ValueError("صيغة ملف المكتبة غير صحيحة.")
                self._json({"catalog": catalog})
            except Exception as error:
                self._json({"error": "تعذر تحميل المكتبة: %s" % error}, 502)
        elif clean_path == "/api/iptv_detect":
            self._json({"plugins": discover_iptv_plugins()})
        elif clean_path == "/api/stats":
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
                out = do_iptv_save(p, p.get("targets", []))
            elif self.path == "/api/iptv_bouquet":
                out = do_iptv_bouquet(p)
            elif self.path == "/api/install":
                emu = p.get("emu")
                url = OSCAM_SCRIPT_URL if emu == "oscam" else NCAM_SCRIPT_URL
                out = "✅ انتهى تثبيت %s:\n\n%s" % (str(emu).upper(), run('wget -qO- "%s" | sh' % url, 180) or "تم.")
            elif self.path == "/api/tool":
                tool = p.get("tool")
                if tool in ("picon_ext", "picon_int"):
                    label = p.get("label") or tool
                    out = do_picon_update(tool)
                else:
                    url = TOOLS_URLS.get(tool)
                    if not url:
                        self._json({"output": "❌ أداة غير معروفة."}, 400)
                        return
                    label = p.get("label") or tool
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
    threading.Thread(target=prefetch_brand_assets, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Online Web Control running on http://%s:%d" % (get_ip(), PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
