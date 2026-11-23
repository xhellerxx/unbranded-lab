"""
unbranded fork: push each finished flight's debrief to The Stack.

The report is signed with LAB_PUSH_KEY (HMAC-SHA256 over the exact body) so the app
can tell a genuine debrief from anything else that reaches the endpoint. The app files
it as a hypothesis, outside every client and deal record. Fire-and-forget: a failed push
is logged and never affects the lab.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.request

from ..utils.logger import get_logger

logger = get_logger('mirofish')

_HB = os.environ.get("HEARTBEAT_URL", "https://unbranded-underwrite.xhellerx.workers.dev/api/lab/heartbeat")
DEBRIEF_URL = os.environ.get("DEBRIEF_URL", _HB.rsplit("/", 1)[0] + "/debrief")
MAX_MARKDOWN = 300_000


def push_debrief(report, run_qualification):
    key = os.environ.get("LAB_PUSH_KEY", "").strip()
    if not key:
        logger.info("Debrief not pushed: LAB_PUSH_KEY is not set on this lab.")
        return
    try:
        payload = {
            "report_id": report.report_id,
            "simulation_id": report.simulation_id,
            "question": (report.simulation_requirement or "")[:4000],
            "run_qualification": run_qualification or {},
            "markdown": (report.markdown_content or "")[:MAX_MARKDOWN],
            "ts": int(time.time()),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sig = hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            DEBRIEF_URL, data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Lab-Signature": sig,
                     "User-Agent": "unbranded-lab/1.0 (+https://unbranded.inc)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        logger.info(f"Debrief {report.report_id} delivered to The Stack.")
    except Exception as e:  # noqa: BLE001 - never crash the lab over a push
        logger.warning(f"Debrief push failed for {getattr(report, 'report_id', '?')}: {e}")
