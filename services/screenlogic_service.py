"""ScreenLogic polling service – *full* data export
   -------------------------------------------------
   • Runs on a background thread.
   • Retrieves the gateway’s complete data tree.
   • Flattens every scalar field (int / float / str / bool).
   • Exposes last snapshot via get_latest_screenlogic_data().
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

import eventlet  # Added for consistency
eventlet.monkey_patch()  # Ensure patched

from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings

from eventlet import tpool  # For blocking async in threads

_log = logging.getLogger(__name__)

# Most-recent flattened payload
_latest_data: Dict[str, Any] = {}


# ───────────────────────── helper: flatten any ScreenLogic tree ─────────────
def _flatten(node: Any, path: List[str], out: Dict[str, Any]) -> None:
    """
    Recursively walk `node` (dict / list / scalar) and append any scalar values
    to `out` using a '.'-joined path.
    """
    # scalars we keep
    if isinstance(node, (int, float, str, bool)) or node is None:
        out[".".join(path)] = node
        return

    # dict → recurse into items
    if isinstance(node, dict):
        for k, v in node.items():
            _flatten(v, path + [str(k)], out)
        return

    # list → recurse with index
    if isinstance(node, list):
        for idx, itm in enumerate(node):
            _flatten(itm, path + [str(idx)], out)
        return


def flatten_screenlogic(data_tree: dict) -> Dict[str, Any]:
    """Return a flat { dotted.path : scalar } dict for *all* values."""
    flat: Dict[str, Any] = {}
    _flatten(data_tree, [], flat)
    return flat


# ───────────────────────── ScreenLogic service class ────────────────────────
class ScreenLogicService:
    def __init__(self) -> None:
        self._stop = eventlet.Event()  # Use eventlet Event for consistency

    # start / stop -----------------------------------------------------------
    def start(self) -> None:
        eventlet.spawn(self._run)  # Use eventlet.spawn like other services
        _log.info("[ScreenLogic] service greenlet started")

    def stop(self) -> None:
        self._stop.send()

    # main loop --------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.ready():
            cfg = load_settings().get("screenlogic", {})
            interval = int(cfg.get("poll_interval", 5)) or 5

            try:
                if not cfg.get("enabled"):
                    eventlet.sleep(10)
                    continue

                host = str(cfg.get("host", "")).strip()
                if not host:
                    _log.warning("[ScreenLogic] enabled but no host/IP in settings")
                    eventlet.sleep(interval)
                    continue

                def sync_poll() -> Dict[str, Any]:
                    # Run async poll in a sync wrapper for tpool
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        gw = ScreenLogicGateway()
                        loop.run_until_complete(gw.async_connect(host))
                        loop.run_until_complete(gw.async_update())
                        flat = flatten_screenlogic(gw.get_data())
                        loop.run_until_complete(gw.async_disconnect())
                        return flat
                    finally:
                        loop.close()

                # Run the async poll in a real thread to avoid eventlet conflicts
                snapshot = tpool.execute(sync_poll)

                _latest_data.clear()
                _latest_data.update(snapshot)

                _log.debug("[ScreenLogic] update (%d fields)", len(snapshot))

                # broadcast to websocket clients
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)

            eventlet.sleep(interval)


# ───────────────────────── public API ───────────────────────────────────────
def get_latest_screenlogic_data() -> Dict[str, Any]:
    """Return a *copy* of the most recent flattened snapshot."""
    return _latest_data.copy()


# singleton created at import-time; app.py calls .start()
screenlogic_service = ScreenLogicService()