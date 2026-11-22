# -*- coding: utf-8 -*-
# Online Web Control - Enigma2 plugin
# بوابة لوحة الويب (بورت 7070): أخضر = فتح، أحمر = قفل، مع عرض الحالة والـ IP والـ PORT.
from __future__ import print_function
import os
import base64
import signal
import socket
import subprocess
import threading

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from enigma import ePicLoad, eTimer

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PLUGIN_DIR, "assets")
SERVER = os.path.join(PLUGIN_DIR, "online_web_control.py")
PORT = 7070
PID_FILE = "/tmp/online_web_control.pid"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/"
BRAND_BANNER_URL = GITHUB_RAW_BASE + "assets/o4t-main-logo.png"
BRAND_ICON_URL = GITHUB_RAW_BASE + "assets/o4t-icon.png"
BRAND_BANNER_PATH = os.path.join(ASSETS_DIR, "o4t-main-logo.png")
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


# ---------------------------------------------------------------------------
# Gate screen: shows OPEN / CLOSED state of the web panel, with IP and port.
# GREEN = open (start), RED = close (stop), YELLOW = update, OK = refresh.
# ---------------------------------------------------------------------------
DEBUG_LOG = "/tmp/owc_debug.log"


def _dbg(where):
    """Write the last Python error to /tmp/owc_debug.log (for troubleshooting)."""
    try:
        import traceback
        with open(DEBUG_LOG, "a") as fh:
            fh.write("== %s ==\n%s\n" % (where, traceback.format_exc()))
    except Exception:
        pass


STATE_CLOSED, STATE_OPEN, STATE_OPENING, STATE_CLOSING = 0, 1, 2, 3
POLL_MS = 500
AUTO_REFRESH_MS = 2000
WAIT_OPEN_TICKS = 20    # 20 x 0.5s = 10 seconds to wait for the port to open
WAIT_CLOSE_TICKS = 10   # 10 x 0.5s = 5 seconds to wait for the port to close


