#!/bin/bash
set -euo pipefail
APP=/opt/rightwrite/app
PIP="$APP/.venv/bin/pip"

echo "===== [0/3] purge any CUDA packages that slipped in ====="
CUDA_PKGS=$("$PIP" list --format=freeze 2>/dev/null | grep -iE "^(nvidia-|cuda-|triton)" | cut -d= -f1 || true)
if [ -n "$CUDA_PKGS" ]; then echo "removing: $CUDA_PKGS"; "$PIP" uninstall -y $CUDA_PKGS; else echo "none present"; fi

echo "===== [1/3] CPU-only torch (no GPU on this box) ====="
"$PIP" install --index-url https://download.pytorch.org/whl/cpu \
               --extra-index-url https://pypi.org/simple \
               torch torchvision

echo "===== [2/3] backend requirements (torch already satisfied -> CUDA skipped) ====="
"$PIP" install -r "$APP/backend/requirements.txt"

echo "===== [3/3] npm ci ====="
cd "$APP" && npm ci --no-audit --no-fund

echo "===== DEPS DONE ====="
"$PIP" list --format=freeze | grep -iE "^(torch|sentence-transformers|transformers)=" || true
echo "--- any CUDA leftovers? ---"
"$PIP" list --format=freeze | grep -icE "^(nvidia-|cuda-)" || echo 0
du -sh "$APP/.venv" "$APP/node_modules" 2>/dev/null || true
