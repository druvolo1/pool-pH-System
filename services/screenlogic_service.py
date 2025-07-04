"""ScreenLogic polling service (thread-based) for the Pool-pH controller."""

from __future__ import annotations

import asyncio, logging, threading, time
from screenlogicpy import ScreenLogicGateway
from screenlogicpy.const.data import DEVICE, GROUP, VALUE
from utils.settings_utils import load_settings

_log = logging.getLogger(__name__)
_latest_data: dict = {}        # last good poll → read by status_namespace


def get_latest_screenlogic_data() -> dict:
    """Return a snapshot of the most recent ScreenLogic reading."""
    return _latest_data.copy()


class ScreenLogicService:
    """Runs in its own daemon thread and polls the Pentair ScreenLogic gateway."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ───────────────────────── start / stop ─────────────────────────
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

    # ───────────────────────── main loop ────────────────────────────
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
                    gw = ScreenLogicGateway()              # v0.11+: ctor no args
                    await gw.async_connect(host)
                    await gw.async_update()

                    # — air temperature is always under controller/sensor —
                    air_temp = gw.get_value(
                        DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.AIR_TEMPERATURE
                    )

                    # — water temperature: newer firmware stores it per-BODY —
                    water_temp = gw.get_value(
                        DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.LAST_TEMPERATURE
                    )
                    if water_temp is None:  # fall back to first body (usually pool)
                        water_temp = gw.get_value(
                            DEVICE.BODY, 0, GROUP.SENSOR, VALUE.LAST_TEMPERATURE
                        )

                    # — chemistry: IntelliChem if present, else controller —
                    ph_now = gw.get_value(
                        DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.PH_NOW
                    )
                    if ph_now is None:
                        ph_now = gw.get_value(
                            DEVICE.CONTROLLER, GROUP.SENSOR, VALUE.PH_NOW
                        )

                    orp_now = gw.get_value(
                        DEVICE.INTELLICHEM, GROUP.SENSOR, VALUE.ORP_NOW
                    )
                    salt_ppm = gw.get_value(
                        DEVICE.SCG, GROUP.SENSOR, VALUE.SALT_PPM
                    )

                    await gw.async_disconnect()
                    return {
                        "air_temp":   air_temp,
                        "water_temp": water_temp,
                        "ph":         ph_now,
                        "orp":        orp_now,
                        "salt_ppm":   salt_ppm,
                    }

                new_data = asyncio.run(_poll_once())
                _latest_data.clear()
                _latest_data.update(new_data)
                _log.debug("[ScreenLogic] update -> %s", new_data)

                # defer import (avoids circular import on module load)
                from status_namespace import emit_status_update

                emit_status_update(force_emit=True)

            except Exception as exc:
                _log.warning("[ScreenLogic] poll failed: %s", exc)
                interval = cfg.get("poll_interval", 30) or 30

            time.sleep(interval)


# global singleton started from app.py
screenlogic_service = ScreenLogicService()
