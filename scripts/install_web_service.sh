#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/creator-sync-web.service"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=creator-sync web console
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_ROOT}
ExecStart=${PROJECT_ROOT}/scripts/run_web.sh --host 0.0.0.0 --port 8714
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now creator-sync-web.service
systemctl --user status creator-sync-web.service --no-pager
