#!/usr/bin/env bash
# Pull-based deploy, run from cron every 2 minutes.
# Deploys are tracked by the last SUCCESSFUL build, not by git HEAD,
# so a build that fails is retried on the next run instead of being skipped forever.
set -u
exec 9>/var/lock/labsync.lock
flock -n 9 || exit 0
cd /opt/unbranded-lab
STATE=/var/lib/labsync.deployed
LOG=/var/log/labsync.log
git fetch -q origin main || exit 0
REMOTE=$(git rev-parse origin/main)
DEPLOYED=$(cat "$STATE" 2>/dev/null || echo none)
[ "$REMOTE" = "$DEPLOYED" ] && exit 0
echo "[labsync] $(date -u +%FT%TZ) deploying $REMOTE" >> "$LOG"
git reset -q --hard origin/main
cp scripts/labsync.sh /usr/local/bin/labsync.sh 2>/dev/null
if docker compose up -d --build >> "$LOG" 2>&1; then
  echo "$REMOTE" > "$STATE"
  echo "[labsync] $(date -u +%FT%TZ) deployed $REMOTE" >> "$LOG"
else
  echo "[labsync] $(date -u +%FT%TZ) BUILD FAILED for $REMOTE, will retry" >> "$LOG"
fi
