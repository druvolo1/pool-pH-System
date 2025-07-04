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
    data = request.get_json() or {}
    target = data.get("target")

    try:
        host = _gw_host()

        async def _do():
            gw = ScreenLogicGateway()
            await gw.async_connect(host)

            if target == "circuit":
                cid      = int(data["id"])
                action   = data.get("action", "toggle")
                current  = gw.get_value("circuit", cid, "value")
                new_state = 0 if current else 1               # default toggle
                if action == "on":  new_state = 1
                if action == "off": new_state = 0
                await gw.async_set_circuit_state(cid, new_state)

            elif target == "heat":
                body     = int(data["body"])
                mode     = int(data["mode"])
                setpt    = int(data["setpoint"])
                await gw.async_set_heat_mode(body, mode)
                await gw.async_set_heat_setpoint(body, setpt)

            else:
                raise ValueError(f"Unsupported target: {target}")

            await gw.async_disconnect()

        asyncio.run(_do())
        return jsonify(status="success")

    except Exception as exc:
        return jsonify(status="failure", error=str(exc)), 400
