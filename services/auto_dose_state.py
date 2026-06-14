# File: services/auto_dose_state.py
import json
import os
from datetime import datetime

_STATE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "auto_dose_state.json")
)

auto_dose_state = {
    "last_dose_time": None,
    "last_dose_type": None,
    "last_dose_amount": 0.0,
}


def _load() -> None:
    try:
        with open(_STATE_FILE) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    t = raw.get("last_dose_time")
    if isinstance(t, str):
        try:
            raw["last_dose_time"] = datetime.fromisoformat(t)
        except ValueError:
            raw["last_dose_time"] = None
    auto_dose_state.update(raw)


def save() -> None:
    snapshot = dict(auto_dose_state)
    if isinstance(snapshot.get("last_dose_time"), datetime):
        snapshot["last_dose_time"] = snapshot["last_dose_time"].isoformat()
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    tmp = _STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snapshot, f, indent=2)
    os.replace(tmp, _STATE_FILE)


_load()
