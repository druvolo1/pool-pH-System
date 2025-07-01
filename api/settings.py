from flask import Blueprint, request, jsonify, render_template, send_file
import json
import os
import subprocess
import stat
from datetime import datetime

from status_namespace import emit_status_update
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from utils.settings_utils import load_settings, save_settings

import requests  # For sending the Discord test POST

import glob

settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# >>> Define your in-code program version here <<<
PROGRAM_VERSION = "1.0.62"

# Ensure the settings file exists with default values
if not os.path.exists(SETTINGS_FILE):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "system_name": "Garden",
            "ph_range": {"min": 5.5, "max": 6.5},
            "ph_target": 5.8,
            "max_dosing_amount": 5,
            "dosing_interval": 1.0,
            "system_volume": 5.5,
            "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
            "auto_dosing_enabled": False,
            "time_zone": "America/New_York",
            "daylight_savings_enabled": True,
            "usb_roles": {
                "ph_probe": None,
                "relay": None,
            },
            "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
            "relay_ports": {"ph_up": 1, "ph_down": 2},

            # NEW: Default Discord notification settings
            "discord_enabled": False,
            "discord_webhook_url": "",

            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": ""
        }, f, indent=4)


@settings_blueprint.route('/', methods=['GET'])
def get_settings():
    settings = load_settings()
    # Inject our code-based version
    settings["program_version"] = PROGRAM_VERSION
    return jsonify(settings)


def ensure_script_executable(script_path: str):
    """Check if script is executable by the owner; if not, chmod +x."""
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    mode = os.stat(script_path).st_mode
    # Check if "owner execute" bit is set:
    if not (mode & stat.S_IXUSR):
        print(f"[INFO] Making {script_path} executable (chmod +x)")
        subprocess.run(["chmod", "+x", script_path], check=True)


@settings_blueprint.route('/', methods=['POST'])
def update_settings():
    """
    Merge new settings into current_settings.json and emit a status update.
    This can handle many fields including the new Discord fields:
      "discord_enabled", "discord_webhook_url".
    """
    new_settings = request.get_json() or {}
    print(f"[DEBUG] update_settings received new_settings = {new_settings}")

    current_settings = load_settings()

    old_system_name = current_settings.get("system_name", "Garden")

    # Check if auto-dosing changed, so we can reset timers
    auto_dosing_changed = (
        "auto_dosing_enabled" in new_settings or
        "dosing_interval" in new_settings
    )

    # 1) Merge relay_ports if present
    if "relay_ports" in new_settings:
        if "relay_ports" not in current_settings:
            current_settings["relay_ports"] = {}
        current_settings["relay_ports"].update(new_settings["relay_ports"])
        del new_settings["relay_ports"]

    # 2) Merge water_level_sensors if present
    water_sensors_updated = False
    if "water_level_sensors" in new_settings:
        if "water_level_sensors" not in current_settings:
            current_settings["water_level_sensors"] = {}

        for sensor_key, sensor_data in new_settings["water_level_sensors"].items():
            current_settings["water_level_sensors"][sensor_key] = sensor_data

        del new_settings["water_level_sensors"]
        water_sensors_updated = True

    # 3) Merge everything else (system_name, etc.)
    #    This includes our new Discord fields if present: "discord_enabled", "discord_webhook_url"
    current_settings.update(new_settings)
    save_settings(current_settings)

    # If auto-dosing changed, reset the auto-dose timer
    if auto_dosing_changed:
        reset_auto_dose_timer()

    # If system_name changed, rename the OS
    new_system_name = current_settings.get("system_name", "Garden")
    if new_system_name != old_system_name:
        print(f"System name changed from {old_system_name} to {new_system_name}.")

        script_path = os.path.join(os.getcwd(), "scripts", "change_hostname.sh")
        ensure_script_executable(script_path)

        try:
            subprocess.run(["sudo", script_path, new_system_name], check=True)
            print(f"Successfully updated system hostname to {new_system_name}.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Unable to change system hostname: {e}")

        emit_status_update()
        return jsonify({"status": "success", "settings": current_settings})

    emit_status_update()
    return jsonify({"status": "success", "settings": current_settings})


