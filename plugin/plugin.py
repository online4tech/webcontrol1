# -*- coding: utf-8 -*-
# Online Web Control - Enigma2 plugin
# دوره فقط: تشغيل / إيقاف لوحة الويب (بورت 7070). كل التحكم الباقي داخل الصفحة.
from __future__ import print_function
import os
import signal
import socket
import subprocess

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(PLUGIN_DIR, "online_web_control.py")
PORT = 7070
PID_FILE = "/tmp/online_web_control.pid"
try:
    with open(os.path.join(PLUGIN_DIR, "VERSION")) as _f:
        VERSION = _f.read().strip()
except Exception:
    VERSION = ""


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


def _restart_gui_later():
    """Restart Enigma2 gracefully and allow enough time for the GUI to stop."""
    try:
        command = (
            "sleep 8; "
            "init 4; "
            "n=0; "
            "while pidof enigma2 >/dev/null 2>&1 && [ \"$n\" -lt 30 ]; do "
            "sleep 1; n=$((n + 1)); "
            "done; "
            "sleep 3; "
            "init 3"
        )
        subprocess.Popen(
            ["/bin/sh", "-c", command],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, close_fds=True, start_new_session=True
        )
    except Exception as error:
        print("[OnlineWebControl] GUI restart scheduling failed: %s" % error)


def update_plugin(session):
    """Fetch and safely install the latest plugin files from the official GitHub repo."""
    import tempfile
    import shutil
    import urllib.request

    base = "https://raw.githubusercontent.com/online4tech/webcontrol1/main/"
    files = {
        "plugin.py": "plugin/plugin.py",
        "online_web_control.py": "plugin/online_web_control.py",
        "__init__.py": "plugin/__init__.py",
        "VERSION": "VERSION",
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
            staged = destination + ".online4tech-new"
            shutil.copyfile(source, staged)
            os.chmod(staged, 0o644)
            os.rename(staged, destination)
            changed.append(destination)

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
        _show_result(
            session,
            "تم تحديث Online4Tech بنجاح إلى الإصدار %s.\n"
            "سيتم إعادة تشغيل واجهة Enigma2 تلقائيًا خلال ثوانٍ." % remote_version,
            timeout=7
        )
        _restart_gui_later()
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
    <screen name="OnlineWebControlScreen" position="center,center" size="760,455"
        title="Online4Tech Control Center" backgroundColor="#101820">
        <widget name="brand" position="30,18" size="700,48"
            font="Regular;32" halign="center" valign="center"
            foregroundColor="#F5C542" backgroundColor="#101820" />
        <widget name="tagline" position="30,67" size="700,28"
            font="Regular;19" halign="center" valign="center"
            foregroundColor="#D8E0E8" backgroundColor="#101820" />
        <widget name="rule" position="70,108" size="620,2"
            backgroundColor="#344451" />
        <widget name="status" position="55,128" size="650,42"
            font="Regular;22" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#1B2B38" />
        <widget name="address" position="55,176" size="650,32"
            font="Regular;18" halign="center" valign="center"
            foregroundColor="#AFC0CC" backgroundColor="#101820" />
        <widget name="hint" position="55,220" size="650,32"
            font="Regular;18" halign="center" valign="center"
            foregroundColor="#F5C542" backgroundColor="#101820" />
        <widget name="green" position="45,285" size="210,66"
            font="Regular;23" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#16834A" />
        <widget name="red" position="275,285" size="210,66"
            font="Regular;23" halign="center" valign="center"
            foregroundColor="#FFFFFF" backgroundColor="#C6283D" />
        <widget name="yellow" position="505,285" size="210,66"
            font="Regular;23" halign="center" valign="center"
            foregroundColor="#17202A" backgroundColor="#F2C230" />
        <widget name="footer" position="40,375" size="680,35"
            font="Regular;16" halign="center" valign="center"
            foregroundColor="#8D9AA5" backgroundColor="#101820" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self["brand"] = Label("ONLINE4TECH")
        self["tagline"] = Label("ONLINE TECHNOLOGY  |  SMART RECEIVER CONTROL")
        self["rule"] = Label("")
        self["status"] = Label("")
        self["address"] = Label("")
        self["hint"] = Label("استخدم أزرار الألوان في الريموت للتحكم")
        self["green"] = Label("●  تشغيل اللوحة")
        self["red"] = Label("■  إيقاف اللوحة")
        self["yellow"] = Label("↻  تحديث البلجن")
        self["footer"] = Label("OK: تحديث الحالة     |     EXIT: خروج     |     التحديث من GitHub الرسمي")
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
        self.refresh_status()

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



def Plugins(**kwargs):
    return [PluginDescriptor(name="Online4Tech Control Center",
                             description="Online4Tech receiver control and GitHub updater (port %d)" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             fnc=main)]
