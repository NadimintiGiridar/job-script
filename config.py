import os
from pathlib import Path

# Base Directory
BASE_DIR = Path(__file__).resolve().parent

# Database Configuration
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "jobs.db"

# Logs Configuration
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "scheduler.log"

# Reports Configuration
REPORTS_DIR = BASE_DIR / "reports"

# Ensure directories exist
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Scheduler & Worker Settings
SCHEDULER_POLL_INTERVAL = 1.0  # seconds
WORKER_HEARTBEAT_INTERVAL = 2.0  # seconds
WORKER_TIMEOUT = 8.0  # seconds (if no heartbeat in 8s, worker is considered dead)
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_INTERVAL = 5  # seconds
