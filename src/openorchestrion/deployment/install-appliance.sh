#!/bin/sh
set -eu

MODE=headless
KIOSK_USER=
PACKAGE_SPEC=.
WITH_OPENAI=0
APPLIANCE_HOSTNAME=
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
  --hostname NAME          Explicitly set the appliance hostname (for example openorchestrion)
  -h, --help               Show this help

The script is intentionally safe to re-run for updates. It preserves existing
configuration/secrets under /etc/openorchestrion and all data under
/var/lib/openorchestrion. The system hostname is never changed unless
--hostname is explicitly supplied.
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
        --hostname)
            [ "$#" -ge 2 ] || { echo "--hostname needs a value" >&2; exit 2; }
            APPLIANCE_HOSTNAME=$2
            shift 2
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

if [ -n "$APPLIANCE_HOSTNAME" ]; then
    if [ "${#APPLIANCE_HOSTNAME}" -gt 63 ]; then
        echo "--hostname must be 63 characters or fewer" >&2
        exit 2
    fi
    case "$APPLIANCE_HOSTNAME" in
        *[!a-z0-9-]*|-*|*-)
            echo "--hostname must contain only lowercase letters, digits, and internal hyphens" >&2
            exit 2
            ;;
    esac
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 2; }
command -v systemctl >/dev/null 2>&1 || { echo "systemd is required" >&2; exit 2; }
command -v flock >/dev/null 2>&1 || { echo "flock is required" >&2; exit 2; }
exec 9>/run/lock/openorchestrion-install.lock
flock -n 9 || { echo "another appliance installation is running" >&2; exit 2; }
[ ! -L "$VENV" ] || { echo "installer requires a directory at $VENV, not a symlink" >&2; exit 2; }
if [ -n "$APPLIANCE_HOSTNAME" ]; then
    command -v hostnamectl >/dev/null 2>&1 || {
        echo "hostnamectl is required when --hostname is used" >&2
        exit 2
    }
fi

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
if [ "$MODE" = kiosk ]; then
    getent passwd "$KIOSK_USER" >/dev/null 2>&1 || {
        echo "unknown --kiosk-user: $KIOSK_USER" >&2; exit 2;
    }
    command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 || {
        echo "Chromium is required for kiosk mode; install chromium first" >&2; exit 2;
    }
fi

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

