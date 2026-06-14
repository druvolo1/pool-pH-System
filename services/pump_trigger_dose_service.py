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
from services.auto_dose_state import auto_dose_state, save as save_auto_dose_state
from services.notification_service import _send_telegram_and_discord
from services.ph_service import get_latest_ph_reading
from services.screenlogic_service import get_latest_screenlogic_data
from status_namespace import is_debug_enabled


def _log(msg: str) -> None:
    if is_debug_enabled("autodose"):
        print(f"[PumpTriggerDose] {datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def pump_trigger_dose_loop() -> None:
    """Background green-thread started via eventlet.spawn()."""
    last_pump_state: Optional[int] = None        # 0 / 1 / None
    scheduled_time: Optional[datetime] = None    # when to dose

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
            # EasyTouch circuit IDs (match home page constants)
            spa_state  = data.get("circuit.500.value")
            pool_state = data.get("circuit.505.value")

            now = datetime.now()

            # Derive last-dosed-date from the persisted auto_dose_state so a
            # service restart can't undo the one-dose-per-day gate.
            last_dose_time = auto_dose_state.get("last_dose_time")
            last_dosed_date = (
                last_dose_time.date() if isinstance(last_dose_time, datetime) else None
            )

            # if ScreenLogic hasn't reported a valid value yet
            if pump_state not in (0, 1):
                eventlet.sleep(5)
                continue

            # OFF → ON transition OR cold-start with pump already running.
            # The date check below still prevents double-dosing after restart.
            # Don't schedule if spa is on - acid would go to the spa, not the pool.
            if pump_state == 1 and last_pump_state in (0, None):
                if spa_state == 1:
                    _log(f"Pump ON but spa is also on - skipping dose schedule")
                else:
                    scheduled_time = now + timedelta(minutes=delay_min)
                    _log(f"Pump ON (prev={last_pump_state}) - dose scheduled for {scheduled_time:%H:%M:%S}")

            # Pump turned OFF before delay expired - cancel
            if pump_state == 0 and scheduled_time:
                _log("Pump OFF before scheduled dose - cancelling")
                scheduled_time = None

            # Spa turned on during the delay - cancel (water now routed to spa)
            if spa_state == 1 and scheduled_time:
                _log("Spa ON before scheduled dose - cancelling (acid would go to spa)")
                scheduled_time = None

            # Time to dose? Require pool ON and spa OFF.
            if (
                scheduled_time
                and now >= scheduled_time
                and pump_state == 1
                and spa_state == 0
                and pool_state == 1
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
                    save_auto_dose_state()
                    _log(f"Dosed {dose_ml:.2f} ml ({dose_type})")
                    try:
                        ph_now = get_latest_ph_reading()
                        ph_text = f"{ph_now:.2f}" if ph_now is not None else "n/a"
                        _send_telegram_and_discord(
                            f"Auto-dose: {dose_ml:.0f} ml pH {dose_type} "
                            f"(current pH {ph_text}) at {now:%Y-%m-%d %H:%M}"
                        )
                    except Exception as nex:
                        _log(f"dose-notify failed: {nex}")
                else:
                    _log("No dose required")

                scheduled_time = None   # one-shot complete

            last_pump_state = pump_state
            eventlet.sleep(5)

        except Exception as exc:
            _log(f"ERROR - {exc}")
            eventlet.sleep(5)