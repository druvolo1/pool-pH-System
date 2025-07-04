"""ScreenLogic polling service (thread-based) for the Pool-pH controller."""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from screenlogicpy import ScreenLogicGateway
from screenlogicpy.const.data import DEVICE, GROUP, VALUE

from utils.settings_utils import load_settings

_log = logging.getLogger(__name__)
_latest_data: dict = {}      # last good poll → read by status_namespace


def get_latest_screenlogic_data() -> dict:
    """Return a defensive-copy of the most recent ScreenLogic reading."""
    return _latest_data.copy()


class ScreenLogicService:
    """Daemon thread that polls the Pentair ScreenLogic gateway."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ────────────────────────────── start / stop ─────────────────────────────
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
        """Poll the ScreenLogic gateway on the configured interval."""
        while not self._stop.is_set():
            cfg = load_settings().get("screenlogic", {})
            interval = int(cfg.get("poll_interval", 30)) or 30

            try:
                if not cfg.get("enabled"):
                    time.sleep(10)
                    continue

                host = str(cfg.get("host", "")).strip()
                if not host:
                    _log.warning("ScreenLogic enabled but no host/IP set in settings")
                    time.sleep(interval)
                    continue

                async def _poll_once() -> dict:
                    gw = ScreenLogicGateway()
                    await gw.async_connect(host)
                    await gw.async_update()          # full poll

                    # helpers
                    val = gw.get_value
                    body_ids  = list((gw.get_data(DEVICE.BODY)  or {}).keys())
                    pump_ids  = list((gw.get_data(DEVICE.PUMP)  or {}).keys())
                    body0     = body_ids[0]  if body_ids else None
                    pump0     = pump_ids[0]  if pump_ids else None

                    data = {
                        # environmental
                        "air_temp":  val(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.AIR_TEMPERATURE),
                        "water_temp": (
                            val(DEVICE.BODY, body0, GROUP.SENSOR, VALUE.LAST_TEMPERATURE)
                            if body0 is not None else None
                        ),
                        # chemistry
                        "ph":         val(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.PH_NOW),
                        "orp":        val(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.ORP_NOW),
                        "salt_ppm":   val(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_PPM),
                        "salt_tds_ppm": val(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_TDS_PPM),
                        # water balance
                        "calcium_hardness":  val(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CALCIUM_HARDNESS),
                        "total_alkalinity":  val(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.TOTAL_ALKALINITY),
                        "cya":              val(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CYA),
                        "saturation_index": val(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.SATURATION),
                        "corrosive_index":  val(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CORROSIVE),
                        # pump-related
                        "pump_rpm":   val(DEVICE.PUMP, pump0, VALUE.RPM_NOW)   if pump0 is not None else None,
                        "pump_watts": val(DEVICE.PUMP, pump0, VALUE.WATTS_NOW) if pump0 is not None else None,
                        "flow_gpm":   val(DEVICE.PUMP, pump0, VALUE.GPM_NOW)   if pump0 is not None else None,
                        "pump_state": val(DEVICE.PUMP, pump0, VALUE.STATE)     if pump0 is not None else None,
                        # SCG super-chlorination
                        "super_chlorinate": val(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLORINATE),
                        "super_chlor_timer": val(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLOR_TIMER),
                    }

                    await gw.async_disconnect()
                    return data

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("[ScreenLogic] update: %s", new_data)

                # circular-import safe
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)

            time.sleep(interval)


# singleton
screenlogic_service = ScreenLogicService()
