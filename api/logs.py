# File: api/logs.py

from flask import Blueprint, jsonify, request
import os
import json
from datetime import datetime

# Create the Blueprint for logs
log_blueprint = Blueprint('logs', __name__)

# Path to the logs file (updated to JSONL for append efficiency and multi-sensor support)
LOGS_FILE = os.path.join(os.getcwd(), "data", "logs", "sensor_log.jsonl")

# Ensure the logs directory exists
os.makedirs(os.path.dirname(LOGS_FILE), exist_ok=True)

# Ensure the logs file exists (empty if not)
if not os.path.exists(LOGS_FILE):
    open(LOGS_FILE, "w").close()


# Helper function: Load logs from JSONL file, filtering for dosing events
def load_logs():
    logs = []
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("event_type") == "dosing":  # Filter to dosing only for this API
                            logs.append(entry)
                    except json.JSONDecodeError:
                        pass  # Skip malformed lines
    return logs


# API Endpoint: Get all dosing logs
@log_blueprint.route('/', methods=['GET'])
def get_logs():
    """
    Retrieve all dosage logs (filtered from the JSONL file).
    """
    logs = load_logs()
    return jsonify(logs)


# API Endpoint: Clear all logs (truncate the file)
@log_blueprint.route('/clear', methods=['POST'])
def clear_logs():
    """
    Clear all logs by truncating the file.
    """
    open(LOGS_FILE, "w").close()
    return jsonify({"status": "success", "message": "Logs cleared."})

# Note: The /add endpoint is deprecated, as logging is now handled automatically via log_service.py.
# If manual addition is still needed in the future, it can be re-added using log_event from log_service.