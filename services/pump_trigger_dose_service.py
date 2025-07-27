# File: services/pump_trigger_dose_service.py
"""
Pump-triggered auto-dosing service
---------------------------------
• Watches ScreenLogic’s pump.<id>.state.value.
• When the selected pump turns ON, schedules one pH-correction dose after a
  configurable delay.
• Cancels the schedule if the pump turns OFF first.
• Ensures only one dose per calendar day.
"""

from datetime import datetime, timedelta
from typing import Optional

import eventlet

from utils.settings_utils import load_settings
from services.dosage_service import perform_auto_dose
from services.auto_dose_state import auto_dose_state
from services.screenlogic_service import get_latest_screenlogic_data
from status_namespace import is_debug_enabled


def _log(msg: str) -> None:
    if is_debug_enabled("autodose"):
        print(f"[PumpTriggerDose] {datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def pump_trigger_dose_loop() -> None:
    """Background green-thread started via eventlet.spawn()."""
    last_pump_state: Optional[int] = None        # 0 / 1 / None
    scheduled_time: Optional[datetime] = None    # when to dose
    last_dosed_date: Optional[datetime.date] = None

    _log("Pump-trigger auto-dosing loop started")

    while True:
        try:
            settings = load_settings()
            if not settings.get("auto_dosing_enabled", False):
                scheduled_time = None
                last_pump_state = None
                eventlet.sleep(5)
                continue

            pump_id     = int(settings.get("pump_circuit", 0))
            delay_min   = float(settings.get("delay_after_on", 15))

            data       = get_latest_screenlogic_data()
            pump_key   = f"pump.{pump_id}.state.value"
            pump_state = data.get(pump_key)        # 0 / 1 / None

            now = datetime.now()

            # ── new day → clear “already dosed” flag ───────────────────────
            if last_dosed_date and now.date() != last_dosed_date:
                _log("New calendar day – dose flag cleared")
                last_dosed_date = None

            # if ScreenLogic hasn’t reported a valid value yet
            if pump_state not in (0, 1):
                eventlet.sleep(5)
                continue

            # ── OFF → ON transition: schedule a dose ───────────────────────
            if last_pump_state == 0 and pump_state == 1:
                scheduled_time = now + timedelta(minutes=delay_min)
                _log(f"Pump ON – dose scheduled for {scheduled_time:%H:%M:%S}")

            # ── pump turned OFF before the delay expired – cancel ──────────
            if pump_state == 0 and scheduled_time:
                _log("Pump OFF before scheduled dose – cancelling")
                scheduled_time = None

            # ── time to dose? ──────────────────────────────────────────────
            if (
                scheduled_time
                and now >= scheduled_time
                and pump_state == 1
                and last_dosed_date != now.date()
            ):
                dose_type, dose_ml = perform_auto_dose(settings)
                if dose_ml > 0:
                    auto_dose_state.update(
                        {
                            "last_dose_time": now,
                            "last_dose_type": dose_type,
                            "last_dose_amount": dose_ml,
                        }
                    )
                    _log(f"Dosed {dose_ml:.2f} ml ({dose_type})")
                    last_dosed_date = now.date()
                else:
                    _log("No dose required")

                scheduled_time = None   # one-shot complete

            last_pump_state = pump_state
            eventlet.sleep(5)

        except Exception as exc:
            _log(f"ERROR — {exc}")
            eventlet.sleep(5)