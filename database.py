import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
import datetime
from config import DATABASE_PATH
from logger import logger
from models import Queue, Job, JobExecution, Worker, DeadLetterJob, Project

def get_connection():
    """Create a connection to the SQLite database with a timeout and foreign keys enabled."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextmanager
def db_transaction():
    """Context manager for database transactions. Commits on success, rolls back on error."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Database transaction failed. Rolled back.")
        raise e
    finally:
        conn.close()

def initialize_database():
    """Initializes tables and seeds default queue if not present."""
    logger.info("Initializing SQLite Database...")
    with db_transaction() as conn:
        # 0. Projects Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """)

        # 1. Queues Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                queue_name TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('Active', 'Paused')),
                created_at TEXT NOT NULL,
                project_id INTEGER,
                FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE SET NULL
            );
        """)

        # Migration to add project_id to queues if existing table doesn't have it
        try:
            conn.execute("ALTER TABLE queues ADD COLUMN project_id INTEGER REFERENCES projects(project_id) ON DELETE SET NULL;")
        except sqlite3.OperationalError:
            pass
        
        # 2. Jobs Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                command TEXT NOT NULL,
                schedule_time TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Pending', 'Running', 'Completed', 'Failed', 'Cancelled')),
                priority INTEGER NOT NULL DEFAULT 0 CHECK(priority IN (0, 1, 2)), -- 0=Low, 1=Medium, 2=High
                retry_policy TEXT NOT NULL CHECK(retry_policy IN ('Fixed', 'Linear', 'Exponential')),
                max_retries INTEGER NOT NULL DEFAULT 3,
                retry_interval INTEGER NOT NULL DEFAULT 5,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                worker_id TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                FOREIGN KEY (queue_name) REFERENCES queues (queue_name) ON DELETE RESTRICT
            );
        """)
        
        # 3. Job Executions Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                worker_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Running', 'Completed', 'Failed')),
                attempt_number INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration REAL,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
            );
        """)
        
        # 4. Workers Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('Active', 'Inactive')),
                last_heartbeat TEXT NOT NULL,
                started_at TEXT NOT NULL
            );
        """)
        
        # 5. Dead Letter Queue Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                dlq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                job_name TEXT NOT NULL,
                queue_name TEXT NOT NULL,
                command TEXT NOT NULL,
                failed_at TEXT NOT NULL,
                reason TEXT NOT NULL
            );
        """)

        # 6. Audit Logs Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                details TEXT NOT NULL
            );
        """)

        # Indexes for query optimization
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_schedule ON jobs(status, schedule_time);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_queue ON jobs(queue_name);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_executions_job_id ON job_executions(job_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);")

        # Seed default project if not exists
        cursor = conn.execute("SELECT 1 FROM projects WHERE project_name = 'Default Project';")
        if not cursor.fetchone():
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO projects (project_name, created_at) VALUES ('Default Project', ?)", (now,))
            logger.info("Default project seeded.")

        # Seed default queue if not exists
        cursor = conn.execute("SELECT 1 FROM queues WHERE queue_name = 'default';")
        if not cursor.fetchone():
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO queues (queue_name, status, created_at, project_id) VALUES ('default', 'Active', ?, 1)", (now,))
            logger.info("Default queue 'default' seeded.")
            
    logger.info("Database initialized successfully.")

# Parse Database Rows to Dataclasses
def row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        job_id=row['job_id'],
        job_name=row['job_name'],
        queue_name=row['queue_name'],
        command=row['command'],
        schedule_time=row['schedule_time'],
        status=row['status'],
        priority=row['priority'],
        retry_policy=row['retry_policy'],
        max_retries=row['max_retries'],
        retry_interval=row['retry_interval'],
        retry_count=row['retry_count'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        worker_id=row['worker_id'],
        started_at=row['started_at'],
        completed_at=row['completed_at'],
        error_message=row['error_message']
    )

def row_to_queue(row: sqlite3.Row) -> Queue:
    return Queue(
        queue_name=row['queue_name'],
        status=row['status'],
        created_at=row['created_at'],
        project_id=row['project_id'] if 'project_id' in row.keys() else None
    )

def row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        project_id=row['project_id'],
        project_name=row['project_name'],
        created_at=row['created_at']
    )

def row_to_execution(row: sqlite3.Row) -> JobExecution:
    return JobExecution(
        execution_id=row['execution_id'],
        job_id=row['job_id'],
        worker_id=row['worker_id'],
        status=row['status'],
        attempt_number=row['attempt_number'],
        started_at=row['started_at'],
        completed_at=row['completed_at'],
        duration=row['duration'],
        stdout=row['stdout'],
        stderr=row['stderr'],
        error_message=row['error_message']
    )

