"""
unbranded fork: fly a flight plan sent from The Stack, end to end, without anyone opening the lab.

POST /api/unbranded/fly
  Body (JSON): { flight_id, title, question, plan, rounds, ts }
  Header: X-Stack-Signature = HMAC-SHA256(LAB_PUSH_KEY, exact body), hex.
  Reached without the lab password (Caddy routes /api/unbranded/* straight here);
  the signature is the only way in.

The orchestrator drives the lab's own API in-process (Flask test client), the same five
steps a person clicks through: read the plan, build the world, cast the crowd, fly, debrief.
Each step reports back to The Stack over the signed channel. The finished report goes to
The Stack through the existing debrief push, filed there as a hypothesis.
One flight at a time: the box is sized for one crowd.
"""

import hashlib
import hmac
import io
import json
import os
import threading
import time
import urllib.request

from flask import Blueprint, current_app, jsonify, request

from ..utils.logger import get_logger

logger = get_logger('mirofish')
unbranded_bp = Blueprint('unbranded', __name__)

_HB = os.environ.get("HEARTBEAT_URL", "https://unbranded-underwrite.xhellerx.workers.dev/api/lab/heartbeat")
STATUS_URL = os.environ.get("FLIGHT_STATUS_URL", _HB.rsplit("/", 1)[0] + "/flight-status")
_busy = threading.Lock()


def _key():
    return os.environ.get("LAB_PUSH_KEY", "").strip()


