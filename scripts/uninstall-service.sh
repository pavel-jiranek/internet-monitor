#!/usr/bin/env bash
# Stop and remove the systemd user service. The database is kept.
set -euo pipefail

UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/internet-monitor.service"

systemctl --user disable --now internet-monitor.service 2>/dev/null || true
rm -f "$UNIT"
systemctl --user daemon-reload
echo "Removed $UNIT"
