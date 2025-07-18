import gevent
from gevent import subprocess  # Gevent's green subprocess for compatibility

def post_fork(server, worker):
    # Apply monkey_patch here (per-worker, after fork)
    gevent.monkey.patch_all()
    print("[WSGI] Gevent monkey-patched in worker.")

    # Force USB rescan with improved commands for serial devices
    try:
        subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=True)
        subprocess.run(["sudo", "udevadm", "trigger", "--action=add"], check=True)
        print("[WSGI] USB/serial rescan triggered successfully.")
        # Give udev time to process (10s empirical delay for Pi)
        gevent.sleep(10)
    except Exception as e:
        print(f"[WSGI] Error triggering USB/serial rescan: {e}")

    print("[WSGI] Initializing worker process. Flushing Avahi, starting threads, and registering mDNS...")

    try:
        #flush_avahi()  # Uncomment if needed
        from app import start_threads
        start_threads()
        print("[WSGI] Background threads started successfully.")

        # Load current system_name
        from utils.settings_utils import load_settings
        s = load_settings()
        system_name = s.get("system_name", "Pool")

        # mDNS registration code (uncomment as needed)
        #register_mdns_pc_hostname(system_name, service_port=8000)
        #register_mdns_pure_system_name(system_name, service_port=8000)

        print(f"[WSGI] Completed mDNS registration for '{system_name}'.")
    except Exception as e:
        print(f"[WSGI] Error in top-level startup code: {e}")

# Other Gunicorn settings
bind = "0.0.0.0:8000"
workers = 1
worker_class = "gevent"
timeout = 60
loglevel = "debug"
preload_app = False