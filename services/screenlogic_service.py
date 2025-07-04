"""ScreenLogic polling service (thread-based) for the Pool-pH controller.

Runs in its own **daemon thread** so the Eventlet worker stays responsive.
Each cycle connects to the Pentair ScreenLogic protocol-adapter,
pulls the latest data, and stores it for the web UI.
"""

import threading, time, asyncio, logging
from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings
from status_namespace import emit_status_update

_log = logging.getLogger(__name__)
_latest_data: dict = {}          # last good reading → picked up by status_namespace


def get_latest_screenlogic_data() -> dict:
    """Return the most recent data pulled from the gateway."""
    return _latest_data.copy()


class ScreenLogicService:
    """Background thread that polls the ScreenLogic gateway at a fixed interval."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ─────────────────────────────────────────────────────────────── start / stop
    def start(self) -> None:
        """Spawn the poller once (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="ScreenLogicPoller", daemon=True
        )
        self._thread.start()
        _log.info("ScreenLogic service thread started")

    def stop(self) -> None:
        """Signal the poller to exit (not used by the app, but here for completeness)."""
        self._stop.set()

    # ─────────────────────────────────────────────────────────────────── main loop
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cfg = load_settings().get("screenlogic", {})
                if not cfg.get("enabled", False):
                    time.sleep(10)
                    continue

                host = cfg.get("host")
                interval = int(cfg.get("poll_interval", 30))

                async def _poll_once() -> dict:
                    gateway = ScreenLogicGateway(host=host)
                    await gateway.async_connect()
                    await gateway.async_update()
                    data = {
                        "water_temp": gateway.get_pool_temp(),
                        "air_temp":   gateway.get_air_temp(),
                        "ph":         gateway.get_ph(),
                    }
                    await gateway.async_disconnect()
                    return data

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("ScreenLogic update: %s", new_data)

                # push to the front-end
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("ScreenLogic poll failed: %s", exc)
                interval = 30   # fall-back if cfg missing or bad

            time.sleep(interval)


# single global instance (started from app.py)
screenlogic_service = ScreenLogicService()
