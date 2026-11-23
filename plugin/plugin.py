# -*- coding: utf-8 -*-
# Online Web Control - Enigma2 plugin
# بوابة لوحة الويب (بورت 7070): أخضر = فتح، أحمر = قفل، مع عرض الحالة والـ IP والـ PORT.
from __future__ import print_function
import os
import signal
import socket
import subprocess
import threading
import time

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from enigma import eTimer

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PLUGIN_DIR, "assets")
SERVER = os.path.join(PLUGIN_DIR, "online_web_control.py")
PORT = 7070
PID_FILE = "/tmp/online_web_control.pid"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/"
BRAND_BANNER_URL = GITHUB_RAW_BASE + "assets/o4t-logo-plugin.png"
BRAND_ICON_URL = GITHUB_RAW_BASE + "assets/o4t-icon.png"
BRAND_BANNER_PATH = os.path.join(ASSETS_DIR, "o4t-logo-plugin.png")
BRAND_ICON_PATH = os.path.join(ASSETS_DIR, "o4t-icon.png")
PLUGIN_ICON = os.path.join(PLUGIN_DIR, "plugin.png")
BRAND_SYNC_FLAG = os.path.join(ASSETS_DIR, ".o4t_brand_v2")

try:
    with open(os.path.join(PLUGIN_DIR, "VERSION")) as _f:
        VERSION = _f.read().strip()
except Exception:
    VERSION = ""


def _download_file(url, dest_path, timeout=20):
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Online4Tech-Enigma2-Plugin"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(5 * 1024 * 1024)
        if not data:
            return False
        folder = os.path.dirname(dest_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        tmp_path = dest_path + ".tmp"
        with open(tmp_path, "wb") as handle:
            handle.write(data)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, dest_path)
        return True
    except Exception as error:
        print("[OnlineWebControl] Asset download failed (%s): %s" % (url, error))
        return False


def _install_menu_icon(src_icon):
    """Install the O4T icon as plugin.png (resized if Pillow is available)."""
    try:
        if not os.path.isfile(src_icon) or os.path.getsize(src_icon) == 0:
            return False
        tmp_icon = PLUGIN_ICON + ".tmp"
        try:
            from PIL import Image
            img = Image.open(src_icon).convert("RGBA")
            img.thumbnail((128, 128), Image.LANCZOS)
            img.save(tmp_icon, "PNG")
        except Exception:
            with open(src_icon, "rb") as src_f, open(tmp_icon, "wb") as dst_f:
                dst_f.write(src_f.read())
        os.chmod(tmp_icon, 0o644)
        os.replace(tmp_icon, PLUGIN_ICON)
        return True
    except Exception as error:
        print("[OnlineWebControl] Menu icon install failed: %s" % error)
        return False


def sync_brand_assets(force=False):
    """Download O4T banner and icon once from GitHub and cache them locally on the receiver."""
    try:
        if not os.path.exists(ASSETS_DIR):
            os.makedirs(ASSETS_DIR, exist_ok=True)
        ok_banner = os.path.isfile(BRAND_BANNER_PATH) and os.path.getsize(BRAND_BANNER_PATH) > 0
        ok_icon = os.path.isfile(BRAND_ICON_PATH) and os.path.getsize(BRAND_ICON_PATH) > 0

        if force or not ok_banner:
            ok_banner = _download_file(BRAND_BANNER_URL, BRAND_BANNER_PATH) or ok_banner
        if force or not ok_icon:
            ok_icon = _download_file(BRAND_ICON_URL, BRAND_ICON_PATH) or ok_icon

        if ok_icon:
            _install_menu_icon(BRAND_ICON_PATH)

        if ok_banner and ok_icon and (force or not os.path.isfile(BRAND_SYNC_FLAG)):
            try:
                with open(BRAND_SYNC_FLAG, "w") as flag_f:
                    flag_f.write("ok\\n")
            except Exception:
                pass
    except Exception as error:
        print("[OnlineWebControl] Brand sync error: %s" % error)


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        out = subprocess.Popen("hostname -I", shell=True, stdout=subprocess.PIPE).communicate()[0]
        out = out.decode("utf-8", "ignore").split()
        if out:
            return out[0]
    except Exception:
        pass
    return "127.0.0.1"