class OnlineWebControlScreen(Screen):
    skin = """
    <screen name="OnlineWebControlScreen" position="center,center" size="800,600"
        title="Online4Tech Web Gate" flags="wfNoBorder" backgroundColor="#061426">
        <eLabel zPosition="0" position="0,0" size="800,600" backgroundColor="#061426" />
        <eLabel zPosition="1" position="0,0" size="800,5" backgroundColor="#00C8F0" />
        <eLabel zPosition="1" position="0,593" size="800,7" backgroundColor="#087EBA" />

        <!-- Header -->
        <eLabel zPosition="1" position="18,17" size="764,110" backgroundColor="#0B2038" />
        <widget zPosition="2" name="banner" position="112,22" size="576,100" alphatest="blend" />
        <widget zPosition="2" name="brand" position="45,35" size="710,45" font="Regular;32" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#0B2038" />
        <widget zPosition="2" name="tagline" position="45,82" size="710,30" font="Regular;20" halign="center" valign="center" foregroundColor="#42D7FF" backgroundColor="#0B2038" />

        <!-- Gate status card (only one of the four is visible at a time) -->
        <widget zPosition="2" name="card_open" position="28,142" size="744,96" font="Regular;34" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#0E8F63" />
        <widget zPosition="2" name="card_closed" position="28,142" size="744,96" font="Regular;34" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#B5233F" />
        <widget zPosition="2" name="card_wait" position="28,142" size="744,96" font="Regular;34" halign="center" valign="center" foregroundColor="#152238" backgroundColor="#E8B323" />
        <widget zPosition="2" name="card_sub" position="28,208" size="744,28" font="Regular;17" halign="center" valign="center" foregroundColor="#FFFFFF" transparent="1" />

        <!-- IP / Port -->
        <eLabel zPosition="1" position="28,252" size="364,70" backgroundColor="#123654" />
        <eLabel zPosition="1" position="408,252" size="364,70" backgroundColor="#123654" />
        <widget zPosition="2" name="ip_label" position="38,256" size="344,22" font="Regular;15" halign="center" valign="center" foregroundColor="#83B6D8" backgroundColor="#123654" />
        <widget zPosition="2" name="ip_value" position="38,278" size="344,38" font="Regular;30" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#123654" />
        <widget zPosition="2" name="port_label" position="418,256" size="344,22" font="Regular;15" halign="center" valign="center" foregroundColor="#83B6D8" backgroundColor="#123654" />
        <widget zPosition="2" name="port_value" position="418,278" size="344,38" font="Regular;30" halign="center" valign="center" foregroundColor="#55D7FF" backgroundColor="#123654" />

        <!-- Full URL -->
        <eLabel zPosition="1" position="28,336" size="744,52" backgroundColor="#0A1C30" />
        <widget zPosition="2" name="url" position="38,340" size="724,44" font="Regular;26" halign="center" valign="center" foregroundColor="#D7EAF8" backgroundColor="#0A1C30" />

        <!-- Gate buttons: bright when usable, dim when not applicable -->
        <widget zPosition="2" name="green" position="28,410" size="364,86" font="Regular;28" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#10A875" />
        <widget zPosition="2" name="green_off" position="28,410" size="364,86" font="Regular;24" halign="center" valign="center" foregroundColor="#6F9A8C" backgroundColor="#0C3A2E" />
        <widget zPosition="2" name="red" position="408,410" size="364,86" font="Regular;28" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="#D52C55" />
        <widget zPosition="2" name="red_off" position="408,410" size="364,86" font="Regular;24" halign="center" valign="center" foregroundColor="#A07582" backgroundColor="#40161F" />

        <widget zPosition="2" name="hint" position="30,512" size="740,28" font="Regular;16" halign="center" valign="center" foregroundColor="#9DBFD8" backgroundColor="#061426" />
        <widget zPosition="2" name="footer" position="30,560" size="740,24" font="Regular;13" halign="center" valign="center" foregroundColor="#4E7899" backgroundColor="#061426" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.state = STATE_CLOSED
        self.ticks = 0
        self.target_open = None

        self["banner"] = Pixmap()
        self["brand"] = Label("Online4Tech Web Gate")
        self["tagline"] = Label("خليك دايمًا أونلاين")
        self["card_open"] = Label("●  البوابة مفتوحة")
        self["card_closed"] = Label("●  البوابة مقفولة")
        self["card_wait"] = Label("")
        self["card_sub"] = Label("")
        self["ip_label"] = Label("IP الرسيفر")
        self["ip_value"] = Label("")
        self["port_label"] = Label("PORT")
        self["port_value"] = Label(str(PORT))
        self["url"] = Label("")
        self["green"] = Label("▶  فتح")
        self["green_off"] = Label("مفتوحة بالفعل")
        self["red"] = Label("■  قفل")
        self["red_off"] = Label("مقفولة بالفعل")
        self["hint"] = Label("")
        self["footer"] = Label("ONLINE4TECH  •  VERSION %s" % (VERSION or "N/A"))
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions"],
            {
                "green": self.do_open,
                "red": self.do_close,
                "yellow": self.do_update,
                "ok": self.refresh_status,
                "cancel": self.close,
            },
            -1
        )

        # Banner loader
        self.picload = ePicLoad()
        self.picload_conn = None
        try:
            self.picload_conn = self.picload.PictureData.connect(self._on_banner_decoded)
        except AttributeError:
            self.picload.PictureData.get().append(self._on_banner_decoded)

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
    def _on_layout(self):
        try:
            self._load_banner()
            self.refresh_status()
            self.timer.start(AUTO_REFRESH_MS, True)
        except Exception:
            _dbg("on_layout")

    def _on_close(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    # ---- banner ----------------------------------------------------------
    def _load_banner(self):
        try:
            self["banner"].hide()
            if not os.path.isfile(BRAND_BANNER_PATH) or os.path.getsize(BRAND_BANNER_PATH) == 0:
                threading.Thread(target=sync_brand_assets, daemon=True).start()
                return
            w = self["banner"].instance.size().width()
            h = self["banner"].instance.size().height()
            self.picload.setPara((w, h, 1, 1, False, 1, "#0B2038"))
            self.picload.startDecode(BRAND_BANNER_PATH)
        except Exception as error:
            print("[OnlineWebControl] Banner load error: %s" % error)

    def _on_banner_decoded(self, picInfo=None):
        try:
            ptr = self.picload.getData()
            if ptr is not None:
                self["banner"].instance.setPixmap(ptr)
                self["banner"].show()
                self["brand"].hide()
                self["tagline"].hide()
        except Exception as error:
            print("[OnlineWebControl] Banner render error: %s" % error)

    # ---- state handling --------------------------------------------------
    def _set_state(self, state):
        self.state = state
        ip = get_ip()
        url = "http://%s:%d" % (ip, PORT)
        self["ip_value"].setText(ip)
        self["port_value"].setText(str(PORT))

        for name in ("card_open", "card_closed", "card_wait"):
            self[name].hide()
        for name in ("green", "green_off", "red", "red_off"):
            self[name].hide()

        if state == STATE_OPEN:
            self["card_open"].show()
            self["card_sub"].setText("اللوحة شغالة وجاهزة للدخول من أي جهاز على نفس الشبكة")
            self["url"].setText(url)
            self["green_off"].show()
            self["red"].show()
            self["hint"].setText("الأحمر: قفل البوابة   •   الأصفر: تحديث   •   OK: فحص الحالة")
        elif state == STATE_CLOSED:
            self["card_closed"].show()
            self["card_sub"].setText("اللوحة متوقفة ومفيش دخول عليها")
            self["url"].setText("اللوحة مقفولة  —  اضغط الأخضر للفتح")
            self["green"].show()
            self["red_off"].show()
            self["hint"].setText("الأخضر: فتح البوابة   •   الأصفر: تحديث   •   OK: فحص الحالة")
        elif state == STATE_OPENING:
            self["card_wait"].setText("◌  جاري الفتح ...")
            self["card_wait"].show()
            self["card_sub"].setText("")
            self["url"].setText(url)
            self["green_off"].setText("جاري الفتح ...")
            self["green_off"].show()
            self["red_off"].show()
            self["hint"].setText("استنى لحظات لحد ما البورت يفتح")
        elif state == STATE_CLOSING:
            self["card_wait"].setText("◌  جاري القفل ...")
            self["card_wait"].show()
            self["card_sub"].setText("")
            self["url"].setText(url)
            self["green_off"].setText("مفتوحة بالفعل")
            self["green_off"].show()
            self["red_off"].setText("جاري القفل ...")
            self["red_off"].show()
            self["hint"].setText("استنى لحظات لحد ما البورت يتقفل")
        if state != STATE_CLOSING:
            self["red_off"].setText("مقفولة بالفعل")
        if state != STATE_OPENING:
            self["green_off"].setText("مفتوحة بالفعل")

    def refresh_status(self):
        if self.state in (STATE_OPENING, STATE_CLOSING):
            return
        self._set_state(STATE_OPEN if is_running() else STATE_CLOSED)

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


def main(session, **kwargs):
    try:
        session.open(OnlineWebControlScreen)
    except Exception as error:
        print("[OnlineWebControl] Screen error: %s" % error)
        _show_result(session, "تعذر فتح واجهة التحكم:\n%s" % error)


_PLUGIN_ICON_B64 = "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"


def ensure_plugin_icon():
    """Create fallback icon if missing, and sync the custom O4T icon/banner once from GitHub."""
    try:
        if os.path.isfile(BRAND_ICON_PATH) and os.path.getsize(BRAND_ICON_PATH) > 0:
            _install_menu_icon(BRAND_ICON_PATH)
        elif not os.path.isfile(PLUGIN_ICON):
            with open(PLUGIN_ICON, "wb") as icon_file:
                icon_file.write(base64.b64decode(_PLUGIN_ICON_B64))
            os.chmod(PLUGIN_ICON, 0o644)
        if not os.path.isfile(BRAND_BANNER_PATH) or not os.path.isfile(BRAND_ICON_PATH):
            threading.Thread(target=sync_brand_assets, daemon=True).start()
    except Exception as error:
        print("[OnlineWebControl] Icon creation failed: %s" % error)


def Plugins(**kwargs):
    ensure_plugin_icon()
    return [PluginDescriptor(name="Online4Tech Control Center",
                             description="بوابة لوحة Online4Tech: فتح وقفل ومتابعة IP والبورت %d" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             icon=PLUGIN_ICON,
                             fnc=main)]
