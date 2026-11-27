#!/usr/bin/env bash
# Idempotent host setup for a Vultr VX1 (Ubuntu 24.04) or any KVM-capable Linux host.
#
# What it does:
#   1. Checks /dev/kvm and adds the current user to the kvm group.
#   2. Installs the Microsandbox CLI (msb) matching requirements.txt, then runs `msb doctor`.
#   3. Creates .venv and installs the Python requirements.
#
# Usage:  bash scripts/setup_vm.sh
# Optional: MSB_INSTALL_SHA256=<hash> to refuse the installer unless it matches.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MSB_INSTALL_URL="https://install.microsandbox.dev"

log() { printf '\n== %s\n' "$*"; }

log "1/3 Checking KVM"
if [[ ! -e /dev/kvm ]]; then
  echo "ERROR: /dev/kvm not found. Microsandbox needs KVM. Enable virtualization or use a KVM-capable VM." >&2
  exit 1
fi
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx kvm; then
  sudo usermod -aG kvm "$USER"
  echo "Added $USER to the kvm group. Log out and back in (or reboot) before re-running msb commands."
fi

log "2/3 Installing Microsandbox CLI"
if ! command -v msb >/dev/null 2>&1; then
  installer="$(mktemp)"
  trap 'rm -f "$installer"' EXIT
  curl -fsSL "$MSB_INSTALL_URL" -o "$installer"
  actual="$(sha256sum "$installer" | cut -d' ' -f1)"
  echo "installer sha256: $actual"
  if [[ -n "${MSB_INSTALL_SHA256:-}" && "$actual" != "$MSB_INSTALL_SHA256" ]]; then
    echo "ERROR: installer checksum does not match MSB_INSTALL_SHA256. Refusing to run it." >&2
    exit 1
  fi
  sh "$installer"
  export PATH="$HOME/.local/bin:$PATH"
fi
msb --version
msb doctor

log "3/3 Python environment"
cd "$REPO_ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

cat <<EOF

Setup complete.
  Next: copy .env.example to .env and fill in VULTR_INFERENCE_API_KEY and VULTR_INFERENCE_MODEL.
  Run tests:  .venv/bin/pytest            (unit)
              .venv/bin/pytest -m integration   (real sandboxes)
  Run app:    .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
EOF
