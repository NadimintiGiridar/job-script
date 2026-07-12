import subprocess
import time
import sys
import os
import datetime
from typing import Tuple, Optional
from logger import logger
from models import Job, JobExecution, DeadLetterJob
import database
import utils

class JobExecutor:
    """Executes a job's shell command, measures duration, captures logs, and updates DB status (handling retries/DLQ)."""

    @staticmethod
    def execute(job_id: int, worker_id: str) -> bool:
        """
        Executes a job by ID.
        Returns True if successful, False if failed.
        """
        job = database.get_job(job_id)
        if not job:
            logger.error(f"Executor: Job {job_id} not found.")
            return False

        # Determine attempt number
        attempt_number = job.retry_count + 1
        started_at = utils.get_current_time_str()
        
        logger.info(f"Executor: Starting job {job.job_id} ({job.job_name}) on worker '{worker_id}'. Attempt {attempt_number}/{job.max_retries + 1}")

        # Create running execution log
        exec_data = JobExecution(
            execution_id=None,
            job_id=job.job_id,
            worker_id=worker_id,
            status="Running",
            attempt_number=attempt_number,
            started_at=started_at
        )
        exec_id = database.insert_execution(exec_data)
        exec_data.execution_id = exec_id

        start_time = time.perf_counter()
        
        stdout_content = ""
        stderr_content = ""
        error_msg = None
        exit_code = 0
        success = False

        try:
            # We run in a shell context to support compound commands, pipes, and python scripts
            # We enforce a timeout of 120 seconds for standard commands to prevent complete locks
            # Use universal_newlines (text=True) and capture_output
            res = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            stdout_content = res.stdout or ""
            stderr_content = res.stderr or ""
            exit_code = res.returncode
            
            if exit_code == 0:
                success = True
            else:
                error_msg = f"Command exited with non-zero code: {exit_code}"
                logger.error(f"Executor: Job {job_id} failed. {error_msg}")
        except subprocess.TimeoutExpired as te:
            stdout_content = te.stdout or ""
            stderr_content = te.stderr or f"TimeoutExpired: Command exceeded time limit of 120 seconds."
            error_msg = "Execution timed out (120s limit exceeded)."
            exit_code = -1
            logger.error(f"Executor: Job {job_id} timed out.")
        except Exception as e:
            stderr_content = str(e)
            error_msg = f"Execution exception: {type(e).__name__}: {str(e)}"
            exit_code = -2
            logger.exception(f"Executor: Job {job_id} raised exception during start.")

        duration = round(time.perf_counter() - start_time, 4)
        completed_at = utils.get_current_time_str()

        # Update execution log
        exec_data.status = "Completed" if success else "Failed"
        exec_data.completed_at = completed_at
        exec_data.duration = duration
        exec_data.stdout = stdout_content
        exec_data.stderr = stderr_content
        exec_data.error_message = error_msg
        database.update_execution(exec_data)

        # Update Job Record
        job.updated_at = completed_at
        if success:
            job.status = "Completed"
            job.completed_at = completed_at
            job.error_message = None
            database.update_job(job)
            logger.info(f"Executor: Job {job_id} Completed successfully in {duration}s.")
        else:
            # Handle Retry logic
            job.error_message = error_msg
            if job.retry_count < job.max_retries:
                # Schedule retry
                job.retry_count += 1
                next_time = utils.calculate_next_retry_time(
                    started_at, 
                    job.retry_policy, 
                    job.retry_interval, 
                    job.retry_count
                )
                job.status = "Pending"
                job.schedule_time = next_time
                database.update_job(job)
                logger.warning(
                    f"Executor: Job {job_id} Failed. Retry scheduled. "
                    f"Attempt {job.retry_count}/{job.max_retries}. Next run: {next_time} (Policy: {job.retry_policy})"
                )
            else:
                # Max retries exceeded -> DLQ
                job.status = "Failed"
                job.completed_at = completed_at
                database.update_job(job)
                
                # Push to Dead Letter Queue
                dlq_entry = DeadLetterJob(
                    dlq_id=None,
                    job_id=job.job_id,
                    job_name=job.job_name,
                    queue_name=job.queue_name,
                    command=job.command,
                    failed_at=completed_at,
                    reason=error_msg or "Unknown failure after max retries."
                )
                database.insert_dlq(dlq_entry)
                logger.error(f"Executor: Job {job_id} Failed. Max retries exceeded. Sent to Dead Letter Queue.")

        return success
