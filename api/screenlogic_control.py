"""
Simple control‐endpoint for ScreenLogic.

Payloads accepted (see index.html JS):
--------------------------------------
• {"target":"circuit", "id":505, "action":"toggle"}
• {"target":"heat", "body":0, "mode":2, "setpoint":82}
"""

from __future__ import annotations
import asyncio
from flask import Blueprint, request, jsonify

from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings

import logging
_log = logging.getLogger(__name__)




bp = Blueprint("screenlogic_control", __name__, url_prefix="/api/screenlogic")

# ───────────────────────── helpers ─────────────────────────
def _gw_host() -> str:
    cfg = load_settings().get("screenlogic", {})
    host = str(cfg.get("host", "")).strip()
    if not host:
        raise RuntimeError("ScreenLogic host/IP not configured")
    return host

# ───────────────────────── routes ──────────────────────────
@bp.route("/control", methods=["POST"])
def control():
    data = request.get_json(force=True) or {}
    print(f"Raw content type: {request.content_type}")
    print(f"Raw request body: {request.data}")
    print(f"Received payload: {data}")
    target = data.get("target")

    try:
        host = _gw_host()
        gw   = ScreenLogicGateway()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(gw.async_connect(host))

        # ───────── CIRCUIT ON / OFF / TOGGLE ─────────
        if target == "circuit":
            cid   = int(data.get("id", -1))
            if cid < 0:
                raise KeyError("id")

            action = data.get("action", "toggle")
            current = gw.get_value("circuit", cid, "value") or 0
            new_state = {"on": 1, "off": 0}.get(action, 1 - current)
            loop.run_until_complete(gw.async_set_circuit(cid, new_state))

        # ───────── HEAT MODE / SET-POINT ─────────
        elif target == "heat":
            body  = int(data.get("body", -1))
            mode  = int(data.get("mode", 0))
            setpt = int(data.get("setpoint", 0))

            if body not in (0, 1):
                raise KeyError("body")
            if mode  not in (0, 1, 2, 3):
                raise KeyError("mode")
            if not (50 <= setpt <= 104):
                raise KeyError("setpoint")

            loop.run_until_complete(gw.async_set_heat_mode(body, mode))
            loop.run_until_complete(gw.async_set_heat_temp(body, setpt))

        else:
            raise ValueError(f"unsupported target {target!r}")

        loop.run_until_complete(gw.async_disconnect())
        return jsonify(status="success")

    except KeyError as ke:
        return jsonify(status="failure",
                       error=f"missing/invalid field {ke}"), 400
    except Exception as exc:
        return jsonify(status="failure", error=str(exc)), 400