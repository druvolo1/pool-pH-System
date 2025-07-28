import eventlet
# eventlet.monkey_patch()  # Comment or remove; already in app.py
import subprocess
import os, stat

from app import app  # Add this line to expose 'app' for Gunicorn

from utils.settings_utils import load_settings


def ensure_script_executable(script_path: str):
    """Check if script is executable by the owner; if not, chmod +x."""
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    mode = os.stat(script_path).st_mode
    if not (mode & stat.S_IXUSR):
        print(f"[INFO] Making {script_path} executable (chmod +x)")
        subprocess.run(["chmod", "+x", script_path], check=True)

def flush_avahi():
    """
    Stop Avahi, remove stale runtime files, and restart it.
    Ensures the script is executable first.
    """
    #script_path = "/home/dave/garden/scripts/flush_avahi.sh"
    #ensure_script_executable(script_path)

    #try:
    #    subprocess.run(["sudo", script_path], check=True)
    #    print("[Gunicorn] Avahi has been flushed prior to starting threads.")
    #except subprocess.CalledProcessError as e:
    #    print(f"[Gunicorn] Failed to flush Avahi: {e}")


# Gunicorn settings
bind = "0.0.0.0:8000"
workers = 1
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False

if __name__ == "__main__":
    print("[WSGI] Running in local development mode (not under Gunicorn).")
    app.run(host="0.0.0.0", port=8000, debug=True)