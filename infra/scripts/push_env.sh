#!/usr/bin/env bash
# Push a local env file to the Vultr VM as the quarantine-api service's EnvironmentFile, then restart and verify.
# Prints key names only, never values. Laptop-only keys (admin DB URL, raw role passwords, Vultr account key)
# are stripped before upload. RECEIPT_SIGNING_KEY_PATH is pinned to a VM path outside the release tree so
# publish.sh never overwrites the key; the key is generated on the VM on first run and never leaves it.
#
# Before swapping, the VM checks that both DB URLs connect. After the restart, /health must report db and
# object_storage "ok"; otherwise the previous env file is restored and the service restarted.
#
# Runs as root (deploy cannot write /opt/vultr-app/.env).
# Usage:
#   push_env.sh --host HOST [--env-file infra/.env] [--user root] [--identity FILE] [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VM_HOST:-}"
USER_NAME=root
IDENTITY=""
ENV_FILE="$REPO_ROOT/infra/.env"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --identity) IDENTITY="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$HOST" ] || { echo "--host (or VM_HOST) is required" >&2; exit 2; }
[ -f "$ENV_FILE" ] || { echo "env file not found: $ENV_FILE" >&2; exit 2; }

REMOTE_ENV=/opt/vultr-app/.env
REMOTE_KEY=/opt/vultr-app/receipt_ed25519.pem
REQUIRED=(DATABASE_URL_PROXY DATABASE_URL_READER HOST_SECRET
  S3_ENDPOINT_URL S3_ACCESS_KEY S3_SECRET_KEY S3_BUCKET S3_REGION VULTR_INFERENCE_API_KEY)
LAPTOP_ONLY='^(DATABASE_URL_ADMIN|PROXY_DB_PASSWORD|READER_DB_PASSWORD|VULTR_API_KEY|RECEIPT_SIGNING_KEY_PATH)$'

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15)
[ -z "$IDENTITY" ] || SSH_OPTS+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
TARGET="$USER_NAME@$HOST"

step() { echo "== $*"; }

TMP="$(mktemp -d)"; chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/env"

step "filter $ENV_FILE"
# KEY=value lines only; comments, blanks and `export` prefixes dropped; empty values dropped so defaults apply.
awk -v drop="$LAPTOP_ONLY" '
  /^[[:space:]]*(#|$)/ { next }
  { sub(/^[[:space:]]*export[[:space:]]+/, "") }
  match($0, /^[A-Za-z_][A-Za-z0-9_]*=/) {
    key = substr($0, 1, RLENGTH - 1); val = substr($0, RLENGTH + 1)
    if (key ~ drop || val == "") next
    print key "=" val; next
  }
  { printf "skipping malformed line %d\n", NR > "/dev/stderr" }
' "$ENV_FILE" > "$OUT"
echo "RECEIPT_SIGNING_KEY_PATH=$REMOTE_KEY" >> "$OUT"

missing=()
grep -qi "^REVIEWER_AUTH_DISABLED=true$" "$OUT" || REQUIRED+=(REVIEWER_TOKEN)
for k in "${REQUIRED[@]}"; do grep -q "^$k=" "$OUT" || missing+=("$k"); done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "missing or empty required keys: ${missing[*]}" >&2; exit 1
fi
echo "keys to push: $(cut -d= -f1 "$OUT" | tr '\n' ' ')"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run: would upload to $TARGET:$REMOTE_ENV, ensure $REMOTE_KEY, restart quarantine-api and verify /health"
  exit 0
fi

step "upload and verify on $TARGET"
ssh "${SSH_OPTS[@]}" "$TARGET" 'umask 077 && mkdir -p /opt/vultr-app/.incoming && cat > /opt/vultr-app/.incoming/env' < "$OUT"
ssh "${SSH_OPTS[@]}" "$TARGET" bash -s -- "$REMOTE_ENV" "$REMOTE_KEY" <<'REMOTE'
set -uo pipefail
ENV="$1"; KEY="$2"; NEW=/opt/vultr-app/.incoming/env
PY=/opt/quarantine/backend/.venv/bin/python
fail() { echo "FAILED: $*" >&2; rm -f "$NEW"; exit 1; }

# 1. Both DB URLs must connect before anything changes.
"$PY" - "$NEW" <<'PY' || fail "DB preflight; $ENV unchanged"
import sys, psycopg
env = {}
for line in open(sys.argv[1]):
    k, _, v = line.rstrip("\n").partition("=")
    env[k] = v.strip().strip('"').strip("'")
for k in ("DATABASE_URL_PROXY", "DATABASE_URL_READER"):
    try:
        with psycopg.connect(env[k], connect_timeout=10) as c:
            user = c.execute("select current_user").fetchone()[0]
        print(f"{k}: connects as {user}")
    except Exception as e:
        print(f"{k}: {type(e).__name__}", file=sys.stderr)
        sys.exit(1)
PY

# 2. Receipt key: generate once on the VM, readable only by runner.
if [ ! -f "$KEY" ]; then
  "$PY" - "$KEY" <<'PY' || fail "signing key generation"
import hashlib, os, sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
key = Ed25519PrivateKey.generate()
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
os.write(fd, pem); os.close(fd)
raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print("generated receipt key, key_id", hashlib.sha256(raw).hexdigest()[:16])
PY
  chown runner:runner "$KEY"
else
  echo "receipt key present"
fi

# 3. Swap, restart, verify; restore the previous file on failure.
BAK="$ENV.bak.$(date +%Y%m%d%H%M%S)"
cp -a "$ENV" "$BAK"
install -m 600 -o runner -g runner "$NEW" "$ENV" && rm -f "$NEW"

healthy() {
  local body=""
  for _ in $(seq 1 30); do body="$(curl -fsS -m 5 http://127.0.0.1:8000/health 2>/dev/null)" && break; sleep 1; done
  echo "health: ${body:-unreachable}"
  echo "$body" | grep -q '"db":"ok"' && echo "$body" | grep -q '"object_storage":"ok"'
}

systemctl restart quarantine-api
if healthy; then
  echo "env pushed; previous file kept at $BAK"
  exit 0
fi
echo "FAILED: health check after restart; restoring $BAK" >&2
journalctl -u quarantine-api -n 20 --no-pager | grep -viE 'password|secret|token|key=' >&2
cp -a "$BAK" "$ENV" && systemctl restart quarantine-api
exit 1
REMOTE

step "public check"
curl -fsS -m 10 "http://$HOST:8000/health"; echo
