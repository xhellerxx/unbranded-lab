"""
unbranded fork: lab heartbeat.

A daemon thread that reports to the unbranded app every few minutes so the
Rehearsal page can honestly say whether the lab is up. Fire-and-forget:
failures are logged at debug level and never affect the lab itself.
"""

import json
import os
import threading
import time
import urllib.request

from ..utils.logger import get_logger

logger = get_logger('mirofish')

HEARTBEAT_URL = os.environ.get(
    "HEARTBEAT_URL",
    "https://unbranded-underwrite.xhellerx.workers.dev/api/lab/heartbeat",
)
INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_INTERVAL", "300"))

_started = False
_lock = threading.Lock()


def _beat_once():
    payload = {"service": "mirofish-fork", "model": os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")[:80], "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    req = urllib.request.Request(
        HEARTBEAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        # A named agent: Cloudflare can refuse the default Python-urllib signature.
        headers={"Content-Type": "application/json", "User-Agent": "unbranded-lab/1.0 (+https://unbranded.inc)"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def _loop():
    while True:
        try:
            _beat_once()
        except Exception as e:  # noqa: BLE001 - heartbeat must never crash the lab
            logger.warning(f"Heartbeat failed: {e}")
        time.sleep(INTERVAL_SECONDS)


def start_heartbeat():
    """Start the heartbeat thread once per process. Safe to call repeatedly."""
    global _started
    if not HEARTBEAT_URL:
        return
    with _lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_loop, name="lab-heartbeat", daemon=True)
    t.start()
    logger.info(f"Lab heartbeat started: every {INTERVAL_SECONDS}s to {HEARTBEAT_URL}")
