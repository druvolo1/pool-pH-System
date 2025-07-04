"""ScreenLogic polling service (thread-based) for the Pool-pH controller."""

import threading, time, asyncio, logging
from screenlogicpy import ScreenLogicGateway
from utils.settings_utils import load_settings

_log = logging.getLogger(__name__)
_latest_data: dict = {}           # last good poll → picked up by status_namespace


def get_latest_screenlogic_data() -> dict:
    """Return a *copy* of the most recent ScreenLogic reading."""
    return _latest_data.copy()


class ScreenLogicService:
    """Background thread that polls the Pentair ScreenLogic gateway."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ───────────────────────────── start / stop ──────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="ScreenLogicPoller", daemon=True
        )
        self._thread.start()
        _log.info("ScreenLogic service thread started")

    def stop(self) -> None:
        self._stop.set()

    # ───────────────────────────── main loop ─────────────────────────────────
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cfg = load_settings().get("screenlogic", {})
                if not cfg.get("enabled", False):
                    time.sleep(10)
                    continue

                host = cfg.get("host", "").strip()
                interval = int(cfg.get("poll_interval", 30))

                # ─── guard: must have a host/ip ───
                if not host:
                    _log.warning("ScreenLogic enabled but no host/ip set in settings.json")
                    time.sleep(interval)
                    continue

                async def _poll_once() -> dict:
                    gw = ScreenLogicGateway()          # ← ctor takes no args
                    await gw.async_connect(host)       # ← pass IP/host here
                    await gw.async_update()

                    data = {
                        "water_temp": gw.get_pool_temp(),
                        "air_temp":   gw.get_air_temp(),
                        "ph":         gw.get_ph(),
                    }

                    await gw.async_disconnect()
                    return data

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("ScreenLogic update: %s", new_data)

                # emit update (import here to avoid circular import)
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("ScreenLogic poll failed: %s", exc)
                interval = 30  # fallback delay if cfg missing/bad

            time.sleep(interval)



# global singleton started from app.py
screenlogic_service = ScreenLogicService()
