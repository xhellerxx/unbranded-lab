#!/usr/bin/env bash
# Pull-based deploy, run from cron every 2 minutes.
# A revision is marked deployed only after the app is verified READY, so a build or
# startup failure is retried on the next run instead of being skipped forever.
set -u
exec 9>/var/lock/labsync.lock
flock -n 9 || exit 0
cd /opt/unbranded-lab || exit 0
STATE=/var/lib/labsync.deployed
LOG=/var/log/labsync.log
git fetch -q origin main || exit 0
REMOTE=$(git rev-parse origin/main)
DEPLOYED=$(cat "$STATE" 2>/dev/null || echo none)
[ "$REMOTE" = "$DEPLOYED" ] && exit 0
echo "[labsync] $(date -u +%FT%TZ) deploying $REMOTE" >> "$LOG"
if ! git reset -q --hard origin/main; then
  echo "[labsync] $(date -u +%FT%TZ) CHECKOUT FAILED for $REMOTE, will retry" >> "$LOG"; exit 0
fi
cp scripts/labsync.sh /usr/local/bin/labsync.sh 2>/dev/null
if ! docker compose up -d --build >> "$LOG" 2>&1; then
  echo "[labsync] $(date -u +%FT%TZ) BUILD FAILED for $REMOTE, will retry" >> "$LOG"; exit 0
fi
# Readiness, checked the way a founder reaches it:
#  1. both containers running;
#  2. the report backend answers its health check (not just the frontend);
#  3. the public front door answers over HTTPS with its login challenge (401), proving DNS, TLS and auth are live.
FRONT=${LAB_DOMAIN:-lab.unbranded.inc}
for i in $(seq 1 30); do
  RUNNING=$(docker compose ps --status running --services 2>/dev/null | wc -l)
  BACK=$(docker compose exec -T caddy wget -q -O - http://mirofish:5001/health 2>/dev/null | grep -c '"ok"')
  DOOR=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$FRONT/" 2>/dev/null)
  if [ "$RUNNING" -ge 2 ] && [ "$BACK" -ge 1 ] && [ "$DOOR" = "401" ]; then
    echo "$REMOTE" > "$STATE"
    echo "[labsync] $(date -u +%FT%TZ) deployed and verified ready: $REMOTE" >> "$LOG"
    exit 0
  fi
  sleep 10
done
echo "[labsync] $(date -u +%FT%TZ) NOT READY after 5 minutes for $REMOTE (containers=$RUNNING backend_ok=$BACK front_door=$DOOR), will retry" >> "$LOG"