@settings_blueprint.route('/reset', methods=['POST'])
def reset_settings():
    """Reset all settings to defaults, etc."""
    default_settings = {
        "system_name": "Garden",
        "ph_range": {"min": 5.5, "max": 6.5},
        "ph_target": 5.8,
        "max_dosing_amount": 5,
        "dosing_interval": 1.0,
        "system_volume": 5.5,
        "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
        "auto_dosing_enabled": False,
        "time_zone": "America/New_York",
        "daylight_savings_enabled": True,
        "usb_roles": {
            "ph_probe": None,
            "relay": None,
        },
        "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
        "relay_ports": {"ph_up": 1, "ph_down": 2},

        # Also reset Discord to default
        "discord_enabled": False,
        "discord_webhook_url": ""
    }
    save_settings(default_settings)

    emit_status_update()
    return jsonify({"status": "success", "settings": default_settings})


@settings_blueprint.route('/usb_devices', methods=['GET'])
def list_usb_devices():
    """Return all visible serial devices and prune stale assignments."""
    # 1) enumerate every likely filename
    patterns = [
        "/dev/serial/by-path/*",
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    ]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(pattern))

    devices = [{"device": p} for p in sorted(paths)]

    # 2) drop assignments whose device has truly vanished
    settings = load_settings()
    usb_roles = settings.setdefault("usb_roles", {"ph_probe": None, "relay": None})

    connected_paths = [d["device"] for d in devices]
    if any(assigned and assigned not in connected_paths for assigned in usb_roles.values()):
        for role, assigned in usb_roles.items():
            if assigned and assigned not in connected_paths:
                usb_roles[role] = None
        save_settings(settings)

    emit_status_update()
    return jsonify(devices)


@settings_blueprint.route('/assign_usb', methods=['POST'])
def assign_usb_device():
    """Assign or clear a USB device for pH probe, dosing relay."""

    data = request.get_json()
    role = data.get("role")
    device = data.get("device")

    if role not in ["ph_probe", "relay"]:
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    settings = load_settings()
    settings.setdefault("usb_roles", {"ph_probe": None, "relay": None})
    old_device = settings.get("usb_roles", {}).get(role)

    # Clear or set
    if not device:
        settings["usb_roles"][role] = None
    else:
        # Ensure no duplication
        for other_role, assigned_dev in settings["usb_roles"].items():
            if assigned_dev == device and other_role != role:
                return jsonify({
                    "status": "failure",
                    "error": f"Device already assigned to {other_role}"
                }), 400
        settings["usb_roles"][role] = device

    save_settings(settings)

    # Re-init logic if needed
    if role == "ph_probe":
        from services.ph_service import restart_serial_reader
        restart_serial_reader()
    elif role == "relay":
        from services.pump_relay_service import reinitialize_relay_service
        reinitialize_relay_service()


    emit_status_update()
    return jsonify({"status": "success", "usb_roles": settings["usb_roles"]})


@settings_blueprint.route('/system_name', methods=['GET'])
def get_system_name():
    settings = load_settings()
    return jsonify({"system_name": settings.get("system_name", "Garden")})


@settings_blueprint.route('/system_name', methods=['POST'])
def set_system_name():
    data = request.get_json() or {}
    system_name = data.get("system_name")
    settings = load_settings()

    if system_name:
        settings["system_name"] = system_name
        save_settings(settings)
        emit_status_update()

    return jsonify({"system_name": settings.get("system_name", "Garden")})


@settings_blueprint.route('/export', methods=['GET'])
def export_settings():
    """Download the current settings.json file."""
    return send_file(
        SETTINGS_FILE,
        mimetype='application/json',
        as_attachment=True,
        download_name='settings.json'
    )