def is_running():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def start_server():
    if is_running():
        return
    py = "python3" if os.system("which python3 >/dev/null 2>&1") == 0 else "python"
    try:
        devnull = open(os.devnull, "wb")
        p = subprocess.Popen([py, SERVER], stdout=devnull, stderr=devnull,
                             close_fds=True, preexec_fn=os.setsid)
        with open(PID_FILE, "w") as f:
            f.write(str(p.pid))
    except Exception:
        pass


def stop_server():
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE)
    except Exception:
        pass
    os.system("pkill -f online_web_control.py >/dev/null 2>&1")


def _show_result(session, message, timeout=6):
    try:
        from Screens.MessageBox import MessageBox
        session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=timeout)
    except Exception as error:
        print("[OnlineWebControl] %s" % error)


def _restart_gui(session):
    """Restart only the Enigma2 GUI through Enigma2's native quit/restart flow."""
    try:
        from Screens.Standby import TryQuitMainloop
        session.open(TryQuitMainloop, 3)
    except Exception as error:
        print("[OnlineWebControl] Native GUI restart failed: %s" % error)
        _show_result(
            session,
            "تم التحديث بنجاح، لكن تعذر طلب إعادة تشغيل الواجهة تلقائيًا.\n%s" % error,
            timeout=12
        )


