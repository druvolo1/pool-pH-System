"""ScreenLogic polling service for the Pool-pH controller
   ------------------------------------------------------
   • Polls on a background thread.
   • Harvests *all* scalar values published by screenlogicpy.
   • Exposes them via get_latest_screenlogic_data().
"""

from __future__ import annotations

import asyncio, logging, threading, time
from typing import Any, Dict, List

from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings

_log = logging.getLogger(__name__)
_latest_data: Dict[str, Any] = {}      # last good poll → read by status_namespace


# ───────────────────────── helpers ──────────────────────────
def _flatten_screenlogic(data: dict) -> Dict[str, Any]:
    """
    Recursively walk `data` (as returned by gw.get_data()) and build a flat
    dict whose keys are joined by '.' and whose values are whatever is stored
    in each leaf's **"value"** field.  Everything else (units, names, etc.) is
    ignored so the payload stays compact and JSON-serialisable.
    """
    flat: Dict[str, Any] = {}

    def _walk(path: List[str], node: Any) -> None:
        # leaf with a scalar 'value'
        if isinstance(node, dict) and "value" in node:
            flat[".".join(path)] = node["value"]
            return
        # internal node → recurse
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(path + [str(k)], v)

    _walk([], data)
    return flat


# ───────────────────────── service class ────────────────────
class ScreenLogicService:
    """Daemon thread that polls the Pentair ScreenLogic gateway."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="ScreenLogicPoller", daemon=True
        )
        self._thread.start()
        _log.info("[ScreenLogic] service thread started")

    def stop(self) -> None:
        self._stop.set()

    # ───────────────────────── main loop ─────────────────────
    def _run(self) -> None:
        while not self._stop.is_set():
            cfg = load_settings().get("screenlogic", {})
            interval = int(cfg.get("poll_interval", 5)) or 30

            try:
                if not cfg.get("enabled"):
                    time.sleep(10)
                    continue

                host = str(cfg.get("host", "")).strip()
                if not host:
                    _log.warning("[ScreenLogic] enabled but no host/IP set")
                    time.sleep(interval)
                    continue

                async def _poll_once() -> Dict[str, Any]:
                    gw = ScreenLogicGateway()
                    await gw.async_connect(host)
                    await gw.async_update()
                    flat = _flatten_screenlogic(gw.get_data())
                    await gw.async_disconnect()
                    return flat

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("[ScreenLogic] update: %s", new_data)

                # push to websocket clients (import here → no circular-import)
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)

            time.sleep(interval)


# ───────────────────────── public API ───────────────────────
def get_latest_screenlogic_data() -> Dict[str, Any]:
    """Return a *copy* of the most recent flattened ScreenLogic snapshot."""
    return _latest_data.copy()


# singleton used by app.py
screenlogic_service = ScreenLogicService()
