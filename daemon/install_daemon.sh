#!/bin/bash
# Install cogman as a systemd user service

set -e

SERVICE_DIR="$HOME/.config/systemd/user"
ENV_DIR="$HOME/.config/cogman"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$SERVICE_DIR" "$ENV_DIR"

# Write env file (edit this with your API key)
cat > "$ENV_DIR/env" <<EOF
ANTHROPIC_API_KEY=your_key_here
COGMAN_MODEL=claude-sonnet-4-6
COGMAN_API=true
EOF

# Install service file
sed "s|%i|$USER|g" "$PROJECT_DIR/daemon/cogman.service" | \
  sed "s|/home/$USER/void/projects/cogman|$PROJECT_DIR|g" \
  > "$SERVICE_DIR/cogman.service"

systemctl --user daemon-reload
systemctl --user enable cogman.service

echo ""
echo "cogman service installed!"
echo "Edit $ENV_DIR/env to set your ANTHROPIC_API_KEY"
echo ""
echo "Commands:"
echo "  systemctl --user start cogman    # start"
echo "  systemctl --user stop cogman     # stop"
echo "  systemctl --user status cogman   # status"
echo "  journalctl --user -u cogman -f   # logs"