def update_plugin(session):
    """Fetch and safely install the latest plugin files from the official GitHub repo."""
    import tempfile
    import shutil
    import urllib.request

    base = GITHUB_RAW_BASE
    files = {
        "plugin.py": "plugin/plugin.py",
        "online_web_control.py": "plugin/online_web_control.py",
        "__init__.py": "plugin/__init__.py",
        "VERSION": "VERSION",
        "assets/o4t-main-logo.png": "assets/o4t-main-logo.png",
        "assets/o4t-logo-plugin.png": "assets/o4t-logo-plugin.png",
        "assets/o4t-icon.png": "assets/o4t-icon.png",
    }
    temp_dir = None
    backups = {}
    changed = []
    try:
        temp_dir = tempfile.mkdtemp(prefix="online4tech-update-")
        for local_name, remote_path in files.items():
            request = urllib.request.Request(
                base + remote_path,
                headers={"User-Agent": "Online4Tech-Enigma2-Plugin"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if not data:
                raise Exception("الملف فارغ: " + remote_path)
            target = os.path.join(temp_dir, local_name)
            parent = os.path.dirname(target)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(target, "wb") as handle:
                handle.write(data)

        # Validate Python files before touching the installed plugin.
        for name in ("plugin.py", "online_web_control.py", "__init__.py"):
            path = os.path.join(temp_dir, name)
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            compile(source, name, "exec")

        with open(os.path.join(temp_dir, "VERSION"), "r") as handle:
            remote_version = handle.read().strip() or "غير محدد"

        # Keep a rollback copy of every existing file.
        for name in files:
            destination = os.path.join(PLUGIN_DIR, name)
            if os.path.exists(destination):
                backup = destination + ".online4tech-backup"
                shutil.copy2(destination, backup)
                backups[destination] = backup

        stop_server()
        for name in files:
            source = os.path.join(temp_dir, name)
            destination = os.path.join(PLUGIN_DIR, name)
            parent = os.path.dirname(destination)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            staged = destination + ".online4tech-new"
            shutil.copyfile(source, staged)
            os.chmod(staged, 0o644)
            os.rename(staged, destination)
            changed.append(destination)

        # Refresh brand banner & menu icon from GitHub (non-fatal if offline).
        sync_brand_assets(force=True)

        # Launch the updated web panel, then restart only Enigma2's GUI.
        start_server()
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir = None
        for backup in backups.values():
            try:
                os.remove(backup)
            except Exception:
                pass
        print("[OnlineWebControl] Updated successfully to version %s; restarting Enigma2 GUI." % remote_version)
        _restart_gui(session)
        return
    except Exception as error:
        # Restore all files already replaced if any step failed.
        for destination in reversed(changed):
            backup = backups.get(destination)
            try:
                if backup and os.path.exists(backup):
                    shutil.copy2(backup, destination)
            except Exception:
                pass
        try:
            start_server()
        except Exception:
            pass
        _show_result(session, "فشل التحديث ولم يكتمل تثبيت الملفات:\n%s" % error, timeout=10)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


DEBUG_LOG = "/tmp/owc_debug.log"


def _dbg(where):
    """Write the last Python error to /tmp/owc_debug.log (for troubleshooting)."""
    try:
        import traceback
        with open(DEBUG_LOG, "a") as fh:
            fh.write("== %s ==\n%s\n" % (where, traceback.format_exc()))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Glass-style UI helpers. Enigma2 cannot blur, so "glass" is built from layered
# semi-transparent labels: soft top highlight, bright top edge, bottom shade and
# a thin light border. Layers: bg=0, panels=1, colored widgets=2, glass=3, text=4.
# ---------------------------------------------------------------------------
def _c(opacity, rgb):
    """Color with opacity 0-255. Enigma2 alpha byte is inverted: 00 = solid, FF = transparent."""
    return "#%02X%s" % (255 - opacity, rgb)


def _lbl(x, y, w, h, color, z):
    return '<eLabel position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="%d" />\n' % (x, y, w, h, color, z)


def _glass(x, y, w, h):
    out = _lbl(x + 1, y + 1, w - 2, min(h // 2, 52), _c(34, "FFFFFF"), 3)   # soft top highlight
    out += _lbl(x + 2, y + 1, w - 4, 2, _c(136, "FFFFFF"), 3)            # bright top edge
    out += _lbl(x + 1, y + h - 4, w - 2, 3, _c(85, "000000"), 3)        # bottom shade
    out += _lbl(x, y, w, 1, _c(85, "FFFFFF"), 3)                        # border
    out += _lbl(x, y + h - 1, w, 1, _c(51, "FFFFFF"), 3)
    out += _lbl(x, y, 1, h, _c(68, "FFFFFF"), 3)
    out += _lbl(x + w - 1, y, 1, h, _c(68, "FFFFFF"), 3)
    return out


def _panel(x, y, w, h, color=_c(204, "10263F")):
    return _lbl(x, y, w, h, color, 1) + _glass(x, y, w, h)


def _txt(name, x, y, w, h, font, color, halign="center", valign="center", z=4, extra=""):
    return ('<widget name="%s" position="%d,%d" size="%d,%d" font="Regular;%d" halign="%s" valign="%s" '
            'foregroundColor="%s" transparent="1" zPosition="%d" %s />\n') % (
                name, x, y, w, h, font, halign, valign, color, z, extra)


def _btn(name, x, y, w, h, font, fg, bg):
    return ('<widget name="%s" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
            'foregroundColor="%s" backgroundColor="%s" zPosition="2" />\n') % (name, x, y, w, h, font, fg, bg)


def _logo_ok():
    return os.path.isfile(BRAND_BANNER_PATH) and os.path.getsize(BRAND_BANNER_PATH) > 0


def _logo_block():
    """Official logo (330x108) centered in the 764px header, or a text fallback."""
    if _logo_ok():
        return ('<ePixmap position="235,25" size="330,108" pixmap="%s" alphatest="blend" zPosition="4" />\n'
                % BRAND_BANNER_PATH)
    return (_txt("brand", 45, 40, 710, 50, 34, "#FFFFFF") +
            _txt("tagline", 45, 92, 710, 34, 22, "#42D7FF"))


def _frame(title):
    s = '<screen name="%s" position="center,center" size="800,600" title="Online4Tech Web Gate" flags="wfNoBorder" backgroundColor="#050F1E">\n' % title
    s += _lbl(0, 0, 800, 600, "#050F1E", 0)
    for i, a in enumerate(("40", "34", "28", "1E", "14", "0A")):      # soft top glow (stepped fade)
        s += _lbl(0, 5 + i * 50, 800, 50, _c(int(a, 16), "1B5A94"), 0)
    s += _lbl(0, 0, 400, 5, "#00C8F0", 1) + _lbl(400, 0, 400, 5, "#1E88E5", 1)
    s += _lbl(0, 593, 400, 7, "#1E88E5", 1) + _lbl(400, 593, 400, 7, "#00C8F0", 1)
    s += _panel(18, 14, 764, 134)                                  # header
    s += _logo_block()
    return s


def _main_skin():
    s = _frame("OnlineWebControlScreen")
    s += _txt("role", 28, 152, 744, 28, 17, "#42D7FF")
    # status card
    s += _btn("card_open", 28, 186, 744, 82, 20, "#FFFFFF", "#0E8F63")
    s += _btn("card_closed", 28, 186, 744, 82, 20, "#FFFFFF", "#B5233F")
    s += _btn("card_wait", 28, 186, 744, 82, 20, "#FFFFFF", "#9A6B00")
    s += _glass(28, 186, 744, 82)
    s += _txt("card_title", 28, 190, 744, 44, 32, "#FFFFFF")
    s += _txt("card_sub", 28, 236, 744, 28, 16, "#E8F6FF")
    # IP / PORT
    s += _panel(28, 278, 364, 70) + _panel(408, 278, 364, 70)
    s += _txt("ip_label", 38, 282, 344, 20, 14, "#83B6D8")
    s += _txt("ip_value", 38, 302, 344, 42, 30, "#FFFFFF")
    s += _txt("port_label", 418, 282, 344, 20, 14, "#83B6D8")
    s += _txt("port_value", 418, 302, 344, 42, 30, "#55D7FF")
    # URL
    s += _panel(28, 358, 744, 50, _c(204, "0A1C30"))
    s += _txt("url", 38, 362, 724, 42, 26, "#D7EAF8")
    # gate buttons
    s += _btn("green", 28, 422, 364, 80, 28, "#FFFFFF", "#10A875")
    s += _btn("green_off", 28, 422, 364, 80, 24, "#6F9A8C", "#0C3A2E")
    s += _btn("red", 408, 422, 364, 80, 28, "#FFFFFF", "#D52C55")
    s += _btn("red_off", 408, 422, 364, 80, 24, "#A07582", "#40161F")
    s += _glass(28, 422, 364, 80) + _glass(408, 422, 364, 80)
    chips = (("chip_green", 34, "#10A875", "#FFFFFF"), ("chip_red", 220, "#D52C55", "#FFFFFF"),
             ("chip_yellow", 406, "#D9A914", "#1A1400"), ("chip_blue", 592, "#2D7DD2", "#FFFFFF"))
    for name, cx, bg, fg in chips:
        s += _btn(name, cx, 510, 174, 32, 17, fg, bg) + _glass(cx, 510, 174, 32)
    s += _txt("hint", 30, 546, 740, 26, 16, "#9DBFD8")
    s += _txt("footer", 30, 574, 740, 18, 13, "#4E7899")
    return s + "</screen>"


def _help_skin():
    s = _frame("OnlineWebControlHelp")
    s += _panel(18, 156, 764, 360, _c(204, "0A1C30"))
    s += _txt("h1", 38, 164, 724, 34, 24, "#42D7FF", halign="right")
    s += _txt("b1", 38, 200, 724, 100, 20, "#FFFFFF", halign="right", valign="top")
    s += _txt("h2", 38, 306, 724, 34, 24, "#42D7FF", halign="right")
    s += _txt("b2", 38, 342, 724, 100, 20, "#FFFFFF", halign="right", valign="top")
    s += _txt("note", 38, 450, 724, 56, 17, "#9DBFD8", halign="right", valign="top")
    s += _txt("hint", 30, 528, 740, 28, 17, "#9DBFD8")
    s += _txt("footer", 30, 562, 740, 24, 13, "#4E7899")
    return s + "</screen>"


def _ver_tuple(text):
    try:
        return tuple(int(x) for x in str(text).strip().split("."))
    except Exception:
        return (0,)


def get_remote_version():
    """Latest released version number from GitHub (None if offline)."""
    try:
        import urllib.request
        req = urllib.request.Request(GITHUB_RAW_BASE + "VERSION", headers={"User-Agent": "Online4Tech-Enigma2-Plugin"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8").strip() or None
    except Exception:
        return None


WEB_STAMP = os.path.join(PLUGIN_DIR, ".web_update_ts")
WEB_OFF_FLAG = os.path.join(PLUGIN_DIR, ".no_auto_web_update")
WEB_INTERVAL = 6 * 3600


def auto_update_web(force=False):
    """Silently refresh the web panel (online_web_control.py) from GitHub, no plugin update needed.
    Checked at most every 6 hours; create the file .no_auto_web_update in the plugin folder to disable."""
    try:
        if os.path.exists(WEB_OFF_FLAG):
            return False
        if not force:
            try:
                with open(WEB_STAMP) as fh:
                    if time.time() - float(fh.read().strip()) < WEB_INTERVAL:
                        return False
            except Exception:
                pass
        import urllib.request
        req = urllib.request.Request(GITHUB_RAW_BASE + "plugin/online_web_control.py",
                                     headers={"User-Agent": "Online4Tech-Enigma2-Plugin"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
        with open(WEB_STAMP, "w") as fh:
            fh.write(str(time.time()))
        if not data or b"ThreadingHTTPServer" not in data:
            return False
        with open(SERVER, "rb") as fh:
            current = fh.read()
        if data == current:
            return False
        compile(data.decode("utf-8"), "online_web_control.py", "exec")   # reject broken files
        tmp = SERVER + ".new"
        with open(tmp, "wb") as fh:
            fh.write(data)
        try:
            with open(SERVER + ".bak", "wb") as fh:
                fh.write(current)
        except Exception:
            pass
        os.replace(tmp, SERVER)
        if is_running():
            stop_server()
            time.sleep(1.5)
            start_server()
        return True
    except Exception as error:
        print("[OnlineWebControl] Web auto-update skipped: %s" % error)
        return False


# ---------------------------------------------------------------------------
# States of the gate
# ---------------------------------------------------------------------------
STATE_CLOSED, STATE_OPEN, STATE_OPENING, STATE_CLOSING = 0, 1, 2, 3
POLL_MS = 500
AUTO_REFRESH_MS = 2000
WAIT_OPEN_TICKS = 20    # 20 x 0.5s = 10 seconds to wait for the port to open
WAIT_CLOSE_TICKS = 10   # 10 x 0.5s = 5 seconds to wait for the port to close

HELP_H1 = "ما هو دور البلجن؟"
HELP_B1 = ("•  هو «بوابة» لوحة تحكم Online4Tech على الرسيفر.\n"
           "•  لما تفتح البوابة تقدر تدخل اللوحة من الموبايل أو الكمبيوتر.\n"
           "•  لما تقفلها اللوحة بتتوقف ومحدش يقدر يدخل عليها.")
HELP_H2 = "طريقة التشغيل"
HELP_B2 = ("أولًا:  اضغط الأخضر لفتح البوابة وانتظر لحد ما الكارت يبقى أخضر.\n"
           "ثانيًا:  من الموبايل أو الكمبيوتر على نفس الشبكة افتح الرابط الظاهر.\n"
           "ثالثًا:  لما تخلص اضغط الأحمر لقفل البوابة.")
HELP_NOTE = ("الأصفر: تحديث البلجن   •   OK: فحص الحالة   •   EXIT: خروج\n"
             "لوحة الويب بتتحدّث لوحدها من GitHub، والموبايل لازم يبقى على نفس الواي فاي.")


class OnlineWebControlHelp(Screen):
    def __init__(self, session):
        self.skin = _help_skin()
        Screen.__init__(self, session)
        if not _logo_ok():
            self["brand"] = Label("Online4Tech Web Gate")
            self["tagline"] = Label("خليك دايمًا أونلاين")
        self["h1"] = Label(HELP_H1)
        self["b1"] = Label(HELP_B1)
        self["h2"] = Label(HELP_H2)
        self["b2"] = Label(HELP_B2)
        self["note"] = Label(HELP_NOTE)
        self["hint"] = Label("اضغط أي زرار للرجوع")
        self["footer"] = Label("ONLINE4TECH  •  VERSION %s" % (VERSION or "N/A"))
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions"],
            {"ok": self.close, "cancel": self.close, "green": self.close,
             "red": self.close, "yellow": self.close, "blue": self.close},
            -1
        )


class OnlineWebControlScreen(Screen):
    def __init__(self, session):
        self.skin = _main_skin()
        Screen.__init__(self, session)
        self.session = session
        self.state = STATE_CLOSED
        self.ticks = 0

        if not _logo_ok():
            self["brand"] = Label("Online4Tech Web Gate")
            self["tagline"] = Label("خليك دايمًا أونلاين")
        self["role"] = Label("بوابة التحكم في لوحة الويب  •  افتح أو اقفل الدخول عليها بضغطة زرار")
        self["card_open"] = Label("")
        self["card_closed"] = Label("")
        self["card_wait"] = Label("")
        self["card_title"] = Label("")
        self["card_sub"] = Label("")
        self["ip_label"] = Label("IP ADDRESS")
        self["ip_value"] = Label("")
        self["port_label"] = Label("PORT")
        self["port_value"] = Label(str(PORT))
        self["url"] = Label("")
        self["green"] = Label("▶  فتح")
        self["green_off"] = Label("مفتوحة بالفعل")
        self["red"] = Label("■  قفل")
        self["red_off"] = Label("مقفولة بالفعل")
        self["chip_green"] = Label("الأخضر: فتح")
        self["chip_red"] = Label("الأحمر: قفل")
        self["chip_yellow"] = Label("الأصفر: تحديث")
        self["chip_blue"] = Label("الأزرق: شرح")
        self["hint"] = Label("")
        self.remote_version = None
        self["footer"] = Label("ONLINE4TECH  •  VERSION %s" % (VERSION or "N/A"))
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions"],
            {
                "green": self.do_open,
                "red": self.do_close,
                "yellow": self.do_update,
                "blue": self.show_help,
                "ok": self.refresh_status,
                "cancel": self.close,
            },
            -1
        )

        # One timer: polls while opening/closing, and auto-refreshes while idle
        self.timer = eTimer()
        self.timer_conn = None
        try:
            self.timer_conn = self.timer.timeout.connect(self._on_tick)
        except AttributeError:
            self.timer.callback.append(self._on_tick)

        self.onLayoutFinish.append(self._on_layout)
        self.onClose.append(self._on_close)

    # ---- lifecycle -------------------------------------------------------
    def _idle_hint(self):
        if self.remote_version and _ver_tuple(self.remote_version) > _ver_tuple(VERSION):
            return "● يوجد إصدار جديد %s — اضغط الأصفر لتحديث البلجن" % self.remote_version
        return "الأصفر: تحديث البلجن من GitHub بضغطة واحدة"

    def _check_updates(self):
        self.remote_version = get_remote_version()
        auto_update_web()

    def _on_layout(self):
        try:
            if not _logo_ok():
                threading.Thread(target=sync_brand_assets, daemon=True).start()
            threading.Thread(target=self._check_updates, daemon=True).start()
            self.refresh_status()
            self.timer.start(AUTO_REFRESH_MS, True)
        except Exception:
            _dbg("on_layout")

    def _on_close(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    # ---- state handling --------------------------------------------------
    def _set_state(self, state):
        self.state = state
        ip = get_ip()
        url = "http://%s:%d" % (ip, PORT)
        self["ip_value"].setText(ip)
        self["port_value"].setText(str(PORT))

        for name in ("card_open", "card_closed", "card_wait",
                     "green", "green_off", "red", "red_off"):
            self[name].hide()

        if state == STATE_OPEN:
            self["card_open"].show()
            self["card_title"].setText("●  البوابة مفتوحة")
            self["card_sub"].setText("اللوحة شغالة وجاهزة للدخول من أي جهاز على نفس الشبكة")
            self["url"].setText(url)
            self["green_off"].setText("مفتوحة بالفعل")
            self["green_off"].show()
            self["red"].show()
            self["hint"].setText(self._idle_hint())
        elif state == STATE_CLOSED:
            self["card_closed"].show()
            self["card_title"].setText("●  البوابة مقفولة")
            self["card_sub"].setText("اللوحة متوقفة ومفيش دخول عليها")
            self["url"].setText("اللوحة مقفولة  —  اضغط الأخضر للفتح")
            self["red_off"].setText("مقفولة بالفعل")
            self["green"].show()
            self["red_off"].show()
            self["hint"].setText(self._idle_hint())
        elif state == STATE_OPENING:
            self["card_wait"].show()
            self["card_title"].setText("◌  جاري الفتح ...")
            self["card_sub"].setText("")
            self["url"].setText(url)
            self["green_off"].setText("جاري الفتح ...")
            self["green_off"].show()
            self["red_off"].setText("مقفولة بالفعل")
            self["red_off"].show()
            self["hint"].setText("استنى لحظات لحد ما البورت يفتح")
        elif state == STATE_CLOSING:
            self["card_wait"].show()
            self["card_title"].setText("◌  جاري القفل ...")
            self["card_sub"].setText("")
            self["url"].setText(url)
            self["green_off"].setText("مفتوحة بالفعل")
            self["green_off"].show()
            self["red_off"].setText("جاري القفل ...")
            self["red_off"].show()
            self["hint"].setText("استنى لحظات لحد ما البورت يتقفل")

    def refresh_status(self):
        if self.state in (STATE_OPENING, STATE_CLOSING):
            return
        try:
            self._set_state(STATE_OPEN if is_running() else STATE_CLOSED)
        except Exception:
            _dbg("refresh_status")

    def _on_tick(self):
        try:
            if self.state == STATE_OPENING:
                self.ticks += 1
                if is_running():
                    self._set_state(STATE_OPEN)
                    self.timer.start(AUTO_REFRESH_MS, True)
                elif self.ticks >= WAIT_OPEN_TICKS:
                    self._set_state(STATE_CLOSED)
                    _show_result(self.session, "تعذر فتح اللوحة. جرّب تاني أو تأكد إن Python شغال على الرسيفر.", timeout=8)
                    self.timer.start(AUTO_REFRESH_MS, True)
                else:
                    self.timer.start(POLL_MS, True)
            elif self.state == STATE_CLOSING:
                self.ticks += 1
                if not is_running():
                    self._set_state(STATE_CLOSED)
                    self.timer.start(AUTO_REFRESH_MS, True)
                elif self.ticks >= WAIT_CLOSE_TICKS:
                    os.system("pkill -9 -f online_web_control.py >/dev/null 2>&1")
                    self.ticks = 0
                    self.timer.start(POLL_MS, True)
                else:
                    self.timer.start(POLL_MS, True)
            else:
                self.refresh_status()
                if self.remote_version and self.state in (STATE_OPEN, STATE_CLOSED):
                    self["hint"].setText(self._idle_hint())
                    self["chip_yellow"].setText("تحديث متاح ●" if _ver_tuple(self.remote_version) > _ver_tuple(VERSION) else "الأصفر: تحديث")
                self.timer.start(AUTO_REFRESH_MS, True)
        except Exception as error:
            _dbg("tick")
            print("[OnlineWebControl] Tick error: %s" % error)
            self.timer.start(AUTO_REFRESH_MS, True)

    # ---- actions ---------------------------------------------------------
    def do_open(self):
        if self.state != STATE_CLOSED:
            return
        start_server()
        self.ticks = 0
        self._set_state(STATE_OPENING)
        self.timer.start(POLL_MS, True)

    def do_close(self):
        if self.state != STATE_OPEN:
            return
        stop_server()
        self.ticks = 0
        self._set_state(STATE_CLOSING)
        self.timer.start(POLL_MS, True)

    def do_update(self):
        if self.state in (STATE_OPENING, STATE_CLOSING):
            return
        _show_result(self.session, "جاري الاتصال بمستودع GitHub وسحب آخر تحديثات Online4Tech...", timeout=3)
        update_plugin(self.session)

    def show_help(self):
        try:
            self.session.open(OnlineWebControlHelp)
        except Exception:
            _dbg("show_help")


def main(session, **kwargs):
    try:
        session.open(OnlineWebControlScreen)
    except Exception as error:
        print("[OnlineWebControl] Screen error: %s" % error)
        _show_result(session, "تعذر فتح واجهة التحكم:\n%s" % error)




def ensure_plugin_icon():
    """Create fallback icon if missing, and sync the custom O4T icon/banner once from GitHub."""
    try:
        if os.path.isfile(BRAND_ICON_PATH) and os.path.getsize(BRAND_ICON_PATH) > 0:
            _install_menu_icon(BRAND_ICON_PATH)
        if not os.path.isfile(BRAND_BANNER_PATH) or not os.path.isfile(BRAND_ICON_PATH):
            threading.Thread(target=sync_brand_assets, daemon=True).start()
    except Exception as error:
        print("[OnlineWebControl] Icon creation failed: %s" % error)


def Plugins(**kwargs):
    ensure_plugin_icon()
    threading.Thread(target=auto_update_web, daemon=True).start()
    return [PluginDescriptor(name="Online4Tech Control Center",
                             description="بوابة لوحة Online4Tech: فتح وقفل ومتابعة IP والبورت %d" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             icon=PLUGIN_ICON,
                             fnc=main)]
