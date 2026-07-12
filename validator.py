import datetime
from typing import Optional

def validate_job_name(name: str) -> str:
    """Validates job name. Cannot be empty."""
    if not name or not name.strip():
        raise ValueError("Job name cannot be empty.")
    return name.strip()

def validate_command(command: str) -> str:
    """Validates the execution command. Cannot be empty."""
    if not command or not command.strip():
        raise ValueError("Command cannot be empty.")
    return command.strip()

def validate_schedule_time(time_str: str, allow_past: bool = False) -> str:
    """
    Validates schedule time. 
    Must be in YYYY-MM-DD HH:MM:SS format.
    Cannot be in the past unless explicitly allowed (e.g. during recovery or migration testing).
    """
    if not time_str or not time_str.strip():
        raise ValueError("Schedule time cannot be empty.")
    
    try:
        dt = datetime.datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError("Invalid date or time format. Please use YYYY-MM-DD HH:MM:SS (e.g. 2026-07-05 15:30:00).")
    
    if not allow_past and dt < datetime.datetime.now():
        raise ValueError("Cannot schedule a job in the past.")
        
    return time_str.strip()

def validate_priority(priority: int) -> int:
    """Validates job priority. Must be 0 (Low), 1 (Medium), or 2 (High)."""
    if priority not in (0, 1, 2):
        raise ValueError("Priority must be 0 (Low), 1 (Medium), or 2 (High).")
    return priority

def validate_retry_policy(policy: str) -> str:
    """Validates retry policy. Must be Fixed, Linear, or Exponential."""
    policy_clean = policy.strip().capitalize()
    if policy_clean not in ("Fixed", "Linear", "Exponential"):
        raise ValueError("Retry policy must be 'Fixed', 'Linear', or 'Exponential'.")
    return policy_clean

def validate_max_retries(max_retries: int) -> int:
    """Validates max retries. Must be non-negative."""
    try:
        val = int(max_retries)
    except (ValueError, TypeError):
        raise ValueError("Max retries must be an integer.")
    if val < 0:
        raise ValueError("Max retries cannot be negative.")
    return val

def validate_retry_interval(interval: int) -> int:
    """Validates retry interval. Must be positive (in seconds)."""
    try:
        val = int(interval)
    except (ValueError, TypeError):
        raise ValueError("Retry interval must be an integer.")
    if val <= 0:
        raise ValueError("Retry interval must be greater than zero.")
    return val

def validate_queue_name(name: str) -> str:
    """Validates queue name. Cannot be empty, must be alphanumeric/dashes."""
    if not name or not name.strip():
        raise ValueError("Queue name cannot be empty.")
    name_clean = name.strip()
    if not all(c.isalnum() or c in ("-", "_") for c in name_clean):
        raise ValueError("Queue name can only contain alphanumeric characters, dashes, and underscores.")
    return name_clean
