# Production-Quality SQLite Job Scheduler

A production-inspired, highly resilient **Job Scheduler** built in Python and powered by SQLite. It implements transactional concurrency controls, worker heartbeats, automated crash recoveries, dead-letter-queues, backoff retries, and a DevOps console dashboard.

---

## Features

1. **Production-Inspired Component Architecture**: Decoupled modules separating database queries (Repository), business rules (Manager/Service), input checks (Validator), and thread supervisors (Scheduler/Worker).
2. **Atomic Job Claiming**: Prevents double-execution in concurrent environments by utilizing SQLite database locks (`BEGIN IMMEDIATE TRANSACTION`).
3. **Resilient Worker Heartbeats**: Active workers update heartbeats dynamically. If a worker dies mid-execution, the scheduler monitor automatically detects the timeout, marks the worker inactive, recovers the orphaned job, and reschedules it or forwards it to the Dead Letter Queue.
4. **Custom Backoff Retries**: Supports Fixed, Linear, and Exponential retry algorithms.
5. **Dead Letter Queue (DLQ)**: Failed tasks exceeding retry thresholds are cleanly isolated to the DLQ for operator inspection.
6. **Active Queue Controller**: Pause and resume queues dynamically; workers halt claiming tasks from paused queues immediately and resume once unpaused.
7. **DevOps Live Console Dashboard**: Real-time view of worker health, DLQ items, recent execution histories, and overall job metrics.
8. **Relative Time Offsets**: Simplifies CLI task creation by allowing input offsets (e.g. `+10s` for 10 seconds, `+5m` for 5 minutes, `+1h` for 1 hour) instead of typing verbose timestamps.

---

## Directory Structure

```
JobScheduler/
│
├── main.py                # Main menu driver and interactive console dashboard
├── config.py              # Paths, heartbeats, and timing configuration settings
├── database.py            # SQLite setup, immediate transactions, and query wrappers
├── scheduler.py           # Background worker pool and heartbeat monitoring loops
├── executor.py            # Subprocess executor and retry/DLQ manager
├── job_manager.py         # Business operations (job editing, canceling, reporting)
├── models.py              # Structured Python dataclasses
├── validator.py           # Constraints validator (names, commands, dates)
├── logger.py              # Application-wide logger configuration
├── utils.py               # Time calculations and table UI formatters
│
├── database/
│   └── jobs.db            # Persistent SQLite database (automatically generated)
│
├── logs/
│   └── scheduler.log      # Application execution logs
│
├── reports/               # Output directory for system reports
│
├── tests/                 # Comprehensive unit test suites
│   ├── test_database.py
│   ├── test_scheduler.py
│   ├── test_executor.py
│   └── test_job_manager.py
│
├── README.md              # Installation and run instructions
├── requirements.txt       # Dependency summary (None needed, uses standard library)
└── architecture.md        # Technical architecture design and flows
```

---

## Installation & Setup

1. **Prerequisites**: Ensure you have Python 3.11 or higher installed on your machine.
2. **Setup**: Clone or copy this directory to your workspace.
3. No external library installations are needed. The system runs entirely on Python's Standard Library.

---

## How to Run

1. Run the main controller:
   ```bash
   python main.py
   ```
2. On startup, the scheduler engine launches `3` worker threads automatically. You will see the main menu options:
   ```
   ==================================
    PRODUCTION JOB SCHEDULER SYSTEM
    Scheduler status: [RUNNING - 3 Workers]
   ==================================
     1. Add Job
     2. Job Explorer (View, Edit, Reschedule, Cancel, Log)
     3. Manage Queues (List, Pause, Resume)
     4. Search Jobs
     5. View Operations Dashboard (DevOps Monitor)
     6. Toggle Background Scheduler Engine
     7. Generate System Report
     8. Exit
   ==================================
   ```

### 1. Adding a Job
- Choose option `1`.
- Enter details:
  - **Job Name**: e.g., `BackupData`
  - **Command**: Enter any shell or terminal command. E.g. `python -c "import time; print('Working...'); time.sleep(2)"` or `echo "Executing Backup"`
  - **Schedule Time**: You can type a absolute date (`2026-07-05 16:30:00`) or a relative shorthand:
    - `+10s` (runs in 10 seconds)
    - `+5m` (runs in 5 minutes)
    - `+1h` (runs in 1 hour)
  - **Retry Policy**: `Fixed`, `Linear`, or `Exponential`.
- The job is stored in `Pending` state. Once the scheduled time passes, an active worker claims and runs it automatically.

### 2. DevOps Dashboard (Operations Dashboard)
- Choose option `5`.
- This shows system statistics, active workers and their last heartbeat timestamp, dead letter queue items, and the most recent job executions with completion times and exit statuses.
- The view automatically polls the database. You can press `q` and `Enter` (or `Ctrl+C`) to return to the main menu.

### 3. Queue Management
- Choose option `3` to view queues.
- Add a new queue or pause an existing one. If you pause the `default` queue, workers immediately stop executing pending jobs scheduled under `default` until you choose option `3` and resume the queue.

### 4. Running the Report Generator
- Choose option `7` to create an overall system report.
- The report containing execution statistics, DLQ status, and average job execution durations is saved in the `reports/` folder.

---

## Running Unit Tests

A comprehensive unit test suite is included to verify all parts of the application:
```bash
python -m unittest discover -s tests
```
*Note: The test suite automatically isolates executions using a test database (`database/test_jobs.db`), ensuring developer data remains untouched.*
