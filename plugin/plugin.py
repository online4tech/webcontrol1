# -*- coding: utf-8 -*-
# Online Web Control - Enigma2 plugin
# دوره فقط: تشغيل / إيقاف لوحة الويب (بورت 7070). كل التحكم الباقي داخل الصفحة.
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
from enigma import ePicLoad

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PLUGIN_DIR, "assets")
SERVER = os.path.join(PLUGIN_DIR, "online_web_control.py")
PORT = 7070
PID_FILE = "/tmp/online_web_control.pid"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/"
BRAND_BANNER_URL = GITHUB_RAW_BASE + "assets/o4t_banner.svg"
BRAND_ICON_URL = GITHUB_RAW_BASE + "assets/o4t_icon.svg"
BRAND_BANNER_PATH = os.path.join(ASSETS_DIR, "banner.svg")
BRAND_ICON_PATH = os.path.join(ASSETS_DIR, "icon.svg")
PLUGIN_ICON = os.path.join(PLUGIN_DIR, "plugin.png")
BRAND_SYNC_FLAG = os.path.join(ASSETS_DIR, ".o4t_brand_v1")

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

        if ok_icon and (force or not os.path.isfile(BRAND_SYNC_FLAG)):
            if not os.path.isfile(PLUGIN_ICON) and _install_menu_icon(PLUGIN_ICON):
                try:
                    with open(BRAND_SYNC_FLAG, "w") as flag_f:
                        flag_f.write("ok\n")
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
        "assets/o4t_banner.svg": "assets/o4t_banner.svg",
        "assets/o4t_icon.svg": "assets/o4t_icon.svg",
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
            os.makedirs(os.path.dirname(target), exist_ok=True)
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
            os.makedirs(os.path.dirname(destination), exist_ok=True)
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


