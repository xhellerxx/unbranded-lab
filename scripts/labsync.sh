#!/usr/bin/env bash
# Pull-based deploy: runs from cron every 2 minutes.
set -e
cd /opt/unbranded-lab
git fetch -q origin main
LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
  echo "[labsync] $(date -u +%FT%TZ) deploying $REMOTE" >> /var/log/labsync.log
  git reset --hard origin/main
  docker compose up -d --build >> /var/log/labsync.log 2>&1
fi
