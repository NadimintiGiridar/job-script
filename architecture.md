# Architecture Design Document: Production-Quality Job Scheduler

This document details the architectural decisions, database models, concurrency patterns, and workflow pipelines implemented in the distributed-ready Job Scheduler.

---

## 1. System Architecture

Our scheduler leverages a multi-threaded, polling-based model with transactional databases. The components are decoupled following clean architecture boundaries:

```mermaid
graph TD
    User([User / CLI]) -->|CLI Menu & Input| Main[main.py Controller]
    Main -->|CRUD Commands| JM[job_manager.py Service]
    Main -->|Control Hooks| SE[scheduler.py Engine]
    
    JM -->|Validates Inputs| Val[validator.py]
    JM -->|SQL Statements| DB[database.py DB Layer]
    SE -->|Heartbeat / Recovery / Claims| DB
    
    subgraph Worker Pool
        SE -->|Spawns Threads| W0[Worker Thread 0]
        SE -->|Spawns Threads| W1[Worker Thread 1]
        SE -->|Spawns Threads| W2[Worker Thread 2]
    end
    
    W0 -->|Atomically Claims & Locks| DB
    W0 -->|Spawns Process| Exec[executor.py]
    Exec -->|Executes Shell / Script| Subprocess[Subprocess Command]
    Exec -->|Logs Executions / Retries / DLQ| DB
    
    DB -->|Persists Data| SQLite[(jobs.db SQLite)]
```

### Module Responsibilities
- **`main.py`**: The CLI UI driver, coordinates startups, serves the DevOps Operations Dashboard, handles menu navigation, and safely hooks shutdown triggers.
- **`config.py`**: Declares central timing thresholds (`WORKER_TIMEOUT`, `WORKER_HEARTBEAT_INTERVAL`), database configurations, and filesystem structure.
- **`database.py`**: Contains SQL statements, table initializations, indices, parse functions, and uses immediate transaction commands to assure atomic state updates.
- **`validator.py`**: Validates input formatting constraints (past schedule checks, naming constraints, priority values, and pattern checking).
- **`utils.py`**: Shared system utilities including CLI table layout engines and retry backoff delays.
- **`job_manager.py`**: Handles jobs administration, queue status toggling, and formats operational statistics report files.
- **`scheduler.py`**: Runs the heartbeat monitor supervisor loop and controls worker thread pools.
- **`executor.py`**: Launches commands inside OS shells, reads execution streams, tracks durations, and manages failures (routing to retries or DLQ).

---

## 2. Database Schema

The database consists of 5 normalized tables with indexes on status and schedule columns:

```mermaid
erDiagram
    QUEUES {
        TEXT queue_name PK
        TEXT status "Active, Paused"
        TEXT created_at
    }
    JOBS {
        INTEGER job_id PK
        TEXT job_name
        TEXT queue_name FK
        TEXT command
        TEXT schedule_time
        TEXT status "Pending, Running, Completed, Failed, Cancelled"
        INTEGER priority "0=Low, 1=Medium, 2=High"
        TEXT retry_policy "Fixed, Linear, Exponential"
        INTEGER max_retries
        INTEGER retry_interval
        INTEGER retry_count
        TEXT created_at
        TEXT updated_at
        TEXT worker_id
        TEXT started_at
        TEXT completed_at
        TEXT error_message
    }
    JOB_EXECUTIONS {
        INTEGER execution_id PK
        INTEGER job_id FK
        TEXT worker_id
        TEXT status "Running, Completed, Failed"
        INTEGER attempt_number
        TEXT started_at
        TEXT completed_at
        REAL duration
        TEXT stdout
        TEXT stderr
        TEXT error_message
    }
    WORKERS {
        TEXT worker_id PK
        TEXT status "Active, Inactive"
        TEXT last_heartbeat
        TEXT started_at
    }
    DEAD_LETTER_QUEUE {
        INTEGER dlq_id PK
        INTEGER job_id
        TEXT job_name
        TEXT queue_name
        TEXT command
        TEXT failed_at
        TEXT reason
    }
    
    QUEUES ||--o{ JOBS : "contains"
    JOBS ||--o{ JOB_EXECUTIONS : "tracks history"
```

---

## 3. Concurrency Control & Atomic Claiming

To prevent race conditions where multiple workers try to execute the same job simultaneously, we use SQLite's database-level write locking via `BEGIN IMMEDIATE TRANSACTION`.

### Claiming Execution Flow:
1. A worker enters `claim_next_job`.
2. It executes `BEGIN IMMEDIATE TRANSACTION`. This locks writing capabilities across other database connections.
3. It fetches the next eligible job candidate using the query:
   ```sql
   SELECT j.* FROM jobs j
   JOIN queues q ON j.queue_name = q.queue_name
   WHERE j.status = 'Pending'
     AND j.schedule_time <= :current_time
     AND q.status = 'Active'
   ORDER BY j.priority DESC, j.schedule_time ASC
   LIMIT 1
   ```
4. If a job is returned, it immediately updates the status:
   ```sql
   UPDATE jobs 
   SET status = 'Running', worker_id = :worker_id, started_at = :current_time
   WHERE job_id = :job_id
   ```
5. The transaction is committed, releasing the lock.
6. The worker receives the claimed job details and begins execution.

This process ensures that a job can be claimed by **exactly one** worker, even if multiple worker threads poll the database at the exact same millisecond.

---

## 4. Heartbeat Monitor & Fault Recovery

If a worker thread crashes or the scheduler process experiences hardware failure, running jobs must not remain stuck in the `Running` state indefinitely.

```mermaid
sequenceDiagram
    participant Monitor as Scheduler Monitor
    participant DB as SQLite Database
    participant Worker as Worker Thread
    
    Note over Worker, DB: Periodic Heartbeat
    Worker->>DB: UPDATE workers SET last_heartbeat = NOW where worker_id = Worker-0
    
    Note over Monitor, DB: Heartbeat Check (Every 1s)
    Monitor->>DB: SELECT * FROM workers WHERE status = 'Active'
    DB-->>Monitor: Returns Worker-0 (last_heartbeat = 20s ago)
    
    Note over Monitor: Detection: last_heartbeat > 8s
    Monitor->>DB: UPDATE workers SET status = 'Inactive' WHERE worker_id = Worker-0
    
    Note over Monitor: Job Recovery Flow
    Monitor->>DB: SELECT * FROM jobs WHERE status = 'Running' AND worker_id = Worker-0
    DB-->>Monitor: Returns Stuck Job (ID: 10)
    
    Monitor->>DB: INSERT INTO job_executions (stating worker crashed)
    
    alt retry_count < max_retries
        Note over Monitor: Reschedule
        Monitor->>DB: UPDATE jobs SET status = 'Pending', schedule_time = next_backoff, retry_count = retry_count + 1 WHERE job_id = 10
    else retry_count >= max_retries
        Note over Monitor: Route to DLQ
        Monitor->>DB: UPDATE jobs SET status = 'Failed' WHERE job_id = 10
        Monitor->>DB: INSERT INTO dead_letter_queue
    end
```

---

## 5. Retry Policies

We support three backoff calculations:

1. **Fixed Delay**: 
   $$\text{Delay} = \text{Interval}$$
   *Constant waiting periods.*
2. **Linear Delay**: 
   $$\text{Delay} = \text{Interval} \times \text{Attempt}$$
   *Waiting time increases linearly with each retry.*
3. **Exponential Delay**: 
   $$\text{Delay} = \text{Interval} \times 2^{\text{Attempt} - 1}$$
   *Waiting time doubles with each retry, preventing thrashing on resource conflicts.*
