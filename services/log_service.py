# File: services/log_service.py
import csv
import os
from datetime import datetime

# Define the log directory and file
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
DOSING_LOG_FILE = os.path.join(LOG_DIR, 'dosing_log.csv')

def ensure_log_file_exists(log_file, headers):
    """
    Ensures the specified log file exists and creates it with the given headers if it doesn't.
    This can be used for different log files in the future.
    """
    if not os.path.exists(log_file):
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(log_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

def log_dosing_event(ph, dose_type, dose_amount_ml):
    """
    Logs a dosing event to the dosing CSV file.
    In the future, additional logging functions for other sensors or events can be added here,
    potentially writing to separate CSV files or a unified log with event types.
    """
    headers = ['timestamp', 'ph', 'dose_type', 'dose_amount_ml']
    ensure_log_file_exists(DOSING_LOG_FILE, headers)
    timestamp = datetime.now().isoformat()
    with open(DOSING_LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, ph, dose_type, dose_amount_ml])

# Future expansion example:
# def log_sensor_data(sensor_name, value, additional_info=None):
#     """
#     Logs sensor data to a separate sensor_log.csv or unified log.
#     """
#     headers = ['timestamp', 'sensor_name', 'value']
#     if additional_info:
#         headers.extend(additional_info.keys())
#     sensor_log_file = os.path.join(LOG_DIR, 'sensor_log.csv')
#     ensure_log_file_exists(sensor_log_file, headers)
#     timestamp = datetime.now().isoformat()
#     row = [timestamp, sensor_name, value]
#     if additional_info:
#         row.extend(additional_info.values())
#     with open(sensor_log_file, 'a', newline='') as f:
#         writer = csv.writer(f)
#         writer.writerow(row)