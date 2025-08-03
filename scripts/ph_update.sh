#!/bin/bash
# ph.sh
# This script pulls the latest code & dependencies, then restarts ph.service.
# Using "restart" means the app only goes offline briefly at the very end.

# Figure out which directory this script resides in:
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# We'll store logs in the same folder:
LOGFILE="${SCRIPTDIR}/ph_update.log"

# Redirect all script output (stdout & stderr) to both the console and the log file.
exec > >(tee -a "$LOGFILE") 2>&1

cd /home/dave/pool-pH-System
source venv/bin/activate

echo "[$(date)] Pulling latest code..."
git pull

echo "[$(date)] Installing dependencies..."
pip install -r requirements.txt

echo "[$(date)] Restarting ph.service..."
sudo systemctl restart ph.service

echo "[$(date)] Update script finished successfully."
