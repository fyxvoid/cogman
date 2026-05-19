#!/usr/bin/env bash
# install_daemon.sh — Install COGMAN as a systemd user service
#
# Usage:
#   bash daemon/install_daemon.sh           # install
#   bash daemon/install_daemon.sh --remove  # uninstall

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="cogman"
UNIT_DIR="$HOME/.config/systemd/user"
ENV_DIR="$HOME/.config/cogman"
UNIT_FILE="$UNIT_DIR/${SERVICE_NAME}.service"

# ── Detect python ─────────────────────────────────────────────────────────────
PYTHON=""
for p in python3 python; do
    if command -v "$p" &>/dev/null; then
        PYTHON="$(command -v "$p")"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "[cogman] ERROR: python3 not found." >&2
    exit 1
fi

# ── Remove ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--remove" ]]; then
    echo "[cogman] Removing service..."
    systemctl --user stop  "$SERVICE_NAME" 2>/dev/null || true
    systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload
    echo "[cogman] Service removed."
    exit 0
fi

# ── Install ───────────────────────────────────────────────────────────────────
echo "[cogman] Installing user service..."
mkdir -p "$UNIT_DIR" "$ENV_DIR"

# Write env file only if it doesn't already exist
if [[ ! -f "$ENV_DIR/env" ]]; then
    cat > "$ENV_DIR/env" <<'EOF'
# COGMAN environment — edit this file then restart the service
# systemctl --user restart cogman

# Set at least ONE provider key (or use Ollama for offline)
ANTHROPIC_API_KEY=

# Optionally override the model
# COGMAN_MODEL=claude-sonnet-4-6

# Local Ollama (auto-detected if running)
COGMAN_LOCAL_LLM=true
# COGMAN_OLLAMA_MODEL=mistral

# REST API settings
COGMAN_API=true
COGMAN_API_HOST=127.0.0.1
COGMAN_API_PORT=7777

# Gateway tokens (optional — only needed for --gateway mode)
# COGMAN_TELEGRAM_TOKEN=
# COGMAN_DISCORD_TOKEN=
# COGMAN_SLACK_BOT_TOKEN=
# COGMAN_SLACK_APP_TOKEN=
# COGMAN_IRC_HOST=

# Brave Search (optional)
# BRAVE_API_KEY=
EOF
    echo "[cogman] Created env file: $ENV_DIR/env"
    echo "         → Edit it to set your ANTHROPIC_API_KEY (or other provider)"
fi

# Instantiate the service unit with real paths
sed \
    -e "s|COGMAN_DIR|${PROJECT_DIR}|g" \
    -e "s|COGMAN_PYTHON|${PYTHON}|g" \
    "$SCRIPT_DIR/cogman.service" \
    > "$UNIT_FILE"

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

# ── Linger (survive logout) ───────────────────────────────────────────────────
if command -v loginctl &>/dev/null; then
    if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=no"; then
        read -rp "[cogman] Enable linger so cogman persists after logout? [y/N] " yn
        if [[ "${yn,,}" == "y" ]]; then
            loginctl enable-linger "$USER"
            echo "[cogman] Linger enabled."
        fi
    fi
fi

# ── Status ────────────────────────────────────────────────────────────────────
echo ""
echo "  COGMAN service installed and started."
echo ""
echo "  Useful commands:"
echo "    systemctl --user status  cogman        # check status"
echo "    systemctl --user restart cogman        # restart after config change"
echo "    systemctl --user stop    cogman        # stop"
echo "    journalctl --user -u cogman -f         # live logs"
echo ""
echo "  Config file: $ENV_DIR/env"
echo "  Project dir: $PROJECT_DIR"
echo "  Python:      $PYTHON"
echo ""
echo "  API will be available at: http://127.0.0.1:7777  (once started)"
echo ""
systemctl --user status "$SERVICE_NAME" --no-pager || true
