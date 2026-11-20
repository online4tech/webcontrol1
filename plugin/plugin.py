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
from enigma import eTimer

try:
    from skin import parseColor
except Exception:
    parseColor = None

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


class OnlineWebControlScreen(Screen):
    skin = """
    <screen name="OnlineWebControl" position="center,center" size="760,400" title="Online Web Control" backgroundColor="#0b0b0b">
        <eLabel position="0,0" size="760,74" backgroundColor="#1a1400" zPosition="-1" />
        <eLabel position="0,74" size="760,2" backgroundColor="#f5b800" zPosition="-1" />
        <widget name="title" position="20,10" size="720,56" font="Regular;34" foregroundColor="#f5b800" backgroundColor="#1a1400" transparent="1" halign="center" valign="center" />

        <eLabel text="IP" position="60,105" size="180,40" font="Regular;28" foregroundColor="#9a9a9a" transparent="1" />
        <widget name="ip" position="250,105" size="460,40" font="Regular;30" foregroundColor="#ffffff" transparent="1" />

        <eLabel text="Port" position="60,155" size="180,40" font="Regular;28" foregroundColor="#9a9a9a" transparent="1" />
        <widget name="port" position="250,155" size="460,40" font="Regular;30" foregroundColor="#ffffff" transparent="1" />

        <eLabel text="Status" position="60,205" size="180,40" font="Regular;28" foregroundColor="#9a9a9a" transparent="1" />
        <widget name="status" position="250,205" size="460,40" font="Regular;30" foregroundColor="#ffffff" transparent="1" />

        <widget name="url" position="30,262" size="700,40" font="Regular;28" foregroundColor="#f5b800" transparent="1" halign="center" />

        <eLabel position="80,345" size="260,6" backgroundColor="#10b981" />
        <eLabel position="420,345" size="260,6" backgroundColor="#ef4444" />
        <widget name="key_green" position="80,355" size="260,34" font="Regular;26" foregroundColor="#ffffff" transparent="1" halign="center" />
        <widget name="key_red" position="420,355" size="260,34" font="Regular;26" foregroundColor="#ffffff" transparent="1" halign="center" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self["title"] = Label("Online Web Control" + ((" v" + VERSION) if VERSION else ""))
        self["ip"] = Label("")
        self["port"] = Label(str(PORT))
        self["status"] = Label("")
        self["url"] = Label("")
        self["key_green"] = Label("Open (Start)")
        self["key_red"] = Label("Close (Stop)")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {"cancel": self.close, "ok": self.toggle, "green": self.start, "red": self.stop}, -1)

        self.timer = eTimer()
        try:
            self.timer.callback.append(self.refresh)
        except Exception:
            self._conn = self.timer.timeout.connect(self.refresh)
        self.once = eTimer()
        try:
            self.once.callback.append(self.refresh)
        except Exception:
            self._conn2 = self.once.timeout.connect(self.refresh)
        self.onLayoutFinish.append(self.refresh)
        self.onLayoutFinish.append(lambda: self.timer.start(3000, False))
        self.onClose.append(self.timer.stop)

    def _color(self, name, hexcolor):
        try:
            self[name].instance.setForegroundColor(parseColor(hexcolor))
        except Exception:
            pass

    def refresh(self):
        ip = get_ip()
        self["ip"].setText(ip)
        if is_running():
            self["status"].setText("Open")
            self._color("status", "#10b981")
            self["url"].setText("http://%s:%d" % (ip, PORT))
        else:
            self["status"].setText("Closed")
            self._color("status", "#ef4444")
            self["url"].setText("")

    def start(self):
        start_server()
        self["status"].setText("Opening...")
        self.once.start(1500, True)

    def stop(self):
        stop_server()
        self["status"].setText("Closing...")
        self.once.start(1500, True)

    def toggle(self):
        if is_running():
            self.stop()
        else:
            self.start()


def main(session, **kwargs):
    session.open(OnlineWebControlScreen)


def Plugins(**kwargs):
    return [PluginDescriptor(name="Online Web Control",
                             description="Open / close the Online4Tech web panel (port %d)" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             fnc=main)]