def row_to_worker(row: sqlite3.Row) -> Worker:
    return Worker(
        worker_id=row['worker_id'],
        status=row['status'],
        last_heartbeat=row['last_heartbeat'],
        started_at=row['started_at']
    )

def row_to_dlq(row: sqlite3.Row) -> DeadLetterJob:
    return DeadLetterJob(
        dlq_id=row['dlq_id'],
        job_id=row['job_id'],
        job_name=row['job_name'],
        queue_name=row['queue_name'],
        command=row['command'],
        failed_at=row['failed_at'],
        reason=row['reason']
    )

# --- Queue Helpers ---
def insert_queue(queue: Queue):
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO queues (queue_name, status, created_at, project_id) VALUES (?, ?, ?, ?)",
            (queue.queue_name, queue.status, queue.created_at, queue.project_id)
        )

# --- Project Helpers ---
def insert_project(project: Project) -> int:
    with db_transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO projects (project_name, created_at) VALUES (?, ?)",
            (project.project_name, project.created_at)
        )
        return cursor.lastrowid

def get_project(project_id: int) -> Optional[Project]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        row = cursor.fetchone()
        return row_to_project(row) if row else None
    finally:
        conn.close()

def list_projects() -> List[Project]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM projects ORDER BY project_name ASC")
        return [row_to_project(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_queue(queue_name: str) -> Optional[Queue]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM queues WHERE queue_name = ?", (queue_name,))
        row = cursor.fetchone()
        return row_to_queue(row) if row else None
    finally:
        conn.close()

def update_queue_status(queue_name: str, status: str):
    with db_transaction() as conn:
        conn.execute(
            "UPDATE queues SET status = ? WHERE queue_name = ?",
            (status, queue_name)
        )

def list_queues() -> List[Queue]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM queues ORDER BY queue_name ASC")
        return [row_to_queue(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# --- Job Helpers ---
def insert_job(job: Job) -> int:
    with db_transaction() as conn:
        cursor = conn.execute("""
            INSERT INTO jobs (
                job_name, queue_name, command, schedule_time, status, priority,
                retry_policy, max_retries, retry_interval, retry_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.job_name, job.queue_name, job.command, job.schedule_time, job.status, job.priority,
            job.retry_policy, job.max_retries, job.retry_interval, job.retry_count, job.created_at, job.updated_at
        ))
        return cursor.lastrowid

def get_job(job_id: int) -> Optional[Job]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return row_to_job(row) if row else None
    finally:
        conn.close()

def update_job(job: Job):
    with db_transaction() as conn:
        conn.execute("""
            UPDATE jobs SET
                job_name = ?, queue_name = ?, command = ?, schedule_time = ?, status = ?,
                priority = ?, retry_policy = ?, max_retries = ?, retry_interval = ?, retry_count = ?,
                updated_at = ?, worker_id = ?, started_at = ?, completed_at = ?, error_message = ?
            WHERE job_id = ?
        """, (
            job.job_name, job.queue_name, job.command, job.schedule_time, job.status,
            job.priority, job.retry_policy, job.max_retries, job.retry_interval, job.retry_count,
            job.updated_at, job.worker_id, job.started_at, job.completed_at, job.error_message, job.job_id
        ))

def delete_job(job_id: int):
    with db_transaction() as conn:
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))

def search_jobs(query: str) -> List[Job]:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT * FROM jobs 
            WHERE job_name LIKE ? OR command LIKE ? OR status LIKE ? OR queue_name LIKE ?
            ORDER BY schedule_time DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
        return [row_to_job(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def list_jobs(status: Optional[str] = None) -> List[Job]:
    conn = get_connection()
    try:
        if status:
            cursor = conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY schedule_time DESC", (status,))
        else:
            cursor = conn.execute("SELECT * FROM jobs ORDER BY schedule_time DESC")
        return [row_to_job(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# --- Concurrency & Claiming ---
def claim_next_job(worker_id: str, now_str: str) -> Optional[Job]:
    """
    Atomically claim the next eligible job.
    Uses 'BEGIN IMMEDIATE TRANSACTION' to lock write capability, and checks:
    - job status is 'Pending'
    - schedule_time <= now_str
    - the parent queue status is 'Active'
    Selects the highest priority job first (priority DESC), then oldest schedule (schedule_time ASC).
    """
    with db_transaction() as conn:
        # Find next eligible job
        cursor = conn.execute("""
            SELECT j.* FROM jobs j
            JOIN queues q ON j.queue_name = q.queue_name
            WHERE j.status = 'Pending'
              AND j.schedule_time <= ?
              AND q.status = 'Active'
            ORDER BY j.priority DESC, j.schedule_time ASC
            LIMIT 1
        """, (now_str,))
        
        row = cursor.fetchone()
        if not row:
            return None
            
        job_id = row['job_id']
        
        # Claim it atomically
        conn.execute("""
            UPDATE jobs 
            SET status = 'Running', worker_id = ?, started_at = ?, updated_at = ?
            WHERE job_id = ?
        """, (worker_id, now_str, now_str, job_id))
        
        # Re-fetch the updated row to return it
        cursor_updated = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        return row_to_job(cursor_updated.fetchone())

# --- Executions ---
def insert_execution(exec_data: JobExecution) -> int:
    with db_transaction() as conn:
        cursor = conn.execute("""
            INSERT INTO job_executions (
                job_id, worker_id, status, attempt_number, started_at, completed_at, duration, stdout, stderr, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exec_data.job_id, exec_data.worker_id, exec_data.status, exec_data.attempt_number,
            exec_data.started_at, exec_data.completed_at, exec_data.duration,
            exec_data.stdout, exec_data.stderr, exec_data.error_message
        ))
        return cursor.lastrowid

def update_execution(exec_data: JobExecution):
    with db_transaction() as conn:
        conn.execute("""
            UPDATE job_executions SET
                status = ?, completed_at = ?, duration = ?, stdout = ?, stderr = ?, error_message = ?
            WHERE execution_id = ?
        """, (
            exec_data.status, exec_data.completed_at, exec_data.duration,
            exec_data.stdout, exec_data.stderr, exec_data.error_message, exec_data.execution_id
        ))

def get_job_executions(job_id: int) -> List[JobExecution]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM job_executions WHERE job_id = ? ORDER BY attempt_number ASC", (job_id,))
        return [row_to_execution(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# --- Worker Heartbeat & Management ---
def insert_worker(worker: Worker):
    with db_transaction() as conn:
        conn.execute("""
            INSERT INTO workers (worker_id, status, last_heartbeat, started_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                status = excluded.status,
                last_heartbeat = excluded.last_heartbeat
        """, (worker.worker_id, worker.status, worker.last_heartbeat, worker.started_at))

def update_worker_heartbeat(worker_id: str, now_str: str):
    with db_transaction() as conn:
        conn.execute(
            "UPDATE workers SET last_heartbeat = ?, status = 'Active' WHERE worker_id = ?",
            (now_str, worker_id)
        )

def list_workers() -> List[Worker]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM workers ORDER BY started_at DESC")
        return [row_to_worker(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_worker(worker_id: str) -> Optional[Worker]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        return row_to_worker(row) if row else None
    finally:
        conn.close()

# --- Dead Letter Queue (DLQ) ---
def insert_dlq(dlq: DeadLetterJob) -> int:
    with db_transaction() as conn:
        cursor = conn.execute("""
            INSERT INTO dead_letter_queue (job_id, job_name, queue_name, command, failed_at, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (dlq.job_id, dlq.job_name, dlq.queue_name, dlq.command, dlq.failed_at, dlq.reason))
        return cursor.lastrowid

def list_dlq() -> List[DeadLetterJob]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM dead_letter_queue ORDER BY failed_at DESC")
        return [row_to_dlq(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# --- Metrics Engine ---
def get_metrics() -> Dict[str, Any]:
    """Calculates operational metrics across the system."""
    conn = get_connection()
    try:
        # Job counts
        cursor = conn.execute("SELECT status, count(*) as cnt FROM jobs GROUP BY status")
        counts = {row['status']: row['cnt'] for row in cursor.fetchall()}
        
        # Ensure all statuses represented
        for stat in ('Pending', 'Running', 'Completed', 'Failed', 'Cancelled'):
            counts.setdefault(stat, 0)
            
        counts['Total'] = sum(counts.values())
        
        # DLQ count
        cursor = conn.execute("SELECT count(*) as cnt FROM dead_letter_queue")
        counts['DLQ'] = cursor.fetchone()['cnt']
        
        # Active workers count
        cursor = conn.execute("SELECT count(*) as cnt FROM workers WHERE status = 'Active'")
        counts['ActiveWorkers'] = cursor.fetchone()['cnt']
        
        # Average duration of completed executions
        cursor = conn.execute("SELECT avg(duration) as avg_dur FROM job_executions WHERE status = 'Completed'")
        avg_dur = cursor.fetchone()['avg_dur']
        counts['AvgDurationSeconds'] = round(avg_dur, 2) if avg_dur is not None else 0.0
        
        return counts
    finally:
        conn.close()

# --- Audit Logs Helper functions ---
def insert_audit_log(username: str, role: str, action: str, target: str, details: str):
    """Inserts a new event into the audit log system."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_transaction() as conn:
        conn.execute("""
            INSERT INTO audit_logs (timestamp, username, role, action, target, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now_str, username, role, action, target, details))

def list_audit_logs() -> List[Dict[str, Any]]:
    """Returns all audit logs sorted by timestamp descending."""
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

