# File: services/salt_monitor_service.py
"""
Salt-level monitor
------------------
• Polls ScreenLogic's salt_ppm value every minute.
• Reads salt_range.{min,max} from settings.
• Sends a Telegram/Discord alert when salt is outside range.
• Throttles to one alert per condition per 24 hours; throttle state is
  persisted to disk so service restarts can't bypass it.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import eventlet

from utils.settings_utils import load_settings
from services.screenlogic_service import get_latest_screenlogic_data
from services.notification_service import _send_telegram_and_discord


_STATE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "salt_alerts.json")
)
_ALERT_INTERVAL = timedelta(hours=24)
_POLL_INTERVAL_SEC = 60

_last_alert: Dict[str, datetime] = {}


def _load() -> None:
    try:
        with open(_STATE_FILE) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    for k, v in raw.items():
        try:
            _last_alert[k] = datetime.fromisoformat(v)
        except (TypeError, ValueError):
            pass


def _save() -> None:
    snapshot = {k: v.isoformat() for k, v in _last_alert.items()}
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snapshot, f, indent=2)
    os.replace(tmp, _STATE_FILE)


def _maybe_alert(key: str, message: str, now: datetime) -> bool:
    last = _last_alert.get(key)
    if last is not None and (now - last) < _ALERT_INTERVAL:
        return False
    _last_alert[key] = now
    _save()
    _send_telegram_and_discord(message)
    return True


def salt_monitor_loop() -> None:
    _load()
    print("[SaltMonitor] loop started", flush=True)

    while True:
        try:
            settings = load_settings()
            salt_range = settings.get("salt_range", {})
            min_salt = salt_range.get("min")
            max_salt = salt_range.get("max")

            if min_salt is None and max_salt is None:
                eventlet.sleep(_POLL_INTERVAL_SEC)
                continue

            data = get_latest_screenlogic_data()
            salt = data.get("controller.sensor.salt_ppm.value")

            if not isinstance(salt, (int, float)) or salt <= 0:
                eventlet.sleep(_POLL_INTERVAL_SEC)
                continue

            now = datetime.now()
            if max_salt is not None and salt > max_salt:
                _maybe_alert(
                    "salt_too_high",
                    f"Salt {salt} ppm is ABOVE max threshold ({max_salt} ppm).",
                    now,
                )
            elif min_salt is not None and salt < min_salt:
                _maybe_alert(
                    "salt_too_low",
                    f"Salt {salt} ppm is BELOW min threshold ({min_salt} ppm).",
                    now,
                )

        except Exception as exc:
            print(f"[SaltMonitor] error: {exc}", flush=True)

        eventlet.sleep(_POLL_INTERVAL_SEC)
