#!/usr/bin/env bash
# unbranded rehearsal lab - one-time droplet bootstrap.
# Run as root on a fresh DigitalOcean "Docker on Ubuntu" droplet:
#   bash <(curl -fsSL https://raw.githubusercontent.com/xhellerxx/unbranded-lab/main/setup.sh)
set -e
REPO="https://github.com/xhellerxx/unbranded-lab.git"
DIR="/opt/unbranded-lab"

echo "== unbranded rehearsal lab setup =="

# 1. swap (2GB droplet + node build needs headroom)
if ! swapon --show | grep -q .; then
  echo "-- adding 2G swap"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2. code
if [ ! -d "$DIR/.git" ]; then git clone -q "$REPO" "$DIR"; fi
cd "$DIR"

# 3. secrets (prompted, never stored in the repo)
if [ ! -f .env ]; then
  read -r -p "OpenAI API key: " OPENAI_KEY
  read -r -p "Zep Cloud API key: " ZEP_KEY
  read -r -s -p "Lab password (for the browser login, user is 'unbranded'): " LAB_PW; echo
  LAB_HASH=$(docker run --rm caddy:2 caddy hash-password --plaintext "$LAB_PW")
  cat > .env <<ENV
LLM_API_KEY=$OPENAI_KEY
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-5-mini
LLM_BOOST_API_KEY=$OPENAI_KEY
LLM_BOOST_BASE_URL=https://api.openai.com/v1
LLM_BOOST_MODEL_NAME=gpt-5.1
ZEP_API_KEY=$ZEP_KEY
LAB_USER=unbranded
LAB_HASH=$LAB_HASH
ENV
  chmod 600 .env
fi

# 4. build and start (first build takes several minutes)
docker compose up -d --build

# 5. pull-based deploys: check GitHub every 2 minutes
cp scripts/labsync.sh /usr/local/bin/labsync.sh && chmod +x /usr/local/bin/labsync.sh
( crontab -l 2>/dev/null | grep -v labsync ; echo "*/2 * * * * /usr/local/bin/labsync.sh" ) | crontab -

IP=$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "== done. The lab is at: http://$IP  (user: unbranded, your lab password) =="
echo "== updates deploy themselves within 2 minutes of a push to main =="
