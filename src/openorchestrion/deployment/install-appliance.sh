#!/bin/sh
set -eu

MODE=headless
KIOSK_USER=
PACKAGE_SPEC=.
WITH_OPENAI=0
SERVICE_USER=openorchestrion
INSTALL_ROOT=/opt/openorchestrion
VENV="$INSTALL_ROOT/venv"
CONFIG_DIR=/etc/openorchestrion
STATE_DIR=/var/lib/openorchestrion

usage() {
    cat <<'EOF'
Usage: install-appliance.sh [options]

Options:
  --package PATH_OR_SPEC   Checkout, wheel, or pip package spec (default: .)
  --mode headless|kiosk    Install backend only or backend + desktop kiosk
  --kiosk-user USER        Desktop login that should autostart the kiosk
  --with-openai            Install optional OpenAI SDK for hosted Concierge
  -h, --help               Show this help

The script is intentionally safe to re-run for updates. It preserves existing
configuration/secrets under /etc/openorchestrion and all data under
/var/lib/openorchestrion.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --package)
            [ "$#" -ge 2 ] || { echo "--package needs a value" >&2; exit 2; }
            PACKAGE_SPEC=$2
            shift 2
            ;;
        --mode)
            [ "$#" -ge 2 ] || { echo "--mode needs a value" >&2; exit 2; }
            MODE=$2
            shift 2
            ;;
        --kiosk-user)
            [ "$#" -ge 2 ] || { echo "--kiosk-user needs a value" >&2; exit 2; }
            KIOSK_USER=$2
            shift 2
            ;;
        --with-openai)
            WITH_OPENAI=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "run this installer as root (sudo)" >&2; exit 2; }
case "$MODE" in
    headless|kiosk) ;;
    *) echo "--mode must be headless or kiosk" >&2; exit 2 ;;
esac
if [ "$MODE" = kiosk ] && [ -z "$KIOSK_USER" ]; then
    echo "--kiosk-user is required for kiosk mode" >&2
    exit 2
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 2; }
command -v systemctl >/dev/null 2>&1 || { echo "systemd is required" >&2; exit 2; }

# Resolve local package paths before changing directories. Non-path values are
# left alone so a packaged wheel/spec can still be supplied.
if [ -e "$PACKAGE_SPEC" ]; then
    PACKAGE_SPEC=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$PACKAGE_SPEC")
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
if getent group audio >/dev/null 2>&1; then
    usermod -a -G audio "$SERVICE_USER"
fi

install -d -m 0755 "$INSTALL_ROOT"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR/library"
install -d -m 0755 "$CONFIG_DIR"

# An update must not replace package files underneath a live playback process.
# A normal systemd stop runs FastAPI's graceful shutdown and closes the active
# history attempt before the virtual environment is modified.
if systemctl is-active --quiet openorchestrion.service 2>/dev/null; then
    echo "stopping running OpenOrchestrion for update"
    systemctl stop openorchestrion.service
fi

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install --upgrade "$PACKAGE_SPEC"
if [ "$WITH_OPENAI" -eq 1 ]; then
    "$VENV/bin/python" -m pip install --upgrade "openai>=2.0"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
"$VENV/bin/openorchestrion-deploy" --output-dir "$TMP"

install -m 0644 "$TMP/openorchestrion.service" /etc/systemd/system/openorchestrion.service
if [ ! -f "$CONFIG_DIR/openorchestrion.env" ]; then
    # This reference env file contains paths/network/runtime flags only. It is
    # intentionally readable by the desktop kiosk and smoke command.
    install -m 0644 -o root -g root \
        "$TMP/openorchestrion.env" "$CONFIG_DIR/openorchestrion.env"
else
    echo "preserving existing $CONFIG_DIR/openorchestrion.env"
    chmod 0644 "$CONFIG_DIR/openorchestrion.env"
fi

# Hosted-provider credentials are service-only. The installer never asks for or
# prints an API key; the operator edits this file explicitly after installation.
SECRETS="$CONFIG_DIR/openorchestrion.secrets.env"
if [ ! -f "$SECRETS" ]; then
    install -m 0640 -o root -g "$SERVICE_USER" /dev/null "$SECRETS"
else
    echo "preserving existing $SECRETS"
    chown root:"$SERVICE_USER" "$SECRETS"
    chmod 0640 "$SECRETS"
fi

if [ "$MODE" = kiosk ]; then
    getent passwd "$KIOSK_USER" >/dev/null 2>&1 || {
        echo "unknown --kiosk-user: $KIOSK_USER" >&2
        exit 2
    }
    HOME_DIR=$(getent passwd "$KIOSK_USER" | cut -d: -f6)
    GROUP_NAME=$(id -gn "$KIOSK_USER")
    AUTOSTART="$HOME_DIR/.config/autostart"
    install -d -m 0755 -o "$KIOSK_USER" -g "$GROUP_NAME" "$AUTOSTART"
    install -m 0644 -o "$KIOSK_USER" -g "$GROUP_NAME" \
        "$TMP/openorchestrion-kiosk.desktop" "$AUTOSTART/openorchestrion-kiosk.desktop"
else
    # Switching an existing kiosk installation to headless should really stop
    # launching Chromium rather than leave a stale desktop entry behind.
    if [ -n "$KIOSK_USER" ] && getent passwd "$KIOSK_USER" >/dev/null 2>&1; then
        HOME_DIR=$(getent passwd "$KIOSK_USER" | cut -d: -f6)
        rm -f "$HOME_DIR/.config/autostart/openorchestrion-kiosk.desktop"
    fi
fi

systemctl daemon-reload
systemctl enable openorchestrion.service
systemctl restart openorchestrion.service

echo
echo "OpenOrchestrion installed in $VENV"
echo "Configuration: $CONFIG_DIR/openorchestrion.env"
echo "Service secrets: $SECRETS"
echo "Durable data: $STATE_DIR"
echo "Logs: journalctl -u openorchestrion.service"
echo "Smoke check: $VENV/bin/openorchestrion-smoke"
if [ "$WITH_OPENAI" -eq 1 ]; then
    echo "OpenAI SDK installed; set OPENAI_API_KEY in $SECRETS and enable the provider in openorchestrion.env."
fi
if [ "$MODE" = kiosk ]; then
    echo "Kiosk autostart installed for $KIOSK_USER; log out/in or reboot to launch Chromium."
fi
