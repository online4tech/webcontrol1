#!/bin/sh
# Online Web Control - direct source installer for Enigma2 (no IPK required)
set -e

REPO_BASE="https://raw.githubusercontent.com/online4tech/webcontrol1/main"
PLUGIN_DIR="/usr/lib/enigma2/python/Plugins/Extensions/OnlineWebControl"
AUTH_FILE="/etc/enigma2/online_web_control.auth"
TMP_DIR="/tmp/onlinewebcontrol-install-$$"

umask 077
mkdir -p "$TMP_DIR"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT HUP INT TERM

download_file() {
    remote="$1"
    local_file="$2"
    if ! wget -q -O "$local_file" "$remote"; then
        wget --no-check-certificate -q -O "$local_file" "$remote" || return 1
    fi
    [ -s "$local_file" ]
}

echo "== Online Web Control: direct installation =="

# Verify Python 3 before changing the receiver.
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1 && python -c 'import http.server' >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python 3 is required. No files were installed."
    exit 1
fi

echo "[1/3] Downloading plugin files..."
download_file "$REPO_BASE/plugin/plugin.py" "$TMP_DIR/plugin.py" || { echo "ERROR: plugin.py download failed"; exit 1; }
download_file "$REPO_BASE/plugin/online_web_control.py" "$TMP_DIR/online_web_control.py" || { echo "ERROR: online_web_control.py download failed"; exit 1; }
download_file "$REPO_BASE/plugin/__init__.py" "$TMP_DIR/__init__.py" || { echo "ERROR: __init__.py download failed"; exit 1; }
download_file "$REPO_BASE/VERSION" "$TMP_DIR/VERSION" || { echo "ERROR: VERSION download failed"; exit 1; }

echo "[2/3] Installing files..."
mkdir -p "$PLUGIN_DIR" /etc/enigma2
cp "$TMP_DIR/plugin.py" "$PLUGIN_DIR/plugin.py"
cp "$TMP_DIR/online_web_control.py" "$PLUGIN_DIR/online_web_control.py"
cp "$TMP_DIR/__init__.py" "$PLUGIN_DIR/__init__.py"
cp "$TMP_DIR/VERSION" "$PLUGIN_DIR/VERSION"
chmod 644 "$PLUGIN_DIR/plugin.py" "$PLUGIN_DIR/online_web_control.py" "$PLUGIN_DIR/__init__.py" "$PLUGIN_DIR/VERSION"

# Keep existing credentials; otherwise create a unique password on this receiver.
if [ ! -s "$AUTH_FILE" ]; then
    AUTH_PASS="$("$PYTHON_BIN" -c 'import binascii, os; print(binascii.hexlify(os.urandom(24)).decode("ascii"))' 2>/dev/null)"
    case "$AUTH_PASS" in
        ""|*[!0-9a-f]*) echo "ERROR: secure password generation failed. No credentials were written."; exit 1 ;;
    esac
    [ "${#AUTH_PASS}" -eq 48 ] || { echo "ERROR: generated password has an invalid length. No credentials were written."; exit 1; }
    {
        echo "online4tech"
        echo "$AUTH_PASS"
    } > "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
    echo "[3/3] Installation complete."
    echo ""
    echo "Panel username: online4tech"
    echo "Panel password: $AUTH_PASS"
    echo "Save this password now; it is stored locally on this receiver only."
else
    chmod 600 "$AUTH_FILE"
    echo "[3/3] Installation complete. Existing panel credentials were preserved."
    echo "Panel username: $(sed -n '1p' "$AUTH_FILE")"
    echo "Panel password: $(sed -n '2p' "$AUTH_FILE")"
fi

echo ""
echo "Plugin path: $PLUGIN_DIR"
echo "Panel port: 7070"
echo "Python: $PYTHON_BIN"
echo ""
echo "Restart the Enigma2 GUI from the receiver menu to show the plugin."
echo "Then open: http://RECEIVER-IP:7070"
echo "Security: keep port 7070 on your trusted local network; do not expose it to the Internet."