class OnlineWebControlScreen(Screen):
    skin = """
    <screen name="OnlineWebControlScreen" position="center,center" size="820,500"
        title="Online4Tech Control Center" flags="wfNoBorder" backgroundColor="#07111F">
        <!-- Outer accent border -->
        <eLabel position="0,0" size="820,4" backgroundColor="#28B5F6" />
        <eLabel position="0,498" size="820,2" backgroundColor="#1E4E79" />
        <eLabel position="0,0" size="2,500" backgroundColor="#1E4E79" />
        <eLabel position="818,0" size="2,500" backgroundColor="#1E4E79" />

        <!-- Header block with custom Online4Tech banner -->
        <eLabel position="2,4" size="816,154" backgroundColor="#0B192C" />
        <widget name="banner" position="160,14" size="500,108" alphatest="blend" />
        <widget name="brand" position="40,26" size="740,56"
            font="Regular;38" halign="center" valign="center"
            foregroundColor="#38BDF8" backgroundColor="#0B192C" />
        <widget name="tagline" position="40,124" size="740,28"
            font="Regular;18" halign="center" valign="center"
            foregroundColor="#9CC2E5" backgroundColor="#0B192C" />
        <eLabel position="40,158" size="740,2" backgroundColor="#1D4265" />

        <!-- Status & Address card -->
        <eLabel position="48,176" size="724,108" backgroundColor="#0E2036" />
        <eLabel position="48,176" size="724,2" backgroundColor="#224C73" />
        <widget name="status" position="64,186" size="692,42"
            font="Regular;24" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#0E2036" />
        <widget name="address" position="64,234" size="692,38"
            font="Regular;22" halign="center" valign="center"
            foregroundColor="#67D2FF" backgroundColor="#0E2036" />

        <!-- Version & Hint -->
        <widget name="hint" position="48,298" size="724,32"
            font="Regular;18" halign="center" valign="center"
            foregroundColor="#F5C542" backgroundColor="#07111F" />

        <!-- Color Action Buttons -->
        <eLabel position="48,342" size="228,4" backgroundColor="#34D399" />
        <widget name="green" position="48,346" size="228,68"
            font="Regular;22" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#12804D" />

        <eLabel position="296,342" size="228,4" backgroundColor="#FB7185" />
        <widget name="red" position="296,346" size="228,68"
            font="Regular;22" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#BE263E" />

        <eLabel position="544,342" size="228,4" backgroundColor="#FDE047" />
        <widget name="yellow" position="544,346" size="228,68"
            font="Regular;20" halign="center" valign="center"
            foregroundColor="#0B131E" backgroundColor="#EAB308" />

        <!-- Footer -->
        <eLabel position="2,444" size="816,54" backgroundColor="#0B192C" />
        <eLabel position="2,444" size="816,1" backgroundColor="#1D4265" />
        <widget name="footer" position="30,452" size="760,38"
            font="Regular;17" halign="center" valign="center"
            foregroundColor="#8BA6C0" backgroundColor="#0B192C" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self["banner"] = Pixmap()
        self["brand"] = Label("ONLINE4TECH")
        self["tagline"] = Label("ONLINE TECHNOLOGY  •  SMART RECEIVER CONTROL")
        self["status"] = Label("")
        self["address"] = Label("")
        self["hint"] = Label("استخدم أزرار الألوان في الريموت للتحكم")
        self["green"] = Label("●  تشغيل اللوحة")
        self["red"] = Label("■  إيقاف اللوحة")
        self["yellow"] = Label("↻  تحديث + ريستارت")
        self["footer"] = Label("OK: تحديث الحالة     •     EXIT: خروج     •     التحديث من GitHub الرسمي")
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions"],
            {
                "green": self.do_start,
                "red": self.do_stop,
                "yellow": self.do_update,
                "ok": self.refresh_status,
                "cancel": self.close,
            },
            -1
        )
        self.picload = ePicLoad()
        self.picload_conn = None
        try:
            self.picload_conn = self.picload.PictureData.connect(self._on_banner_decoded)
        except AttributeError:
            self.picload.PictureData.get().append(self._on_banner_decoded)
        self.onLayoutFinish.append(self._load_banner)
        self.refresh_status()

    def _load_banner(self):
        try:
            self["banner"].hide()
            if not os.path.isfile(BRAND_BANNER_PATH) or os.path.getsize(BRAND_BANNER_PATH) == 0:
                threading.Thread(target=sync_brand_assets, daemon=True).start()
                return
            w = self["banner"].instance.size().width()
            h = self["banner"].instance.size().height()
            self.picload.setPara((w, h, 1, 1, False, 1, "#0B192C"))
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
        except Exception as error:
            print("[OnlineWebControl] Banner render error: %s" % error)

    def refresh_status(self):
        running = is_running()
        state = "● اللوحة تعمل الآن" if running else "● اللوحة متوقفة"
        self["status"].setText(state)
        self["address"].setText("رابط اللوحة: http://%s:%d" % (get_ip(), PORT))
        self["hint"].setText("الإصدار %s  |  تشغيل أخضر  •  إيقاف أحمر  •  تحديث أصفر" % (VERSION or "غير معروف"))

    def do_start(self):
        start_server()
        self.refresh_status()
        _show_result(self.session, "تم إرسال أمر تشغيل لوحة Online4Tech.")

    def do_stop(self):
        stop_server()
        self.refresh_status()
        _show_result(self.session, "تم إيقاف لوحة Online4Tech.")

    def do_update(self):
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
        if not os.path.isfile(PLUGIN_ICON):
            with open(PLUGIN_ICON, "wb") as icon_file:
                icon_file.write(base64.b64decode(_PLUGIN_ICON_B64))
            os.chmod(PLUGIN_ICON, 0o644)
        if not os.path.isfile(BRAND_SYNC_FLAG) or not os.path.isfile(BRAND_BANNER_PATH):
            threading.Thread(target=sync_brand_assets, daemon=True).start()
    except Exception as error:
        print("[OnlineWebControl] Icon creation failed: %s" % error)


def Plugins(**kwargs):
    ensure_plugin_icon()
    return [PluginDescriptor(name="Online4Tech Control Center",
                             description="Online4Tech receiver control and GitHub updater (port %d)" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             icon=PLUGIN_ICON,
                             fnc=main)]
