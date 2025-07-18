import eventlet
from eventlet.green import subprocess  # Use Eventlet's green subprocess for compatibility

def post_fork(server, worker):
    # Apply monkey_patch here (per-worker, after fork)
    eventlet.monkey_patch()
    print("[WSGI] Eventlet monkey-patched in worker.")

    # Disable Eventlet's multiple-readers check to avoid conflicts with multiprocessing pipes
    import eventlet.debug
    eventlet.debug.hub_prevent_multiple_readers(False)  # WARNING: Disables global safety check; use only if necessary (low risk for our isolated mp.Pool)

    # Force USB rescan with improved commands for serial devices
    try:
        # Reload udev rules first
        subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=True)
        # Trigger re-add for all devices (no subsystem limit to ensure tty/serial symlinks)
        subprocess.run(["sudo", "udevadm", "trigger", "--action=add"], check=True)
        print("[WSGI] USB/serial rescan triggered successfully.")
        # Give udev time to process (5-10s empirical delay)
        eventlet.sleep(5)
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

# Other Gunicorn settings (moved from wsgi.py)
bind = "0.0.0.0:8000"
workers = 1
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False