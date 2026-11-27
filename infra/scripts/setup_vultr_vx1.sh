#!/usr/bin/env bash
# Prepare a Vultr VX1 (Ubuntu 24.04) host: KVM check, uv, node/pnpm, Microsandbox (msb), systemd unit for uvicorn.
# Run on the VM as a sudo-capable user. Idempotent. Usage: setup_vultr_vx1.sh [--app-dir /opt/quarantine]
set -euo pipefail

APP_DIR=/opt/quarantine
while [ $# -gt 0 ]; do
  case "$1" in
    --app-dir) APP_DIR="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
RUN_USER="${SUDO_USER:-$USER}"

echo "== KVM check"
if [ ! -e /dev/kvm ]; then
  echo "FAIL: /dev/kvm missing; this plan needs nested virtualization (VX1)." >&2
  exit 1
fi
sudo usermod -aG kvm "$RUN_USER" || true

echo "== base packages"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates git build-essential

echo "== uv"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== node 22 + pnpm"
if ! command -v node >/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
sudo corepack enable
corepack prepare pnpm@latest --activate || true

echo "== microsandbox"
command -v msb >/dev/null || curl -sSL https://get.microsandbox.dev | sh
export PATH="$HOME/.local/bin:$PATH"
msb doctor

echo "== systemd unit (uvicorn)"
sudo mkdir -p "$APP_DIR"
sudo tee /etc/systemd/system/quarantine-api.service >/dev/null <<UNIT
[Unit]
Description=Memory Quarantine API
After=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/infra/.env
ExecStart=/home/$RUN_USER/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable quarantine-api.service
echo "done. Copy the repo to $APP_DIR, create infra/.env, then: sudo systemctl start quarantine-api"
