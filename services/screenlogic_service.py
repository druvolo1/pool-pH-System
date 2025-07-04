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
from screenlogicpy.const.data import DEVICE, GROUP, VALUE   # add to imports …

# ---------------------------------------------------------------------------
def _run(self) -> None:
    """Background worker: poll the ScreenLogic gateway at the configured interval."""
    while not self._stop.is_set():
        try:
            cfg = load_settings().get("screenlogic", {})
            if not cfg.get("enabled"):
                time.sleep(10)
                continue

            host      = cfg.get("host")
            interval  = int(cfg.get("poll_interval", 30))

            async def _poll_once() -> dict:
                gw = ScreenLogicGateway()                 # ctor no longer takes host/port
                await gw.async_connect(host)              # pass IP here
                await gw.async_update()                   # pull every data set we can
                data = {
                    # controller-level sensors
                    "air_temp": gw.get_value(
                        DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.AIR_TEMPERATURE
                    ),
                    "water_temp": gw.get_value(          # works for single-body pools
                        DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.LAST_TEMPERATURE
                    ),
                    # chemistry (IntelliChem / chemistry board); will be None if absent
                    "ph": gw.get_value(
                        DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.PH_NOW
                    ),
                }
                await gw.async_disconnect()
                return data

            new_data = asyncio.run(_poll_once())
            _latest_data.clear()
            _latest_data.update(new_data)
            _log.debug("ScreenLogic update: %s", new_data)

            # defer import → avoids circular-import on module load
            from status_namespace import emit_status_update
            emit_status_update(force_emit=True)

        except Exception as exc:
            _log.warning("ScreenLogic poll failed: %s", exc)
            interval = cfg.get("poll_interval", 30) or 30   # fallback

        time.sleep(interval)




# global singleton started from app.py
screenlogic_service = ScreenLogicService()
