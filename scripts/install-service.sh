#!/usr/bin/env bash
# Install internet-monitor into a local virtualenv and register it as a systemd user service.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_DIR/.venv"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/internet-monitor.service"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating virtualenv in $VENV"
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$REPO_DIR"

mkdir -p "$UNIT_DIR"
sed "s|@EXEC@|$VENV/bin/internet-monitor|" "$REPO_DIR/systemd/internet-monitor.service.in" > "$UNIT"
echo "Installed $UNIT"

systemctl --user daemon-reload
systemctl --user enable --now internet-monitor.service
systemctl --user --no-pager status internet-monitor.service | head -n 5

cat <<EOF

Dashboard: http://127.0.0.1:${IM_PORT:-8085}/
Logs:      journalctl --user -u internet-monitor -f

User services stop when you log out. To keep monitoring regardless, run once:
    sudo loginctl enable-linger $USER
EOF
