import datetime
import os
from typing import List, Dict, Any, Optional
from logger import logger
from models import Job, Queue, DeadLetterJob, JobExecution, Project
import database
import validator
import utils

class JobManager:
    """Manages high-level CRUD operations, validations, and administrative actions for jobs/queues."""

    @staticmethod
    def create_queue(queue_name: str, project_id: Optional[int] = None) -> Queue:
        """Creates a new job queue. Validates formatting first."""
        cleaned_name = validator.validate_queue_name(queue_name)
        
        # Check if queue already exists
        existing = database.get_queue(cleaned_name)
        if existing:
            raise ValueError(f"Queue '{cleaned_name}' already exists.")
            
        now = utils.get_current_time_str()
        queue = Queue(queue_name=cleaned_name, status="Active", created_at=now, project_id=project_id)
        database.insert_queue(queue)
        logger.info(f"Queue '{cleaned_name}' created successfully.")
        return queue

    @staticmethod
    def create_project(project_name: str) -> Project:
        """Creates a new project."""
        if not project_name or not project_name.strip():
            raise ValueError("Project name cannot be empty.")
        
        cleaned_name = project_name.strip()
        now = utils.get_current_time_str()
        
        # Check if project already exists
        for p in database.list_projects():
            if p.project_name.lower() == cleaned_name.lower():
                raise ValueError(f"Project '{cleaned_name}' already exists.")
                
        project = Project(project_id=None, project_name=cleaned_name, created_at=now)
        project_id = database.insert_project(project)
        project.project_id = project_id
        return project

    @staticmethod
    def get_projects() -> List[Project]:
        """Lists all projects available in the system."""
        return database.list_projects()

    @staticmethod
    def pause_queue(queue_name: str):
        """Pauses a queue so workers stop claiming jobs from it."""
        queue = database.get_queue(queue_name)
        if not queue:
            raise ValueError(f"Queue '{queue_name}' does not exist.")
        if queue.status == "Paused":
            return
        database.update_queue_status(queue_name, "Paused")
        logger.info(f"Queue '{queue_name}' has been paused.")

    @staticmethod
    def resume_queue(queue_name: str):
        """Resumes a paused queue so workers can claim jobs again."""
        queue = database.get_queue(queue_name)
        if not queue:
            raise ValueError(f"Queue '{queue_name}' does not exist.")
        if queue.status == "Active":
            return
        database.update_queue_status(queue_name, "Active")
        logger.info(f"Queue '{queue_name}' has been resumed.")

    @staticmethod
    def get_queues() -> List[Queue]:
        """Lists all queues available in the system."""
        return database.list_queues()

    @staticmethod
    def add_job(
        job_name: str,
        command: str,
        schedule_time: str,
        queue_name: str = "default",
        priority: int = 0,
        retry_policy: str = "Fixed",
        max_retries: int = 3,
        retry_interval: int = 5
    ) -> int:
        """Validates parameters and inserts a job into the queue."""
        # Validation checks
        val_name = validator.validate_job_name(job_name)
        val_cmd = validator.validate_command(command)
        val_time = validator.validate_schedule_time(schedule_time)
        val_queue = validator.validate_queue_name(queue_name)
        val_priority = validator.validate_priority(priority)
        val_policy = validator.validate_retry_policy(retry_policy)
        val_max_retries = validator.validate_max_retries(max_retries)
        val_interval = validator.validate_retry_interval(retry_interval)

        # Check if queue exists
        queue = database.get_queue(val_queue)
        if not queue:
            raise ValueError(f"Queue '{val_queue}' does not exist. Please create it first.")

        now = utils.get_current_time_str()
        new_job = Job(
            job_id=None,
            job_name=val_name,
            queue_name=val_queue,
            command=val_cmd,
            schedule_time=val_time,
            status="Pending",
            priority=val_priority,
            retry_policy=val_policy,
            max_retries=val_max_retries,
            retry_interval=val_interval,
            created_at=now,
            updated_at=now
        )
        job_id = database.insert_job(new_job)
        logger.info(f"Job added successfully. Job ID: {job_id}, Name: {val_name}, Schedule Time: {val_time}")
        return job_id

    @staticmethod
    def edit_job(
        job_id: int,
        job_name: Optional[str] = None,
        command: Optional[str] = None,
        schedule_time: Optional[str] = None,
        priority: Optional[int] = None,
        retry_policy: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_interval: Optional[int] = None
    ) -> Job:
        """Modifies a job's details. Only allowed if status is Pending/Cancelled/Failed."""
        job = database.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")

        if job.status == "Running":
            raise ValueError(f"Cannot edit job {job_id} because it is currently running.")

        # Update and validate fields if provided
        if job_name is not None:
            job.job_name = validator.validate_job_name(job_name)
        if command is not None:
            job.command = validator.validate_command(command)
        if schedule_time is not None:
            # When rescheduling, we validate if time is in the future
            job.schedule_time = validator.validate_schedule_time(schedule_time)
            # If the job failed or was completed, we reset its status to Pending upon rescheduling
            if job.status in ("Failed", "Completed", "Cancelled"):
                job.status = "Pending"
                job.retry_count = 0
                job.error_message = None
                job.started_at = None
                job.completed_at = None
                job.worker_id = None
        if priority is not None:
            job.priority = validator.validate_priority(priority)
        if retry_policy is not None:
            job.retry_policy = validator.validate_retry_policy(retry_policy)
        if max_retries is not None:
            job.max_retries = validator.validate_max_retries(max_retries)
        if retry_interval is not None:
            job.retry_interval = validator.validate_retry_interval(retry_interval)

        job.updated_at = utils.get_current_time_str()
        database.update_job(job)
        logger.info(f"Job {job_id} updated successfully.")
        return job

    @staticmethod
    def delete_job(job_id: int):
        """Deletes a job. Cannot delete running jobs."""
        job = database.get_job(job_id)
        if not job:
            raise ValueError(f"Job with ID {job_id} not found.")
        if job.status == "Running":
            raise ValueError(f"Cannot delete job {job_id} because it is currently running.")
        
        database.delete_job(job_id)
        logger.info(f"Job {job_id} deleted successfully.")

    @staticmethod
    def search_jobs(query: str) -> List[Job]:
        """Searches jobs matching name, command, queue, or status."""
        return database.search_jobs(query)

    @staticmethod
    def get_all_jobs(status: Optional[str] = None) -> List[Job]:
        """Lists all jobs in the database."""
        return database.list_jobs(status)

    @staticmethod
    def get_job_details(job_id: int) -> Optional[Job]:
        """Gets detailed job profile by ID."""
        return database.get_job(job_id)

    @staticmethod
    def get_job_executions(job_id: int) -> List[JobExecution]:
        """Gets all attempt executions for a job."""
        return database.get_job_executions(job_id)

    @staticmethod
    def cancel_job(job_id: int):
        """Cancels a pending job."""
        job = database.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")
        if job.status != "Pending":
            raise ValueError(f"Only 'Pending' jobs can be cancelled. Current status: {job.status}")
        
        job.status = "Cancelled"
        job.updated_at = utils.get_current_time_str()
        database.update_job(job)
        logger.info(f"Job {job_id} has been cancelled.")

    @staticmethod
    def get_dlq_jobs() -> List[DeadLetterJob]:
        """Lists dead letter queue entries."""
        return database.list_dlq()

    @staticmethod
    def generate_report() -> str:
        """Generates a text report containing operational metrics and returns its path."""
        metrics = database.get_metrics()
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"report_{now_str}.txt"
        
        from config import REPORTS_DIR
        report_path = REPORTS_DIR / report_filename
        
        # Build nice format
        lines = [
            "================================================",
            "          JOB SCHEDULER SYSTEM REPORT           ",
            "================================================",
            f"Generated at: {utils.get_current_time_str()}",
            "------------------------------------------------",
            "METRICS SUMMARY:",
            f"  Total Registered Jobs: {metrics['Total']}",
            f"  Pending Jobs:          {metrics['Pending']}",
            f"  Running Jobs:          {metrics['Running']}",
            f"  Completed Jobs:        {metrics['Completed']}",
            f"  Failed Jobs:           {metrics['Failed']}",
            f"  Cancelled Jobs:        {metrics['Cancelled']}",
            "------------------------------------------------",
            f"  Dead Letter Queue:     {metrics['DLQ']} jobs",
            f"  Active Workers:        {metrics['ActiveWorkers']}",
            f"  Avg Exec Duration:     {metrics['AvgDurationSeconds']} seconds",
            "================================================",
        ]
        
        # Add details of recent failed/DLQ jobs
        dlq_jobs = database.list_dlq()
        if dlq_jobs:
            lines.append("\nDEAD LETTER QUEUE DETAILS:")
            for j in dlq_jobs[:5]:
                lines.append(f"  - DLQ ID: {j.dlq_id} | Job ID: {j.job_id} | Name: {j.job_name} | Failed At: {j.failed_at}")
                lines.append(f"    Reason: {j.reason}")
                
        # Write to file
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        logger.info(f"Report generated successfully: {report_path}")
        return str(report_path)
