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
        while not self._stop.is_set():
            try:
                cfg = load_settings().get("screenlogic", {})
                if not cfg.get("enabled"):
                    time.sleep(10)
                    continue

                host     = str(cfg.get("host", "")).strip()
                interval = int(cfg.get("poll_interval", 30))
                if not host:
                    _log.warning("[ScreenLogic] enabled but no host/ip set")
                    time.sleep(interval)
                    continue

                async def _poll_once() -> dict:
                    gw = ScreenLogicGateway()          # v0.11+: ctor takes no args
                    await gw.async_connect(host)
                    await gw.async_update()

                    # ── Temperature & environmental ─────────────────────────
                    air_temp   = gw.get_value(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.AIR_TEMPERATURE)
                    water_temp = (
                        gw.get_value(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.LAST_TEMPERATURE)
                        or gw.get_value(DEVICE.BODY, 0, GROUP.SENSOR, VALUE.LAST_TEMPERATURE)
                    )

                    # ── Chemistry (IntelliChem first, then controller) ─────
                    ph_now  = (
                        gw.get_value(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.PH_NOW)
                        or gw.get_value(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.PH_NOW)
                    )
                    orp_now = (
                        gw.get_value(DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.ORP_NOW)
                        or gw.get_value(DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.ORP_NOW)
                    )

                    # ── Salt cell / chlorine generator ─────────────────────
                    salt_ppm      = gw.get_value(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_PPM)
                    salt_tds_ppm  = gw.get_value(DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_TDS_PPM)
                    super_chlor   = gw.get_value(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLORINATE)
                    super_chlor_t = gw.get_value(DEVICE.SCG, GROUP.SENSOR, VALUE.SUPER_CHLOR_TIMER)

                    # ── Pump telemetry (pump index 0) ──────────────────────
                    pump_rpm   = gw.get_value(DEVICE.PUMP, 0, GROUP.SENSOR, VALUE.RPM_NOW)
                    pump_watts = gw.get_value(DEVICE.PUMP, 0, GROUP.SENSOR, VALUE.WATTS_NOW)
                    pump_gpm   = gw.get_value(DEVICE.PUMP, 0, GROUP.SENSOR, VALUE.GPM_NOW)
                    pump_state = gw.get_value(DEVICE.PUMP, 0, GROUP.CONFIGURATION, VALUE.STATE)

                    # ── Water-balance readings ─────────────────────────────
                    calcium_hardness  = gw.get_value(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CALCIUM_HARDNESS)
                    total_alkalinity  = gw.get_value(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.TOTAL_ALKALINITY)
                    cya               = gw.get_value(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CYA)
                    saturation_index  = gw.get_value(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.SATURATION)
                    corrosive_index   = gw.get_value(DEVICE.CONTROLLER, GROUP.WATER_BALANCE, VALUE.CORROSIVE)

                    await gw.async_disconnect()

                    return {
                        # environmental
                        "air_temp":           air_temp,
                        "water_temp":         water_temp,

                        # chemistry
                        "ph":                 ph_now,
                        "orp":                orp_now,
                        "salt_ppm":           salt_ppm,
                        "salt_tds_ppm":       salt_tds_ppm,

                        # pump
                        "pump_rpm":           pump_rpm,
                        "pump_watts":         pump_watts,
                        "pump_gpm":           pump_gpm,
                        "pump_state":         pump_state,

                        # super-chlorination
                        "super_chlorinate":   super_chlor,
                        "super_chlor_timer":  super_chlor_t,

                        # water-balance
                        "calcium_hardness":   calcium_hardness,
                        "total_alkalinity":   total_alkalinity,
                        "cya":                cya,
                        "saturation_index":   saturation_index,
                        "corrosive_index":    corrosive_index,
                    }

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("[ScreenLogic] update -> %s", new_data)

                # emit via Socket-IO (deferred import avoids circular refs)
                from status_namespace import emit_status_update
                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)
                interval = cfg.get("poll_interval", 30) or 30

            time.sleep(interval)


# Global singleton started from app.py
screenlogic_service = ScreenLogicService()
