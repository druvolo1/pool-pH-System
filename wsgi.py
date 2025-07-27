import eventlet
eventlet.monkey_patch()
import subprocess
import os, stat

from app import app
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
    #S    print(f"[Gunicorn] Failed to flush Avahi: {e}")


# Gunicorn hook: Runs after worker fork
def post_fork(server, worker):
    print("[WSGI] Initializing worker process. Flushing Avahi, starting threads, and registering mDNS...")

    try:
        #flush_avahi()
        # Assuming start_threads is defined in app.py; import if needed
        from app import start_threads
        start_threads()
        print("[WSGI] Background threads started successfully.")

        # Load current system_name
        s = load_settings()
        system_name = s.get("system_name", "Garden")

        # 1) Register the system_name-pc mDNS (hostname-based)
        #register_mdns_pc_hostname(system_name, service_port=8000)

        # 2) Also register the pure system name
        #register_mdns_pure_system_name(system_name, service_port=8000)

        print(f"[WSGI] Completed mDNS registration for '{system_name}'.")
    except Exception as e:
        print(f"[WSGI] Error in top-level startup code: {e}")


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