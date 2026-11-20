#!/bin/sh
# Online Web Control - تثبيت على الرسيفر بأمر واحد
REPO="online4tech/webcontrol1"
BRANCH="main"
URL="https://raw.githubusercontent.com/$REPO/$BRANCH/dist/enigma2-plugin-extensions-onlinewebcontrol_all.ipk"
TMP="/tmp/onlinewebcontrol.ipk"

echo "== Online Web Control installer =="
rm -f "$TMP"
wget -q -O "$TMP" "$URL" || wget -q --no-check-certificate -O "$TMP" "$URL"
if [ ! -s "$TMP" ]; then
  echo "ERROR: download failed. Check internet / repo name."
  exit 1
fi
opkg install --force-reinstall "$TMP" || { echo "ERROR: opkg install failed"; rm -f "$TMP"; exit 1; }
rm -f "$TMP"
echo ""
echo "Done. Panel port: 7070  (login: admin / admin)"
echo "Restarting GUI in 3 seconds..."
sleep 3
killall -9 enigma2