def _sign(raw: bytes) -> str:
    return hmac.new(_key().encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _report(flight_id, step, state, detail="", lab=None):
    """Tell The Stack where the flight is. Never raises."""
    if not _key():
        return
    try:
        body = json.dumps({"flight_id": flight_id, "step": step, "state": state, "detail": str(detail)[:600],
                           "lab": lab or {}, "ts": int(time.time())}).encode("utf-8")
        req = urllib.request.Request(STATUS_URL, data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Lab-Signature": _sign(body),
            "User-Agent": "unbranded-lab/1.0 (+https://unbranded.inc)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Flight status push failed ({flight_id} {step} {state}): {e}")


@unbranded_bp.route('/fly', methods=['POST'])
def fly():
    if not _key():
        return jsonify({"success": False, "error": "Flights from The Stack are not configured on this lab."}), 503
    raw = request.get_data(cache=True) or b""
    got = (request.headers.get("X-Stack-Signature") or "").lower()
    if not got or not hmac.compare_digest(_sign(raw), got):
        return jsonify({"success": False, "error": "Bad signature."}), 403
    try:
        b = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return jsonify({"success": False, "error": "Malformed request."}), 400
    if abs(time.time() - int(b.get("ts") or 0)) > 900:
        return jsonify({"success": False, "error": "Stale request."}), 400
    flight_id = int(b.get("flight_id") or 0)
    plan = str(b.get("plan") or "")
    question = str(b.get("question") or "").strip()
    if not flight_id or len(plan) < 40 or not question:
        return jsonify({"success": False, "error": "A flight needs its id, its question and its plan."}), 400
    rounds = max(5, min(40, int(b.get("rounds") or 20)))
    if not _busy.acquire(blocking=False):
        return jsonify({"success": False, "error": "The lab is already flying. One flight at a time."}), 409
    app = current_app._get_current_object()
    title = str(b.get("title") or "Flight")[:80]
    t = threading.Thread(target=_run, args=(app, flight_id, title, question, plan, rounds), daemon=True)
    t.start()
    return jsonify({"success": True, "data": {"flight_id": flight_id, "accepted": True}}), 202


def _wait(fn, ok, bad, timeout, every=10):
    """Poll fn() until ok(result) or bad(result) or timeout. Returns (result, reason)."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if ok(last):
            return last, "ok"
        if bad(last):
            return last, "failed"
        time.sleep(every)
    return last, "timeout"


def _run(app, flight_id, title, question, plan, rounds):
    lab = {}
    try:
        with app.test_client() as c:
            # 1. Read the plan: ontology from the flight plan document.
            _report(flight_id, "reading", "running", "Reading the flight plan.", lab)
            r = c.post("/api/graph/ontology/generate", data={
                "files": (io.BytesIO(plan.encode("utf-8")), "flight_plan.md"),
                "simulation_requirement": question,
                "project_name": title,
            }, content_type="multipart/form-data")
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("Reading the plan failed: " + str(j.get("error") or r.status_code))
            lab["project_id"] = j["data"]["project_id"]

            # 2. Build the world: the memory graph the crowd will live in.
            _report(flight_id, "building", "running", "Building the world from the plan.", lab)
            r = c.post("/api/graph/build", json={"project_id": lab["project_id"]})
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("Building the world failed: " + str(j.get("error") or r.status_code))
            task_id = j["data"]["task_id"]
            res, why = _wait(lambda: (c.get(f"/api/graph/task/{task_id}").get_json(silent=True) or {}).get("data") or {},
                             lambda d: d.get("status") == "completed", lambda d: d.get("status") == "failed", 45 * 60, 15)
            if why != "ok":
                raise RuntimeError("Building the world " + ("failed: " + str(res.get("error")) if why == "failed" else "took too long."))
            proj = (c.get(f"/api/graph/project/{lab['project_id']}").get_json(silent=True) or {}).get("data") or {}
            lab["graph_id"] = proj.get("graph_id")

            # 3. Cast the crowd.
            _report(flight_id, "casting", "running", "Casting the crowd.", lab)
            r = c.post("/api/simulation/create", json={"project_id": lab["project_id"], "graph_id": lab.get("graph_id")})
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("Creating the flight failed: " + str(j.get("error") or r.status_code))
            lab["simulation_id"] = j["data"]["simulation_id"]
            _report(flight_id, "casting", "running", "Casting the crowd.", lab)
            r = c.post("/api/simulation/prepare", json={"simulation_id": lab["simulation_id"]})
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("Casting failed: " + str(j.get("error") or r.status_code))
            ptask = (j.get("data") or {}).get("task_id")
            if not (j.get("data") or {}).get("already_prepared"):
                res, why = _wait(lambda: (c.post("/api/simulation/prepare/status", json={"task_id": ptask, "simulation_id": lab["simulation_id"]}).get_json(silent=True) or {}).get("data") or {},
                                 lambda d: d.get("status") in ("completed", "ready"), lambda d: d.get("status") == "failed", 60 * 60, 15)
                if why != "ok":
                    raise RuntimeError("Casting " + ("failed: " + str(res.get("message") or res.get("error")) if why == "failed" else "took too long."))

            # 4. Fly.
            _report(flight_id, "flying", "running", f"Flying {rounds} rounds.", lab)
            r = c.post("/api/simulation/start", json={"simulation_id": lab["simulation_id"], "platform": "parallel",
                                                      "max_rounds": rounds, "enable_graph_memory_update": True})
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("Take-off failed: " + str(j.get("error") or r.status_code))
            seen = {"round": -1}

            def run_status():
                d = (c.get(f"/api/simulation/{lab['simulation_id']}/run-status").get_json(silent=True) or {}).get("data") or {}
                rd = d.get("current_round")
                if isinstance(rd, int) and rd != seen["round"]:
                    seen["round"] = rd
                    _report(flight_id, "flying", "running", f"Round {rd} of {rounds}.", lab)
                return d
            res, why = _wait(run_status, lambda d: d.get("runner_status") in ("completed", "stopped"),
                             lambda d: d.get("runner_status") == "failed", 4 * 60 * 60, 30)
            if why == "timeout":
                raise RuntimeError("The flight ran past four hours and was left running for review in the back room.")
            # A failed run that recorded actions still gets a debrief, marked partial by the report step.

            # 5. Debrief: the report goes to The Stack through the signed debrief push.
            _report(flight_id, "debriefing", "running", "Writing the debrief." + (" The flight stopped early; the debrief will say it is partial." if why == "failed" else ""), lab)
            r = c.post("/api/report/generate", json={"simulation_id": lab["simulation_id"]})
            j = r.get_json(silent=True) or {}
            if r.status_code >= 400 or not j.get("success"):
                raise RuntimeError("The debrief could not start: " + str(j.get("error") or r.status_code))
            d0 = j.get("data") or {}
            lab["report_id"] = d0.get("report_id")
            if d0.get("status") != "completed" and not d0.get("already_generated"):
                rtask = d0.get("task_id")
                res, why2 = _wait(lambda: (c.post("/api/report/generate/status", json={"task_id": rtask, "simulation_id": lab["simulation_id"]}).get_json(silent=True) or {}).get("data") or {},
                                  lambda d: d.get("status") == "completed", lambda d: d.get("status") == "failed", 60 * 60, 20)
                if why2 != "ok":
                    raise RuntimeError("The debrief " + ("failed." if why2 == "failed" else "took too long."))
                lab["report_id"] = lab.get("report_id") or (res.get("result") or {}).get("report_id")
            _report(flight_id, "landed", "done", "Landed. The debrief is filed in The Stack as a hypothesis.", lab)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Flight {flight_id} failed: {e}")
        _report(flight_id, "failed", "failed", str(e), lab)
    finally:
        _busy.release()
