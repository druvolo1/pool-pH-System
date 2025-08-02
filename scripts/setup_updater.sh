#!/bin/bash
# setup_updater.sh

set -e

# Figure out which directory this script resides in:
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOGFILE="${SCRIPTDIR}/setup_updater.log"

# Redirect all script output to both console and log file in the same dir
exec > >(tee -a "$LOGFILE") 2>&1

echo "[$(date)] Starting setup_updater.sh..."

# 1) Copy the systemd unit to the correct location
echo "[$(date)] Copying ph-updater.service to /etc/systemd/system/"
sudo cp /home/dave/pool-pH-System/scripts/ph-updater.service /etc/systemd/system/

# 2) Reload systemd
echo "[$(date)] Reloading systemd daemon..."
sudo systemctl daemon-reload

# 3) Optional: enable so it can be started at any time
echo "[$(date)] Enabling ph-updater.service..."
sudo systemctl enable ph-updater.service

# 4) Make sure the script is executable
echo "[$(date)] Ensuring ph_update.sh is executable..."
sudo chmod +x /home/dave/pool-pH-System/scripts/ph_update.sh

# 5) Make sure the hostname script is executable
echo "[$(date)] Ensuring change_hostname.sh is executable..."
sudo chmod +x /home/dave/pool-pH-System/scripts/change_hostname.sh

# 6) Make sure the hostname avahi is executable
echo "[$(date)] Ensuring change_hostname.sh is executable..."
#sudo chmod +x /home/dave/pool-pH-System/scripts/flush_avahi.sh

echo "[$(date)] setup_updater.sh completed."
