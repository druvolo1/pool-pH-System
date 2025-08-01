import json, os, subprocess, stat, glob
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

from status_namespace import emit_status_update
from services.auto_dose_utils import reset_auto_dose_timer
from utils.settings_utils import load_settings, save_settings

settings_blueprint = Blueprint("settings", __name__)
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")
PROGRAM_VERSION = "1.0.5"

# ─────────────────────────── default settings ───────────────────────────
_DEFAULTS = {
    "system_name": "Pool-pH",
    "ph_range": {"min": 7.2, "max": 7.8},
    "ph_target": 7.5,
    "max_dosing_amount": 5,
    "dosing_interval": 1.0,
    "system_volume": 35000.0,
    "dosage_strength": {"ph_up": 1.0, "ph_down": 1.0},
    "auto_dosing_enabled": False,
    "pump_trigger": {"pump_id": 0, "dose_delay_min": 15},
    "time_zone": "America/New_York",
    "daylight_savings_enabled": True,
    "usb_roles": {"ph_probe": None, "relay": None},
    "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
    "relay_ports": {"ph_up": 1, "ph_down": 2},
    "discord_enabled": False,
    "discord_webhook_url": "",
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "ph_jump_threshold": 1.0,
    "ph_median_window": 3,
    "ph_stability_threshold": 0.2,
    "screenlogic": {           # NEW – Pentair gateway config
        "enabled": True,
        "host": "172.16.1.197",
        "poll_interval": 5    # seconds
    }
}

if not os.path.exists(SETTINGS_FILE):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as fp:
        json.dump(_DEFAULTS, fp, indent=4)

# -------------- helpers (unchanged from your previous file) --------------
def _ensure_executable(path: str):
    if not os.path.isfile(path):
        return
    mode = os.stat(path).st_mode
    if not (mode & stat.S_IXUSR):
        subprocess.run(["chmod", "+x", path], check=True)

# ─────────────────────────── routes ────────────────────────────────────────────
@settings_blueprint.route("/", methods=["GET"])
def get_settings():
    data = load_settings()
    data["program_version"] = PROGRAM_VERSION
    return jsonify(data)


@settings_blueprint.route("/", methods=["POST"])
def update_settings():
    new_settings = request.get_json() or {}
    current = load_settings()

    dosing_keys = {"auto_dosing_enabled", "pump_trigger"}
    auto_dosing_changed = bool(dosing_keys.intersection(new_settings.keys()))

    # merge relay_ports if present
    if "relay_ports" in new_settings:
        current.setdefault("relay_ports", {}).update(new_settings.pop("relay_ports"))
    if "pump_trigger" in new_settings:
        current.setdefault("pump_trigger", {}).update(new_settings.pop("pump_trigger"))

    current.update(new_settings)
    save_settings(current)

    if auto_dosing_changed:
        reset_auto_dose_timer()

    emit_status_update()
    return jsonify({"status": "success", "settings": current})


@settings_blueprint.route("/usb_devices", methods=["GET"])
def list_usb_devices():
    """
    Enumerate every likely serial device and prune usb_roles that point
    to vanished paths.
    """
    patterns = [
        "/dev/serial/by-path/*",
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ]
    paths = []
    for pat in patterns:
        paths.extend(glob.glob(pat))

    devices = [{"device": p} for p in sorted(paths)]

    settings = load_settings()
    usb_roles = settings.setdefault("usb_roles", {"ph_probe": None, "relay": None})

    connected = {d["device"] for d in devices}
    changed = False
    for role, assigned in list(usb_roles.items()):
        if assigned and assigned not in connected:
            usb_roles[role] = None
            changed = True
    if changed:
        save_settings(settings)

    emit_status_update()
    return jsonify(devices)


@settings_blueprint.route("/assign_usb", methods=["POST"])
def assign_usb():
    data = request.get_json() or {}
    role = data.get("role")
    device = data.get("device")

    if role not in ("ph_probe", "relay"):
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    settings = load_settings()
    settings.setdefault("usb_roles", {"ph_probe": None, "relay": None})

    # prevent duplicates
    for other_role, assigned in settings["usb_roles"].items():
        if assigned == device and other_role != role:
            return (
                jsonify({"status": "failure", "error": f"Device already assigned to {other_role}"}),
                400,
            )

    settings["usb_roles"][role] = device or None
    save_settings(settings)

    # restart services if needed
    if role == "ph_probe":
        from services.ph_service import restart_serial_reader

        restart_serial_reader()
    elif role == "relay":
        from services.pump_relay_service import reinitialize_relay_service

        reinitialize_relay_service()

    emit_status_update()
    return jsonify({"status": "success", "usb_roles": settings["usb_roles"]})


@settings_blueprint.route("/export", methods=["GET"])
def export_settings():
    return send_file(SETTINGS_FILE, mimetype="application/json", as_attachment=True, download_name="settings.json")