@settings_blueprint.route('/import', methods=['POST'])
def import_settings():
    """Upload a settings.json to replace existing, then re-init services."""
    if 'file' not in request.files:
        return jsonify({"status": "failure", "error": "No file part in request."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "failure", "error": "No selected file."}), 400

    try:
        data = json.load(file)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        if "system_name" not in data:
            return jsonify({
                "status": "failure",
                "error": "Missing 'system_name' in imported settings."
            }), 400

        # Try re-init logic
        try:
            from services.ph_service import restart_serial_reader
            from services.pump_relay_service import reinitialize_relay_service
            from services.auto_dose_utils import reset_auto_dose_timer

            restart_serial_reader()
            reinitialize_relay_service()
            reset_auto_dose_timer()

            print("[IMPORT] Successfully re-initialized dependent services.")
        except Exception as ex:
            print(f"[IMPORT] Service re-init failed: {ex}")
            # Possibly restart the entire system:
            try:
                subprocess.run(["sudo", "systemctl", "restart", "garden.service"], check=True)
                print("[IMPORT] Triggered service restart due to re-init failure.")
            except Exception as restart_err:
                print(f"[IMPORT] Could not restart garden.service: {restart_err}")

        emit_status_update()
        return jsonify({"status": "success"}), 200

    except json.JSONDecodeError:
        return jsonify({"status": "failure", "error": "Invalid JSON in uploaded file."}), 400
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500


@settings_blueprint.route('/discord_message', methods=['POST'])
def discord_webhook():
    """
    POST JSON like:
    {
      "test_message": "Hello from my garden!"
    }
    We'll retrieve settings.discord_webhook_url and settings.discord_enabled,
    then attempt to POST to Discord.
    """
    data = request.get_json() or {}
    test_message = data.get("test_message", "").strip()
    if not test_message:
        return jsonify({"status": "failure", "error": "No test_message provided"}), 400

    settings = load_settings()
    if not settings.get("discord_enabled", False):
        return jsonify({"status": "failure", "error": "Discord notifications are disabled"}), 400

    webhook_url = settings.get("discord_webhook_url", "").strip()
    if not webhook_url:
        return jsonify({"status": "failure", "error": "No Discord webhook URL is configured"}), 400

    # Attempt to send
    try:
        resp = requests.post(webhook_url, json={"content": test_message}, timeout=10)
        if 200 <= resp.status_code < 300:
            return jsonify({"status": "success", "info": f"Message delivered (HTTP {resp.status_code})."})
        else:
            return jsonify({
                "status": "failure",
                "error": f"Discord webhook returned {resp.status_code} {resp.text}"
            }), 400
    except Exception as ex:
        return jsonify({"status": "failure", "error": f"Exception sending webhook: {ex}"}), 400

@settings_blueprint.route('/telegram_message', methods=['POST'])
def telegram_webhook():
    """
    POST JSON like:
    {
      "test_message": "Hello from my garden!"
    }
    We'll retrieve settings.telegram_bot_token and settings.telegram_enabled,
    then attempt to POST to Telegram's Bot API using raw HTTP.
    """
    data = request.get_json() or {}
    test_message = data.get("test_message", "").strip()
    if not test_message:
        return jsonify({"status": "failure", "error": "No test_message provided"}), 400

    settings = load_settings()
    if not settings.get("telegram_enabled", False):
        return jsonify({"status": "failure", "error": "Telegram notifications are disabled"}), 400

    bot_token = settings.get("telegram_bot_token", "").strip()
    if not bot_token:
        return jsonify({"status": "failure", "error": "No Telegram bot token is configured"}), 400

    # For a real integration, you also need a chat_id or channel username.
    # For testing, either store "telegram_chat_id" in settings or accept in request.
    # Example: let's just assume we store it in the settings:
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not chat_id:
        return jsonify({"status": "failure", "error": "No Telegram chat_id is configured"}), 400

    # Attempt to send a message via raw POST
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": test_message
        }
        resp = requests.post(url, json=payload, timeout=10)
        if 200 <= resp.status_code < 300:
            return jsonify({"status": "success", "info": f"Message delivered (HTTP {resp.status_code})."})
        else:
            return jsonify({
                "status": "failure",
                "error": f"Telegram API returned {resp.status_code} {resp.text}"
            }), 400
    except Exception as ex:
        return jsonify({"status": "failure", "error": f"Exception sending Telegram message: {ex}"}), 400

