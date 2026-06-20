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
from datetime import datetime
from typing import Any, Dict, List, Optional

import eventlet  # Added for consistency
eventlet.monkey_patch()  # Ensure patched

from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings
from services.notification_service import set_status, clear_status
from services.error_service import set_error, clear_error

from eventlet import tpool  # For blocking async in threads

_log = logging.getLogger(__name__)

# Most-recent flattened payload
_latest_data: Dict[str, Any] = {}

# Flap suppression: don't notify until poll has been failing continuously
# for OFFLINE_NOTIFY_THRESHOLD_SEC. Cached data is still cleared immediately.
_first_failure_time: Optional[datetime] = None
OFFLINE_NOTIFY_THRESHOLD_SEC = 60

# Track when the pool pump transitioned to ON, so consumers (e.g. pH alerts)
# can require a "fresh water" period before trusting readings.
_pump_on_since: Optional[datetime] = None


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
        global _first_failure_time, _pump_on_since
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

                # Track pump-on transitions for downstream consumers.
                if snapshot.get("pump.0.state.value") == 1:
                    if _pump_on_since is None:
                        _pump_on_since = datetime.now()
                else:
                    _pump_on_since = None

                _log.debug("[ScreenLogic] update (%d fields)", len(snapshot))
                set_status("screenlogic", "connection", "ok",
                           f"Connected to {host} ({len(snapshot)} fields)")
                clear_error("SCREENLOGIC_OFFLINE")
                _first_failure_time = None

                # broadcast to websocket clients
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)
                now = datetime.now()
                if _first_failure_time is None:
                    _first_failure_time = now
                offline_sec = (now - _first_failure_time).total_seconds()
                # Always invalidate cached data so downstream consumers don't
                # trust stale state during the outage.
                _latest_data.clear()
                _pump_on_since = None
                # Only notify once the outage has lasted past the flap threshold.
                if offline_sec >= OFFLINE_NOTIFY_THRESHOLD_SEC:
                    set_status("screenlogic", "connection", "error",
                               f"Poll failed for {host} for {int(offline_sec)}s: {exc}")
                    set_error("SCREENLOGIC_OFFLINE")

            eventlet.sleep(interval)


# ───────────────────────── public API ───────────────────────────────────────
def get_latest_screenlogic_data() -> Dict[str, Any]:
    """Return a *copy* of the most recent flattened snapshot."""
    return _latest_data.copy()


def get_pump_on_seconds() -> float:
    """Seconds since the pool pump transitioned to ON, or 0 if pump is off /
    state is unknown."""
    if _pump_on_since is None:
        return 0.0
    return (datetime.now() - _pump_on_since).total_seconds()


# singleton created at import-time; app.py calls .start()
screenlogic_service = ScreenLogicService()