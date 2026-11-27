#!/usr/bin/env bash
# One-time VM setup for publish.sh: a locked 'deploy' account that can only publish the app.
# Run as root on the VM. Idempotent: a second run changes nothing it already set.
# The public key is passed in; the private key never touches this repo or the VM.
# Sudo is limited to the two exact commands publish.sh runs: restart quarantine-api, and uv sync as runner.
#
# Usage (from the laptop, public key only):
#   ssh root@HOST bash -s -- --pubkey "$(cat ~/.config/vultr/deploy_key.pub)" < infra/scripts/setup_deploy_user.sh
set -euo pipefail

DEPLOY_USER="deploy"
PUBKEY=""
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --pubkey) PUBKEY="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
case "$PUBKEY" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*\ *) ;;
  *) echo "--pubkey must be a public key line (ssh-ed25519 ...)" >&2; exit 2 ;;
esac

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ $*" >&2
  else
    "$@"
  fi
}

echo "== user $DEPLOY_USER"
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  echo "ok: exists"
else
  run useradd --create-home --shell /bin/bash --gid runner "$DEPLOY_USER"
fi
run passwd -l "$DEPLOY_USER" >/dev/null

echo "== authorized key"
HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
run install -d -m 700 -o "$DEPLOY_USER" -g runner "$HOME_DIR/.ssh"
AUTH="$HOME_DIR/.ssh/authorized_keys"
if [ "$DRY_RUN" -eq 0 ]; then
  touch "$AUTH"
  grep -qxF "$PUBKEY" "$AUTH" || printf '%s\n' "$PUBKEY" >> "$AUTH"
  chown "$DEPLOY_USER":runner "$AUTH"
  chmod 600 "$AUTH"
fi
echo "ok: key installed for $DEPLOY_USER"

echo "== sudo (exact commands only)"
SUDOERS=/etc/sudoers.d/quarantine-deploy
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<EOF
# publish.sh (infra/scripts/setup_deploy_user.sh): exact commands, no wildcards.
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart quarantine-api
$DEPLOY_USER ALL=(runner) NOPASSWD: /home/runner/.local/bin/uv sync --frozen --no-dev --project /opt/quarantine/backend
EOF
if [ "$DRY_RUN" -eq 0 ]; then
  visudo -cf "$TMP" >/dev/null
  install -m 440 -o root -g root "$TMP" "$SUDOERS"
fi
echo "ok: $SUDOERS"

echo "== app directory"
if [ -d /opt/quarantine ]; then
  run chgrp -R runner /opt/quarantine
  run chmod -R g+rwX /opt/quarantine
  echo "ok: /opt/quarantine writable by group runner"
else
  echo "skip: /opt/quarantine missing; run publish.sh after the first deploy layout exists" >&2
fi

echo "done"
