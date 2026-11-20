# -*- coding: utf-8 -*-
# Online Web Control - Enigma2 plugin
# دوره فقط: تشغيل / إيقاف لوحة الويب (بورت 7070). كل التحكم الباقي داخل الصفحة.
from __future__ import print_function
import os
import signal
import socket
import subprocess

from Plugins.Plugin import PluginDescriptor

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



def main(session, **kwargs):
    """Start the local web panel without creating a custom Enigma2 screen."""
    start_server()
    try:
        from Screens.MessageBox import MessageBox
        ip = get_ip()
        message = (
            "Online Web Control\n\n"
            "لوحة التحكم قيد التشغيل أو جاري تشغيلها.\n"
            "افتح من متصفح جهازك داخل نفس الشبكة:\n\n"
            "http://%s:%d\n\n"
            "الاستخدام داخل الشبكة المحلية فقط."
        ) % (ip, PORT)
        session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=12)
    except Exception as error:
        print("[OnlineWebControl] Could not show status message: %s" % error)



def Plugins(**kwargs):
    return [PluginDescriptor(name="Online Web Control",
                             description="Open / close the Online4Tech web panel (port %d)" % PORT,
                             where=PluginDescriptor.WHERE_PLUGINMENU,
                             fnc=main)]
