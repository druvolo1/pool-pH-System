def post_fork(server, worker):
    import eventlet
    from eventlet.green import subprocess  # Use Eventlet's green subprocess for compatibility
    import eventlet.tpool  # For running blocking subprocess in a native thread
    import eventlet.debug  # For disabling blocking detection
    print("[GUNICORN_CONFIG] Imported eventlet inside post_fork:", eventlet.__version__)

    # Apply monkey_patch here (per-worker, after fork)
    eventlet.monkey_patch()
    print("[WSGI] Eventlet monkey-patched in worker.")

    # Disable Eventlet's multiple-readers check to avoid conflicts with multiprocessing pipes
    eventlet.debug.hub_prevent_multiple_readers(False)  # WARNING: Disables global safety check; low risk for our isolated mp.Pool
    print("[WSGI] Disabled multiple-readers check.")

    # Force USB rescan with improved commands for serial devices
    try:
        # Temporarily disable hub blocking detection to avoid false positives during rescan
        eventlet.debug.hub_blocking_detection(False)

        # Define a function for the blocking subprocess calls
        def run_udevadm_commands():
            original_subprocess = eventlet.patcher.original('subprocess')
            original_subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=True)
            original_subprocess.run(["sudo", "udevadm", "trigger", "--action=add"], check=True)
            return True

        # Run the blocking commands in a native thread via tpool
        eventlet.tpool.execute(run_udevadm_commands)
        print("[WSGI] USB/serial rescan triggered successfully.")
        # Give udev time to process (5-10s empirical delay)
        eventlet.sleep(5)
    except Exception as e:
        print(f"[WSGI] Error triggering USB/serial rescan: {e}")
    finally:
        # Re-enable hub blocking detection
        eventlet.debug.hub_blocking_detection(True)

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
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False