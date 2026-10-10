#!/bin/bash
set -euo pipefail
cd /opt/rightwrite/app
export NODE_OPTIONS="--max-old-space-size=5120"
echo "===== building at $(git rev-parse --short HEAD) ====="
date
npm run build
echo "===== BUILD DONE ====="
date
du -sh build
ls build | head
