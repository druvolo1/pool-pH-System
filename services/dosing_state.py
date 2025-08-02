# File: services/dosing_state.py

# Global state for active dosing task (shared between manual and auto-dosing)
active_dosing_task = None
active_relay_port = None
active_dosing_type = None
active_dosing_amount = None