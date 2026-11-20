#!/bin/sh
# يبني ملف ipk جديد داخل dist/  (الاستخدام: ./build_ipk.sh)
set -e
cd "$(dirname "$0")"
ROOT=$(pwd)
VER=$(cat VERSION)
PKG=enigma2-plugin-extensions-onlinewebcontrol
B=$(mktemp -d)
D=$B/data/usr/lib/enigma2/python/Plugins/Extensions/OnlineWebControl
mkdir -p "$D" "$B/control" dist
cp plugin/*.py VERSION "$D/"

cat > "$B/control/control" <<EOT
Package: $PKG
Version: $VER
Architecture: all
Section: extra
Priority: optional
Maintainer: Online4Tech
Homepage: https://github.com/YOUR_USER/OnlineWebControl
Description: Online Web Control - Enigma2 web panel (port 7070) with start/stop plugin
EOT

cat > "$B/control/postinst" <<'EOT'
#!/bin/sh
echo ""
echo "Online Web Control installed. Restart the GUI to see the plugin."
exit 0
EOT
cat > "$B/control/prerm" <<'EOT'
#!/bin/sh
pkill -f online_web_control.py >/dev/null 2>&1
exit 0
EOT
chmod 755 "$B/control/postinst" "$B/control/prerm"

echo "2.0" > "$B/debian-binary"
tar --owner=0 --group=0 -czf "$B/control.tar.gz" -C "$B/control" .
tar --owner=0 --group=0 -czf "$B/data.tar.gz" -C "$B/data" .
OUT="$ROOT/dist/${PKG}_all.ipk"
rm -f "$OUT"
( cd "$B" && ar -r "$OUT" debian-binary control.tar.gz data.tar.gz >/dev/null 2>&1 )
rm -rf "$B"
echo "Built dist/${PKG}_all.ipk (v$VER)"
