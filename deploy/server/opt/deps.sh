#!/bin/bash
set -euo pipefail
APP=/opt/rightwrite/app

echo "===== [1/4] clone (retry x3, GitHub route is flaky from HK) ====="
if [ ! -d "$APP/.git" ]; then
  for i in 1 2 3; do
    git clone https://github.com/Chauban/open-webui.git "$APP" && break
    echo "clone attempt $i failed, retrying..."; sleep 5
  done
fi
cd "$APP"
git config --global --add safe.directory "$APP" || true
echo "HEAD: $(git rev-parse --short HEAD) $(git log -1 --format='%s')"

echo "===== [2/4] python venv ====="
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -U pip wheel setuptools

echo "===== [3/4] pip install backend requirements (this is the long one) ====="
"$APP/.venv/bin/pip" install -r "$APP/backend/requirements.txt"

echo "===== [4/4] npm ci ====="
cd "$APP" && npm ci --no-audit --no-fund

echo "===== DEPS DONE ====="
du -sh "$APP/.venv" "$APP/node_modules"
