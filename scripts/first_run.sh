#!/usr/bin/env python3
import os
import subprocess
import sys

SERVICE_PATH = "/etc/systemd/system/ph.service"

SERVICE_CONTENT = """[Unit]
Description=Pool pH System Web App
After=network.target

[Service]
User=dave
WorkingDirectory=/home/dave/pool-pH-System
Environment="PATH=/home/dave/pool-pH-System/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/dave/pool-pH-System/venv/bin/gunicorn -w 1 --worker-class eventlet -b 0.0.0.0:8000 wsgi:app --log-level=debug
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

def run_command(cmd_list, description=None):
    """
    Helper to run shell commands with a descriptive message.
    Raises an exception if the command fails.
    """
    if description:
        print(f"\n=== {description} ===")
    print("Running:", " ".join(cmd_list))
    try:
        subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)

def main():
    # 1) Must run as root
    if os.geteuid() != 0:
        print("Please run this script with sudo or as root.")
        sys.exit(1)

    # 2) Update & upgrade
    run_command(["apt-get", "update"], "apt-get update")
    run_command(["apt-get", "upgrade", "-y"], "apt-get upgrade")

    # 3) Install needed packages
    run_command(["apt-get", "install", "-y", "git", "python3", "python3-venv", "python3-pip"],
                "Install Git, Python 3, venv, pip")

    # Note: We are NOT cloning the repo here,
    # because you indicated you already did a git pull.

    # 4) Create & activate a virtual environment
    if not os.path.isdir("/home/dave/pool-pH-System/venv"):
        print("\n=== Creating virtual environment ===")
        run_command(["python3", "-m", "venv", "/home/dave/pool-pH-System/venv"],
                    "Create Python venv in /home/dave/pool-pH-System/venv")
    else:
        print("\n=== venv already exists. Skipping creation. ===")

    # 5) Upgrade pip & install requirements
    run_command(["/home/dave/pool-pH-System/venv/bin/pip", "install", "--upgrade", "pip"],
                "Upgrade pip in the venv")

    requirements_file = "/home/dave/pool-pH-System/requirements.txt"
    if os.path.isfile(requirements_file):
        run_command(["/home/dave/pool-pH-System/venv/bin/pip", "install", "-r", requirements_file],
                    "Install Python dependencies from requirements.txt")
    else:
        print(f"\n=== {requirements_file} not found! Installing core dependencies ===")
        run_command(["/home/dave/pool-pH-System/venv/bin/pip", "install", "gunicorn", "flask", "flask-socketio", "eventlet"],
                    "Install core Python dependencies")

    # 6) Create the systemd service file
    print(f"\n=== Creating systemd service at {SERVICE_PATH} ===")
    with open(SERVICE_PATH, "w") as f:
        f.write(SERVICE_CONTENT)

    # 7) Set permissions for service file
    run_command(["chmod", "644", SERVICE_PATH], "Set permissions for ph.service")

    # 8) Reload systemd so it sees the new service
    run_command(["systemctl", "daemon-reload"], "Reload systemd")

    # 9) Enable and start the ph service
    run_command(["systemctl", "enable", "ph.service"], "Enable ph.service on startup")
    run_command(["systemctl", "start", "ph.service"], "Start ph.service now")

    print("\n=== Setup complete! ===")
    print("You can check logs with: journalctl -u ph.service -f")
    print("You can check status with: systemctl status ph.service")

if __name__ == "__main__":
    main()