import threading
import time
import datetime
from typing import List
from logger import logger
from models import Worker, JobExecution, DeadLetterJob
import database
import utils
from config import (
    SCHEDULER_POLL_INTERVAL, 
    WORKER_HEARTBEAT_INTERVAL, 
    WORKER_TIMEOUT
)
from executor import JobExecutor

class SchedulerEngine:
    """
    Manages the background Scheduler Monitor thread and Worker Pool threads.
    Implements worker heartbeats, atomic job claiming, failure recovery, and graceful shutdown.
    """
    def __init__(self, num_workers: int = 3):
        self.num_workers = num_workers
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.worker_threads: List[threading.Thread] = []
        self._shutdown_event = threading.Event()

    def start(self):
        """Starts the scheduler monitor and worker threads."""
        if self.running:
            logger.warning("SchedulerEngine is already running.")
            return

        self.running = True
        self._shutdown_event.clear()
        
        logger.info(f"Starting SchedulerEngine with {self.num_workers} worker(s)...")

        # 1. Start the main Scheduler Monitor thread
        self.monitor_thread = threading.Thread(
            target=self._run_monitor, 
            name="SchedulerMonitor", 
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("SchedulerMonitor thread started.")

        # 2. Start Worker threads
        self.worker_threads = []
        for i in range(self.num_workers):
            worker_id = f"worker-{i}"
            thread = threading.Thread(
                target=self._run_worker, 
                args=(worker_id,), 
                name=f"WorkerThread-{worker_id}",
                daemon=True
            )
            self.worker_threads.append(thread)
            thread.start()
            logger.info(f"Worker thread '{worker_id}' started.")

        logger.info("SchedulerEngine started successfully.")

    def stop(self):
        """Gracefully shuts down all threads."""
        if not self.running:
            return

        logger.info("Stopping SchedulerEngine...")
        self.running = False
        self._shutdown_event.set()

        # Join monitor thread
        if self.monitor_thread:
            self.monitor_thread.join(timeout=3.0)
            
        # Join worker threads
        for thread in self.worker_threads:
            thread.join(timeout=3.0)

        # Mark all active workers as Inactive in the database upon shutdown
        try:
            active_workers = [w for w in database.list_workers() if w.status == 'Active']
            for w in active_workers:
                w.status = 'Inactive'
                database.insert_worker(w)
            logger.info("All workers set to Inactive on shutdown.")
        except Exception:
            logger.exception("Failed to clean up workers status on shutdown.")

        logger.info("SchedulerEngine stopped.")

    def _run_worker(self, worker_id: str):
        """Worker thread loop: Sends heartbeat, claims job, and executes it."""
        # Register worker in DB
        now_str = utils.get_current_time_str()
        worker = Worker(
            worker_id=worker_id,
            status="Active",
            last_heartbeat=now_str,
            started_at=now_str
        )
        try:
            database.insert_worker(worker)
        except Exception:
            logger.exception(f"Worker {worker_id}: Failed to register in DB.")
            return

        last_heartbeat_time = 0.0

        while self.running:
            now = time.time()
            now_str = utils.get_current_time_str()

            # 1. Update Heartbeat
            if now - last_heartbeat_time >= WORKER_HEARTBEAT_INTERVAL:
                try:
                    database.update_worker_heartbeat(worker_id, now_str)
                    last_heartbeat_time = now
                except Exception:
                    logger.exception(f"Worker {worker_id}: Heartbeat update failed.")

            # 2. Claim next available job
            try:
                job = database.claim_next_job(worker_id, now_str)
                if job:
                    # Execute job
                    logger.info(f"Worker {worker_id}: Claimed job {job.job_id} successfully.")
                    JobExecutor.execute(job.job_id, worker_id)
                    # Loop immediately to check for more jobs without sleeping
                    continue
            except Exception:
                logger.exception(f"Worker {worker_id}: Exception during claim or execution.")

            # Sleep briefly before next poll/heartbeat check
            self._shutdown_event.wait(SCHEDULER_POLL_INTERVAL)

    def _run_monitor(self):
        """Scheduler Monitor loop: Inspects worker heartbeats and recovers orphaned jobs."""
        while self.running:
            try:
                self._check_worker_heartbeats()
            except Exception:
                logger.exception("SchedulerMonitor: Error during heartbeat checks.")

            # Sleep before checking again
            self._shutdown_event.wait(SCHEDULER_POLL_INTERVAL)

    def _check_worker_heartbeats(self):
        """Detects inactive workers and recovers jobs currently assigned to them."""
        now_str = utils.get_current_time_str()
        now_dt = datetime.datetime.now()
        
        workers = database.list_workers()
        for w in workers:
            if w.status != 'Active':
                continue
                
            try:
                hb_dt = datetime.datetime.strptime(w.last_heartbeat, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                hb_dt = now_dt - datetime.timedelta(seconds=WORKER_TIMEOUT + 1)
                
            if (now_dt - hb_dt).total_seconds() > WORKER_TIMEOUT:
                logger.warning(
                    f"SchedulerMonitor: Worker '{w.worker_id}' has timed out. "
                    f"Last heartbeat: {w.last_heartbeat}. Threshold: {WORKER_TIMEOUT}s."
                )
                
                # Mark worker as inactive
                w.status = 'Inactive'
                database.insert_worker(w)
                
                # Reclaim jobs running on this worker
                self._reclaim_jobs_for_worker(w.worker_id, now_str)

    def _reclaim_jobs_for_worker(self, worker_id: str, now_str: str):
        """Recovers any jobs stuck in 'Running' status for a dead worker."""
        # Find jobs in Running status assigned to this worker
        all_jobs = database.list_jobs(status="Running")
        stuck_jobs = [j for j in all_jobs if j.worker_id == worker_id]
        
        for job in stuck_jobs:
            logger.warning(f"SchedulerMonitor: Reclaiming job {job.job_id} ('{job.job_name}') from dead worker '{worker_id}'.")
            
            # Log execution failure for the recovery attempt
            attempt_number = job.retry_count + 1
            error_msg = f"Worker '{worker_id}' died unexpectedly (heartbeat expired)."
            
            exec_data = JobExecution(
                execution_id=None,
                job_id=job.job_id,
                worker_id=worker_id,
                status="Failed",
                attempt_number=attempt_number,
                started_at=job.started_at or now_str,
                completed_at=now_str,
                duration=0.0,
                stdout="",
                stderr=error_msg,
                error_message=error_msg
            )
            database.insert_execution(exec_data)

            # Process retries
            job.updated_at = now_str
            job.error_message = error_msg
            
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                next_time = utils.calculate_next_retry_time(
                    now_str,
                    job.retry_policy,
                    job.retry_interval,
                    job.retry_count
                )
                job.status = "Pending"
                job.schedule_time = next_time
                database.update_job(job)
                logger.info(
                    f"SchedulerMonitor: Rescheduled reclaimed job {job.job_id}. "
                    f"Attempt {job.retry_count}/{job.max_retries}. Next run: {next_time}"
                )
            else:
                job.status = "Failed"
                job.completed_at = now_str
                database.update_job(job)
                
                # Move to DLQ
                dlq = DeadLetterJob(
                    dlq_id=None,
                    job_id=job.job_id,
                    job_name=job.job_name,
                    queue_name=job.queue_name,
                    command=job.command,
                    failed_at=now_str,
                    reason=error_msg
                )
                database.insert_dlq(dlq)
                logger.error(f"SchedulerMonitor: Job {job.job_id} marked as Failed. Max retries exceeded after worker death. Sent to DLQ.")