# Resolve/build every dependency before stopping a working appliance. Keep the
# original virtual environment intact until the offline installation is ready.
TMP=$(mktemp -d)
WAS_RUNNING=0
INSTALL_STARTED=0
HAD_VENV=0
cleanup() {
    result=$?
    trap - EXIT INT TERM
    if [ "$result" -ne 0 ] && [ "$INSTALL_STARTED" -eq 1 ]; then
        echo "installation failed; restoring the previous Python environment" >&2
        systemctl stop openorchestrion.service 2>/dev/null || true
        for unit in openorchestrion.service openorchestrion-discovery.service; do
            if [ -f "$TMP/previous-units/$unit" ]; then
                cp -a "$TMP/previous-units/$unit" "/etc/systemd/system/$unit"
            else
                rm -f "/etc/systemd/system/$unit"
            fi
        done
        systemctl daemon-reload
        rm -rf "$VENV"
        if [ "$HAD_VENV" -eq 1 ]; then
            cp -a "$TMP/previous-venv" "$VENV"
            if [ "$WAS_RUNNING" -eq 1 ]; then
                systemctl daemon-reload
                systemctl restart openorchestrion.service || {
                    echo "rollback restored; service restart failed; inspect journalctl" >&2
                }
            fi
        fi
    fi
    rm -rf "$TMP"
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python3 -m venv "$TMP/bootstrap"
"$TMP/bootstrap/bin/python" -m pip wheel --wheel-dir "$TMP/wheels" "$PACKAGE_SPEC"
if [ "$WITH_OPENAI" -eq 1 ]; then
    "$TMP/bootstrap/bin/python" -m pip wheel --wheel-dir "$TMP/wheels" "openai>=2.0"
fi
# Require the actual appliance wheel, not an arbitrary successful pip download.
set -- "$TMP"/wheels/openorchestrion-*.whl
[ "$#" -eq 1 ] && [ -f "$1" ] || {
    echo "package must build exactly one OpenOrchestrion wheel" >&2; exit 2;
}
APPLIANCE_WHEEL=$1
mkdir -p "$TMP/previous-units"
for unit in openorchestrion.service openorchestrion-discovery.service; do
    if [ -f "/etc/systemd/system/$unit" ]; then
        cp -a "/etc/systemd/system/$unit" "$TMP/previous-units/$unit"
    fi
done
if [ -d "$VENV" ]; then
    cp -a "$VENV" "$TMP/previous-venv"
    HAD_VENV=1
fi
if systemctl is-active --quiet openorchestrion.service 2>/dev/null; then
    WAS_RUNNING=1
    echo "stopping running OpenOrchestrion for update"
    systemctl stop openorchestrion.service
fi
INSTALL_STARTED=1
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --no-index --find-links "$TMP/wheels" \
    --upgrade --force-reinstall "$APPLIANCE_WHEEL"
if [ "$WITH_OPENAI" -eq 1 ]; then
    "$VENV/bin/python" -m pip install --no-index --find-links "$TMP/wheels" \
        --upgrade "openai>=2.0"
fi
"$VENV/bin/openorchestrion-deploy" --output-dir "$TMP"

install -m 0644 "$TMP/openorchestrion.service" /etc/systemd/system/openorchestrion.service
install -m 0644 "$TMP/openorchestrion-discovery.service" \
    /etc/systemd/system/openorchestrion-discovery.service
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

# Host identity belongs to the operator. A dedicated appliance may explicitly
# opt into the reference name, which Avahi then exposes as openorchestrion.local.
# Updates without --hostname leave the current host identity untouched.
if [ -n "$APPLIANCE_HOSTNAME" ]; then
    CURRENT_HOSTNAME=$(hostnamectl --static 2>/dev/null || hostname)
    if [ "$CURRENT_HOSTNAME" != "$APPLIANCE_HOSTNAME" ]; then
        echo "setting system hostname to $APPLIANCE_HOSTNAME"
        hostnamectl set-hostname "$APPLIANCE_HOSTNAME"
    fi
fi

systemctl daemon-reload
systemctl enable openorchestrion.service
systemctl restart openorchestrion.service

READY=0
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if runuser -u "$SERVICE_USER" -- "$VENV/bin/openorchestrion-smoke" >"$TMP/smoke.log" 2>&1; then
        READY=1
        break
    fi
    sleep 1
done
if [ "$READY" -ne 1 ]; then
    cat "$TMP/smoke.log" >&2
    echo "updated appliance failed its health check" >&2
    exit 1
fi
INSTALL_STARTED=0

DISCOVERY_STATE=unavailable
if command -v avahi-publish-service >/dev/null 2>&1 \
    && systemctl cat avahi-daemon.service >/dev/null 2>&1; then
    systemctl enable avahi-daemon.service >/dev/null 2>&1 || true
    if systemctl restart avahi-daemon.service >/dev/null 2>&1 \
        && systemctl is-active --quiet avahi-daemon.service; then
        systemctl enable openorchestrion-discovery.service >/dev/null 2>&1
        if systemctl restart openorchestrion-discovery.service >/dev/null 2>&1; then
            DISCOVERY_STATE=enabled
        else
            echo "warning: OpenOrchestrion is running, but the mDNS advertisement failed to start" >&2
        fi
    else
        echo "warning: OpenOrchestrion is running, but avahi-daemon is not active" >&2
    fi
else
    # Discovery is an optional LAN convenience. Never make playback depend on it.
    systemctl disable --now openorchestrion-discovery.service >/dev/null 2>&1 || true
    echo "warning: Avahi discovery unavailable; install avahi-daemon and avahi-utils for .local discovery" >&2
fi

echo
echo "OpenOrchestrion installed in $VENV"
echo "Configuration: $CONFIG_DIR/openorchestrion.env"
echo "Service secrets: $SECRETS"
echo "Durable data: $STATE_DIR"
echo "Logs: journalctl -u openorchestrion.service"
echo "Smoke check: $VENV/bin/openorchestrion-smoke"
if [ "$DISCOVERY_STATE" = enabled ]; then
    CURRENT_HOSTNAME=$(hostnamectl --static 2>/dev/null || hostname)
    echo "LAN discovery: enabled as $CURRENT_HOSTNAME.local (using the configured OpenOrchestrion port)"
fi
if [ "$WITH_OPENAI" -eq 1 ]; then
    echo "OpenAI SDK installed; set OPENAI_API_KEY in $SECRETS and enable the provider in openorchestrion.env."
fi
if [ "$MODE" = kiosk ]; then
    echo "Kiosk autostart installed for $KIOSK_USER; log out/in or reboot to launch Chromium."
fi
