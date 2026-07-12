from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Project:
    project_id: Optional[int]
    project_name: str
    created_at: str

@dataclass
class Queue:
    queue_name: str
    status: str  # 'Active' or 'Paused'
    created_at: str
    project_id: Optional[int] = None

@dataclass
class Job:
    job_id: Optional[int]
    job_name: str
    queue_name: str
    command: str
    schedule_time: str  # YYYY-MM-DD HH:MM:SS
    status: str  # 'Pending', 'Running', 'Completed', 'Failed', 'Cancelled'
    priority: int  # 0 = Low, 1 = Medium, 2 = High
    retry_policy: str  # 'Fixed', 'Linear', 'Exponential'
    max_retries: int
    retry_interval: int
    created_at: str
    updated_at: str
    worker_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0

@dataclass
class JobExecution:
    execution_id: Optional[int]
    job_id: int
    worker_id: str
    status: str  # 'Running', 'Completed', 'Failed'
    attempt_number: int
    started_at: str
    completed_at: Optional[str] = None
    duration: Optional[float] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class Worker:
    worker_id: str
    status: str  # 'Active', 'Inactive'
    last_heartbeat: str
    started_at: str

@dataclass
class DeadLetterJob:
    dlq_id: Optional[int]
    job_id: int
    job_name: str
    queue_name: str
    command: str
    failed_at: str
    reason: str
