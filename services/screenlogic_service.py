"""ScreenLogic polling service (thread-based) for the Pool-pH controller."""

from __future__ import annotations

import asyncio, logging, threading, time
from screenlogicpy import ScreenLogicGateway
from screenlogicpy.const.data import DEVICE, GROUP, VALUE
from utils.settings_utils import load_settings

_log = logging.getLogger(__name__)
_latest_data: dict = {}           # last good poll → read by status_namespace


def get_latest_screenlogic_data() -> dict:
    """Return a snapshot of the most recent ScreenLogic reading."""
    return _latest_data.copy()


class ScreenLogicService:
    """Background thread that polls the Pentair ScreenLogic gateway."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ─────────────────────────────── start / stop ────────────────────────────
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

    # ─────────────────────────────── main loop ───────────────────────────────
    def _run(self) -> None:
        """Worker thread: poll ScreenLogic gateway on the configured interval."""
        while not self._stop.is_set():
            try:
                cfg = load_settings().get("screenlogic", {})
                if not cfg.get("enabled"):
                    time.sleep(10)
                    continue

                host      = str(cfg.get("host", "")).strip()
                interval  = int(cfg.get("poll_interval", 30))
                if not host:
                    _log.warning("ScreenLogic enabled but no host/ip set")
                    time.sleep(interval)
                    continue

                async def _poll_once() -> dict:
                    gw = ScreenLogicGateway()          # ctor takes no args (v 0.10+)
                    await gw.async_connect(host)
                    await gw.async_update()            # pulls *all* data trees

                    # ───── body / pump id helpers ─────
                    bodies = list((gw.get_data(DEVICE.BODY) or {}).keys())
                    pools_body_id = bodies[0] if bodies else None

                    pumps = list((gw.get_data(DEVICE.PUMP) or {}).keys())
                    pump0 = pumps[0] if pumps else None

                    def v(*path):                          # convenience
                        return gw.get_value(*path)

                    data = {
                        # environmental
                        "air_temp":       v(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.AIR_TEMPERATURE),
                        "water_temp":     v(DEVICE.BODY, pools_body_id, GROUP.SENSOR, VALUE.LAST_TEMPERATURE)
                                            if pools_body_id is not None else None,

                        # chemistry (IntelliChem)
                        "ph":             v(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.PH_NOW),
                        "orp":            v(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.ORP_NOW),

                        # salt-cell
                        "salt_ppm":       v(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_PPM),
                        "salt_tds_ppm":   v(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_TDS_PPM),
                        "super_chlorinate": v(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLORINATE),
                        "super_chlor_timer": v(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLOR_TIMER),

                        # water balance (IntelliChem)
                        "calcium_hardness": v(DEVICE.INTELLICHEM, GROUP.WATER_BALANCE, VALUE.CALCIUM_HARDNESS),
                        "total_alkalinity": v(DEVICE.INTELLICHEM, GROUP.WATER_BALANCE, VALUE.TOTAL_ALKALINITY),
                        "cya":              v(DEVICE.INTELLICHEM, GROUP.WATER_BALANCE, VALUE.CYA),
                        "saturation_index": v(DEVICE.INTELLICHEM, GROUP.WATER_BALANCE, VALUE.SATURATION),
                        "corrosive_index":  v(DEVICE.INTELLICHEM, GROUP.WATER_BALANCE, VALUE.CORROSIVE),

                        # first-pump snapshot
                        "pump_rpm":     v(DEVICE.PUMP, pump0, VALUE.RPM_NOW)   if pump0 is not None else None,
                        "pump_watts":   v(DEVICE.PUMP, pump0, VALUE.WATTS_NOW) if pump0 is not None else None,
                        "pump_gpm":     v(DEVICE.PUMP, pump0, VALUE.GPM_NOW)   if pump0 is not None else None,
                        "pump_state":   v(DEVICE.PUMP, pump0, VALUE.STATE)     if pump0 is not None else None,
                    }

                    await gw.async_disconnect()
                    return data

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("ScreenLogic update: %s", new_data)

                # avoid circular import
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("ScreenLogic poll failed: %s", exc)
                interval = cfg.get("poll_interval", 30) or 30

            time.sleep(interval)


# Global singleton started from app.py
screenlogic_service = ScreenLogicService()
