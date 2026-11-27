#!/usr/bin/env bash
# Serve the honeypot pages on a separate, read-only static service (port 8081) on the VM.
# Separate from the API process so the API never serves attacker-authored content. Idempotent.
# Run on the VM as root from the repo checkout.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO/honeypot/site"
DEST=/opt/honeypot/site
PORT="${HONEYPOT_PORT:-8081}"
UNIT=/etc/systemd/system/honeypot-static.service

[ -d "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

install -d -m 0755 "$DEST"
rsync -a --delete "$SRC"/ "$DEST"/ 2>/dev/null || { rm -rf "$DEST"; cp -r "$SRC" "$DEST"; }
chmod -R a+rX,go-w "$DEST"

cat > "$UNIT.tmp" <<UNIT_EOF
[Unit]
Description=Honeypot static pages (read-only, no secrets)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 -m http.server ${PORT} --bind 0.0.0.0 --directory ${DEST}
DynamicUser=yes
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
PrivateTmp=yes
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT_EOF
if ! cmp -s "$UNIT.tmp" "$UNIT" 2>/dev/null; then
  mv "$UNIT.tmp" "$UNIT"
  systemctl daemon-reload
else
  rm -f "$UNIT.tmp"
fi

systemctl enable --now honeypot-static.service
systemctl is-active --quiet honeypot-static.service
echo "honeypot served on port ${PORT}; open it in the VM firewall if the crawler must reach it from outside"
