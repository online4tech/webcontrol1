#!/bin/sh
# Online Web Control - direct source installer for Enigma2 (no IPK, no password)
set -e

REPO_BASE="https://raw.githubusercontent.com/online4tech/webcontrol1/main"
PLUGIN_DIR="/usr/lib/enigma2/python/Plugins/Extensions/OnlineWebControl"
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

echo "== Online Web Control: local-network installation =="

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python is required. No plugin files were installed."
    exit 1
fi

echo "[1/2] Downloading plugin files..."
download_file "$REPO_BASE/plugin/plugin.py" "$TMP_DIR/plugin.py" || { echo "ERROR: plugin.py download failed"; exit 1; }
download_file "$REPO_BASE/plugin/online_web_control.py" "$TMP_DIR/online_web_control.py" || { echo "ERROR: online_web_control.py download failed"; exit 1; }
download_file "$REPO_BASE/plugin/__init__.py" "$TMP_DIR/__init__.py" || { echo "ERROR: __init__.py download failed"; exit 1; }
download_file "$REPO_BASE/VERSION" "$TMP_DIR/VERSION" || { echo "ERROR: VERSION download failed"; exit 1; }
mkdir -p "$TMP_DIR/assets"
download_file "$REPO_BASE/assets/o4t_banner.svg" "$TMP_DIR/assets/o4t_banner.svg" || { echo "ERROR: Online4Tech banner download failed"; exit 1; }
download_file "$REPO_BASE/assets/o4t_icon.svg" "$TMP_DIR/assets/o4t_icon.svg" || { echo "ERROR: Online4Tech icon download failed"; exit 1; }

echo "[2/2] Installing plugin files and Online4Tech branding..."
mkdir -p "$PLUGIN_DIR"
cp "$TMP_DIR/plugin.py" "$PLUGIN_DIR/plugin.py"
cp "$TMP_DIR/online_web_control.py" "$PLUGIN_DIR/online_web_control.py"
cp "$TMP_DIR/__init__.py" "$PLUGIN_DIR/__init__.py"
cp "$TMP_DIR/VERSION" "$PLUGIN_DIR/VERSION"
mkdir -p "$PLUGIN_DIR/assets"
cp "$TMP_DIR/assets/o4t_banner.svg" "$PLUGIN_DIR/assets/o4t_banner.svg"
cp "$TMP_DIR/assets/o4t_icon.svg" "$PLUGIN_DIR/assets/o4t_icon.svg"
chmod 644 "$PLUGIN_DIR/plugin.py" "$PLUGIN_DIR/online_web_control.py" "$PLUGIN_DIR/__init__.py" "$PLUGIN_DIR/VERSION" "$PLUGIN_DIR/assets/o4t_banner.svg" "$PLUGIN_DIR/assets/o4t_icon.svg"

echo "Installation complete."
echo "Login/password: not required (local network use)."
echo "Plugin path: $PLUGIN_DIR"
echo "Panel port: 7070"
echo "Python: $PYTHON_BIN"
echo ""
echo "Enigma2 GUI restart will start automatically in a few seconds."
echo "Then open: http://RECEIVER-IP:7070"
echo "Security: anyone on your local network may access and control this panel. Do not expose port 7070 to the Internet."

# Restart only the Enigma2 GUI (not the whole receiver), after this installer exits.
if command -v init >/dev/null 2>&1; then
    (
        sleep 3
        init 4
        sleep 3
        init 3
    ) >/dev/null 2>&1 </dev/null &
    echo "Automatic GUI restart scheduled (init 4 -> init 3)."
else
    echo "WARNING: init command not found; please restart the Enigma2 GUI manually."
fi
