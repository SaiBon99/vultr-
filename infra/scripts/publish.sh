#!/usr/bin/env bash
# Publish HEAD's backend and contracts plus the built frontend to the Vultr VM, then restart quarantine-api.
# The VM keeps the previous release in /opt/quarantine/.releases/previous.tgz; a failed health or smoke
# check puts it back automatically, and --rollback puts it back on demand.
# Runs as the deploy user (see setup_deploy_user.sh). Never reads, prints or copies any .env file or key:
# the service's secrets stay in /opt/vultr-app/.env on the VM.
#
# Usage:
#   publish.sh --host HOST [--user deploy] [--identity FILE] [--frontend-build DIR] [--build]
#              [--allow-dirty] [--dry-run]
#   publish.sh --host HOST [--user deploy] [--identity FILE] --rollback
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${VM_HOST:-}"
USER_NAME="${VM_USER:-deploy}"
IDENTITY=""
FRONTEND_BUILD="$REPO_ROOT/frontend/build"
BUILD=0
ALLOW_DIRTY=0
DRY_RUN=0
ROLLBACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --identity) IDENTITY="$2"; shift 2 ;;
    --frontend-build) FRONTEND_BUILD="$2"; shift 2 ;;
    --build) BUILD=1; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --rollback) ROLLBACK=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$HOST" ] || { echo "--host (or VM_HOST) is required" >&2; exit 2; }

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=15)
[ -z "$IDENTITY" ] || SSH_OPTS+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
TARGET="$USER_NAME@$HOST"

step() { echo "== $*"; }

if [ "$ROLLBACK" -eq 1 ]; then
  step "rollback on $TARGET"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "would restore .releases/previous.tgz, restart quarantine-api and run the health and smoke checks"
    exit 0
  fi
  ssh "${SSH_OPTS[@]}" "$TARGET" bash -s -- rollback <<'REMOTE'
set -euo pipefail
APP=/opt/quarantine
cd "$APP"
[ -f .releases/previous.tgz ] || { echo "no previous release on the VM" >&2; exit 1; }
rm -rf frontend/build
tar -x --no-same-owner -f .releases/previous.tgz -C "$APP"
sudo -n -u runner /home/runner/.local/bin/uv sync --frozen --no-dev --project "$APP/backend"
sudo -n /usr/bin/systemctl restart quarantine-api
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:8000/health && break; sleep 1; done
curl -fsS -o /dev/null http://127.0.0.1:8000/health
echo "rolled back to previous release"
REMOTE
  exit 0
fi

step "preconditions"
if [ "$ALLOW_DIRTY" -eq 0 ] && { ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; }; then
  echo "working tree has uncommitted changes; commit them or pass --allow-dirty (the build will not match HEAD)" >&2
  exit 1
fi
[ "$ALLOW_DIRTY" -eq 0 ] || echo "WARNING: --allow-dirty; the frontend build may not match HEAD" >&2
echo "commit $(git -C "$REPO_ROOT" rev-parse --short HEAD) -> $TARGET"

if [ "$BUILD" -eq 1 ]; then
  step "build frontend (live, same-origin API)"
  if [ "$DRY_RUN" -eq 0 ]; then
    (cd "$REPO_ROOT/frontend" && PUBLIC_API_MODE=live PUBLIC_API_BASE=/ pnpm run build)
  else
    echo "would run: cd frontend && PUBLIC_API_MODE=live PUBLIC_API_BASE=/ pnpm run build"
  fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
  [ -f "$FRONTEND_BUILD/index.html" ] || { echo "no frontend build at $FRONTEND_BUILD (pass --build)" >&2; exit 1; }
fi

if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run: would publish"
  echo "1. archive HEAD: backend contracts infra openspec -> $TARGET:/opt/quarantine/.incoming/code.tgz"
  echo "2. archive $FRONTEND_BUILD -> $TARGET:/opt/quarantine/.incoming/frontend.tgz"
  echo "3. keep current release as .releases/previous.tgz (excludes backend/.venv)"
  echo "4. extract new release; uv sync --frozen --no-dev; restart quarantine-api"
  echo "5. health 200, /ui/ 200, POST /crawl without token 401; on failure restore previous and exit 1"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step "package"
git -C "$REPO_ROOT" archive --format=tar HEAD backend contracts infra openspec | gzip -9 > "$TMP/code.tgz"
tar -C "$FRONTEND_BUILD" -czf "$TMP/frontend.tgz" .
echo "code.tgz $(du -h "$TMP/code.tgz" | cut -f1), frontend.tgz $(du -h "$TMP/frontend.tgz" | cut -f1)"

step "upload"
ssh "${SSH_OPTS[@]}" "$TARGET" 'mkdir -p /opt/quarantine/.incoming && cat > /opt/quarantine/.incoming/code.tgz' < "$TMP/code.tgz"
ssh "${SSH_OPTS[@]}" "$TARGET" 'cat > /opt/quarantine/.incoming/frontend.tgz' < "$TMP/frontend.tgz"

step "install, restart, verify"
ssh "${SSH_OPTS[@]}" "$TARGET" bash -s -- deploy <<'REMOTE'
set -euo pipefail
APP=/opt/quarantine
cd "$APP"

check() {
  for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:8000/health && break; sleep 1; done
  curl -fsS -o /dev/null http://127.0.0.1:8000/health || return 1
  curl -fsS -o /dev/null http://127.0.0.1:8000/ui/ || return 1
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/crawl \
    -H 'content-type: application/json' -d '{"url":"https://example.com"}')"
  [ "$code" = 401 ]
}

mkdir -p .releases
paths=()
for p in backend contracts infra openspec frontend/build; do [ -e "$p" ] && paths+=("$p"); done
tar --exclude='backend/.venv' -czf .releases/previous.tgz.tmp "${paths[@]}"
mv .releases/previous.tgz.tmp .releases/previous.tgz

tar -x --no-same-owner -f .incoming/code.tgz -C "$APP"
rm -rf frontend/build && mkdir -p frontend/build
tar -x --no-same-owner -f .incoming/frontend.tgz -C frontend/build

sudo -n -u runner /home/runner/.local/bin/uv sync --frozen --no-dev --project "$APP/backend"
sudo -n /usr/bin/systemctl restart quarantine-api

if check; then
  rm -rf .incoming
  echo "deployed: health, /ui/ and crawl auth check passed"
  exit 0
fi

echo "FAILED: new release did not pass checks; restoring previous release" >&2
rm -rf frontend/build
tar -x --no-same-owner -f .releases/previous.tgz -C "$APP"
sudo -n -u runner /home/runner/.local/bin/uv sync --frozen --no-dev --project "$APP/backend"
sudo -n /usr/bin/systemctl restart quarantine-api
if check; then
  echo "previous release restored and healthy" >&2
else
  echo "previous release also failed its checks; check journalctl -u quarantine-api" >&2
fi
exit 1
REMOTE

step "public check"
curl -fsS -o /dev/null "http://$HOST:8000/health"
echo "http://$HOST:8000/health 200"
echo "http://$HOST:8000/ui/ 200 expected; open it to confirm"
