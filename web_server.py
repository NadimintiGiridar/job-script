import http.server
import json
import os
import socketserver
import threading
import urllib.parse
from typing import Any, List, Dict
from logger import logger
import database
from job_manager import JobManager
import utils
import validator
import datetime
import random

# Start time for uptime calculation
START_TIME = datetime.datetime.now()

# Demo credentials for RBAC simulation
DEMO_USERS = {
    "admin@scheduler.io": {"password": "password", "role": "Admin", "name": "Sarah Connor"},
    "operator@scheduler.io": {"password": "password", "role": "Operator", "name": "John Doe"},
    "viewer@scheduler.io": {"password": "password", "role": "Viewer", "name": "Jane Smith"}
}

# Embedded Premium SaaS Single Page Application


# Store in-memory colored logs for UI consumption
SYSTEM_LOGS_CACHE: List[Dict[str, str]] = []

def add_system_log(level: str, text: str):
    """Saves a log memory chunk locally for live browser terminal consumption."""
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    SYSTEM_LOGS_CACHE.append({"time": now_str, "level": level, "text": text})
    if len(SYSTEM_LOGS_CACHE) > 200:
        SYSTEM_LOGS_CACHE.pop(0)

# Hook logger messages to also route to Dashboard Web Terminal
def log_info(msg: str):
    logger.info(msg)
    add_system_log("INFO", msg)

def log_warning(msg: str):
    logger.warning(msg)
    add_system_log("WARNING", msg)

def log_error(msg: str):
    logger.error(msg)
    add_system_log("ERROR", msg)

def log_success(msg: str):
    logger.info(msg)
    add_system_log("SUCCESS", msg)


class EnterpriseDashboardHandler(http.server.BaseHTTPRequestHandler):
    """SaaS style REST API endpoints & UI template server."""

    def log_message(self, format, *args):
        # Silence raw requests in console, forward to file logs
        logger.debug(format % args)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == '/':
            path = '/index.html'

        # Check if the file exists in the public folder
        public_dir = os.path.join(os.path.dirname(__file__), 'public')
        file_path = os.path.normpath(os.path.join(public_dir, path.lstrip('/')))
        if file_path.startswith(public_dir) and os.path.exists(file_path):
            self.send_response(200)
            if file_path.endswith('.html'): self.send_header('Content-Type', 'text/html; charset=utf-8')
            elif file_path.endswith('.css'): self.send_header('Content-Type', 'text/css; charset=utf-8')
            elif file_path.endswith('.js'): self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            elif file_path.endswith('.png'): self.send_header('Content-Type', 'image/png')
            else: self.send_header('Content-Type', 'application/octet-stream')
            self.end_headers()
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
            return

        # 2. REST API: Metrics
        elif path == "/api/metrics":
            try:
                metrics = database.get_metrics()
                self._send_json(metrics)
            except Exception as e:
                self._send_error(500, str(e))

        # 3. REST API: System Status
        elif path == "/api/system-status":
            try:
                uptime = str(datetime.datetime.now() - START_TIME).split('.')[0]
                status = "Active" if JobManager.get_queues() else "Stopped"
                # Simulated cpu / memory telemetry values
                cpu = round(random.uniform(3.0, 18.0), 1)
                memory = round(random.uniform(32.0, 35.0), 1)
                disk = 14.2
                self._send_json({
                    "uptime": uptime,
                    "status": status,
                    "thread_count": 3,
                    "cpu": cpu,
                    "memory": memory,
                    "disk": disk
                })
            except Exception as e:
                self._send_error(500, str(e))

        # 4. REST API: Jobs
        elif path == "/api/jobs":
            try:
                jobs = database.list_jobs()
                self._send_json([j.__dict__ for j in jobs])
            except Exception as e:
                self._send_error(500, str(e))

        # 5. REST API: Job Details
        elif path == "/api/jobs/details":
            try:
                query_params = urllib.parse.parse_qs(parsed_url.query)
                job_id_str = query_params.get("job_id", [None])[0]
                if not job_id_str:
                    self._send_error(400, "Missing job_id parameter.")
                    return
                job = database.get_job(int(job_id_str))
                if not job:
                    self._send_error(404, "Job not found.")
                else:
                    self._send_json(job.__dict__)
            except Exception as e:
                self._send_error(500, str(e))

        # 6. REST API: Job Executions
        elif path == "/api/executions":
            try:
                query_params = urllib.parse.parse_qs(parsed_url.query)
                job_id_str = query_params.get("job_id", [None])[0]
                if not job_id_str:
                    self._send_error(400, "Missing job_id parameter.")
                    return
                execs = database.get_job_executions(int(job_id_str))
                self._send_json([e.__dict__ for e in execs])
            except Exception as e:
                self._send_error(500, str(e))

        # 7. REST API: Queues List
        elif path == "/api/queues":
            try:
                queues = database.list_queues()
                self._send_json([q.__dict__ for q in queues])
            except Exception as e:
                self._send_error(500, str(e))

        # 7b. REST API: Projects List
        elif path == "/api/projects":
            try:
                projects = database.list_projects()
                self._send_json([p.__dict__ for p in projects])
            except Exception as e:
                self._send_error(500, str(e))

        # 8. REST API: Workers Pool
        elif path == "/api/workers":
            try:
                workers = database.list_workers()
                self._send_json([w.__dict__ for w in workers])
            except Exception as e:
                self._send_error(500, str(e))

        # 9. REST API: DLQ
        elif path == "/api/dlq":
            try:
                dlq = database.list_dlq()
                self._send_json([d.__dict__ for d in dlq])
            except Exception as e:
                self._send_error(500, str(e))

        # 10. REST API: Live Logs
        elif path == "/api/live-logs":
            self._send_json(SYSTEM_LOGS_CACHE)

        # 11. REST API: Audit Logs
        elif path == "/api/audit-logs":
            try:
                logs = database.list_audit_logs()
                self._send_json(logs)
            except Exception as e:
                self._send_error(500, str(e))

        # 12. REST API: Analytics
        elif path == "/api/analytics":
            # Generate mock last 7 days analytics breakdown
            analytics_list = []
            today = datetime.date.today()
            for i in range(6, -1, -1):
                day = today - datetime.timedelta(days=i)
                day_str = day.strftime("%a")
                # Generate realistic completed / failed stats
                completed = random.randint(10, 45) if i != 0 else random.randint(1, 10)
                failed = random.randint(0, 3)
                duration = round(random.uniform(0.1, 1.8), 2)
                analytics_list.append({
                    "day": day_str,
                    "completed": completed,
                    "failed": failed,
                    "duration": duration
                })
            self._send_json(analytics_list)

        else:
            self._send_error(404, "Endpoint not found.")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b""
        
        try:
            body = json.loads(post_data.decode('utf-8')) if post_data else {}
        except json.JSONDecodeError:
            self._send_error(400, "Malformed JSON request.")
            return

        # 1. POST REST: Login
        if path == "/api/auth/login":
            email = body.get("email")
            password = body.get("password")
            user = DEMO_USERS.get(email)
            if user and user["password"] == password:
                database.insert_audit_log(
                    username=user["name"],
                    role=user["role"],
                    action="User Login",
                    target="AuthSystem",
                    details=f"Successful login for {email}."
                )
                self._send_json({
                    "success": True,
                    "name": user["name"],
                    "role": user["role"]
                })
            else:
                self._send_error(401, "Invalid email or password.")

        # 2. POST REST: Logout
        elif path == "/api/auth/logout":
            username = body.get("username", "Unknown")
            database.insert_audit_log(
                username=username,
                role="Unknown",
                action="User Logout",
                target="AuthSystem",
                details=f"User logged out of session."
            )
            self._send_json({"success": True})

        # 3. POST REST: Register
        elif path == "/api/auth/register":
            email = body.get("email")
            name = body.get("name")
            password = body.get("password")
            role = body.get("role", "Viewer")
            if email in DEMO_USERS:
                self._send_error(400, "User email already exists.")
            else:
                DEMO_USERS[email] = {"password": password, "role": role, "name": name}
                database.insert_audit_log(
                    username=name,
                    role=role,
                    action="Register User",
                    target="AuthSystem",
                    details=f"Registered account for {email}."
                )
                self._send_json({"success": True})

        # 4. POST REST: Create Job
        elif path == "/api/jobs":
            # RBAC check
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot create jobs.")
                return

            try:
                schedule_time_input = body.get("schedule_time", "")
                cleaned_input = schedule_time_input.strip().lower()
                
                # Settle relative offsets
                if cleaned_input.startswith("+"):
                    unit = cleaned_input[-1]
                    value = int(cleaned_input[1:-1])
                    now = datetime.datetime.now()
                    if unit == 's':
                        delta = datetime.timedelta(seconds=value)
                    elif unit == 'm':
                        delta = datetime.timedelta(minutes=value)
                    elif unit == 'h':
                        delta = datetime.timedelta(hours=value)
                    else:
                        raise ValueError("Invalid unit. Use s, m, or h.")
                    schedule_time = (now + delta).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    schedule_time = schedule_time_input

                job_id = JobManager.add_job(
                    job_name=body.get("job_name", ""),
                    command=body.get("command", ""),
                    schedule_time=schedule_time,
                    queue_name=body.get("queue_name", "default"),
                    priority=int(body.get("priority", 0)),
                    retry_policy=body.get("retry_policy", "Fixed"),
                    max_retries=int(body.get("max_retries", 3)),
                    retry_interval=int(body.get("retry_interval", 5))
                )
                
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Create Job",
                    target=f"Job {job_id}",
                    details=f"Scheduled job '{body.get('job_name')}' to run at {schedule_time}."
                )
                add_system_log("INFO", f"Job {job_id} ('{body.get('job_name')}') created successfully.")
                self._send_json({"success": True, "job_id": job_id})
            except Exception as e:
                self._send_error(500, str(e))

        # 5. POST REST: Edit Job
        elif path == "/api/jobs/edit":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot edit jobs.")
                return

            try:
                job_id = int(body.get("job_id"))
                JobManager.edit_job(
                    job_id=job_id,
                    job_name=body.get("job_name"),
                    command=body.get("command"),
                    schedule_time=body.get("schedule_time"),
                    priority=int(body.get("priority")),
                    retry_policy=body.get("retry_policy"),
                    max_retries=int(body.get("max_retries")),
                    retry_interval=int(body.get("retry_interval"))
                )
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Edit Job",
                    target=f"Job {job_id}",
                    details=f"Updated job configurations."
                )
                add_system_log("INFO", f"Job {job_id} configuration modified.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 6. POST REST: Clone Job
        elif path == "/api/jobs/clone":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot clone jobs.")
                return

            try:
                src_id = int(body.get("job_id"))
                job = database.get_job(src_id)
                if not job:
                    self._send_error(404, "Source job not found.")
                    return
                
                # Append duplicate suffix
                clone_id = JobManager.add_job(
                    job_name=f"{job.job_name}_Clone",
                    command=job.command,
                    schedule_time=job.schedule_time,
                    queue_name=job.queue_name,
                    priority=job.priority,
                    retry_policy=job.retry_policy,
                    max_retries=job.max_retries,
                    retry_interval=job.retry_interval
                )
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Clone Job",
                    target=f"Job {clone_id}",
                    details=f"Cloned parameters from Job {src_id}."
                )
                add_system_log("INFO", f"Job {clone_id} cloned from {src_id}.")
                self._send_json({"success": True, "clone_id": clone_id})
            except Exception as e:
                self._send_error(500, str(e))

        # 7. POST REST: Retry Job
        elif path == "/api/jobs/retry":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot retry jobs.")
                return

            try:
                job_id = int(body.get("job_id"))
                job = database.get_job(job_id)
                if not job:
                    self._send_error(404, "Job not found.")
                    return

                # Schedule execution immediately
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                job.status = "Pending"
                job.schedule_time = now_str
                job.retry_count = 0
                database.update_job(job)
                
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Retry Job",
                    target=f"Job {job_id}",
                    details=f"Forced immediate retry rescheduling."
                )
                add_system_log("INFO", f"Job {job_id} rescheduled immediately.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 8. POST REST: Pause Job
        elif path == "/api/jobs/pause":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot pause jobs.")
                return

            try:
                job_id = int(body.get("job_id"))
                JobManager.cancel_job(job_id)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Pause Job",
                    target=f"Job {job_id}",
                    details=f"Paused job (status set to Cancelled)."
                )
                add_system_log("INFO", f"Job {job_id} paused.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 9. POST REST: Resume Job
        elif path == "/api/jobs/resume":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot resume jobs.")
                return

            try:
                job_id = int(body.get("job_id"))
                job = database.get_job(job_id)
                if job and job.status == "Cancelled":
                    job.status = "Pending"
                    database.update_job(job)
                    database.insert_audit_log(
                        username=body.get("username", "Operator"),
                        role=role,
                        action="Resume Job",
                        target=f"Job {job_id}",
                        details=f"Resumed job (status set to Pending)."
                    )
                    add_system_log("INFO", f"Job {job_id} resumed.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 10. POST REST: Delete Job
        elif path == "/api/jobs/delete":
            role = body.get("role", "Viewer")
            if role != "Admin":
                self._send_error(403, "Only Admin role can delete jobs.")
                return

            try:
                job_id = int(body.get("job_id"))
                JobManager.delete_job(job_id)
                database.insert_audit_log(
                    username=body.get("username", "Admin"),
                    role=role,
                    action="Delete Job",
                    target=f"Job {job_id}",
                    details=f"Permanently removed job and its executions."
                )
                add_system_log("WARNING", f"Job {job_id} deleted permanently.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 11. POST REST: Bulk Delete
        elif path == "/api/jobs/bulk-delete":
            role = body.get("role", "Viewer")
            if role != "Admin":
                self._send_error(403, "Only Admin role can perform bulk delete.")
                return

            try:
                ids = body.get("ids", [])
                for job_id in ids:
                    JobManager.delete_job(int(job_id))
                database.insert_audit_log(
                    username=body.get("username", "Admin"),
                    role=role,
                    action="Bulk Delete",
                    target=f"Jobs {ids}",
                    details=f"Deleted jobs in bulk."
                )
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 12. POST REST: Bulk Retry
        elif path == "/api/jobs/bulk-retry":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot retry jobs.")
                return

            try:
                ids = body.get("ids", [])
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for job_id in ids:
                    job = database.get_job(int(job_id))
                    if job:
                        job.status = "Pending"
                        job.schedule_time = now_str
                        job.retry_count = 0
                        database.update_job(job)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Bulk Retry",
                    target=f"Jobs {ids}",
                    details=f"Triggered bulk reschedule retries."
                )
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 13. POST REST: Pause Queue
        elif path == "/api/queues/pause":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot pause queues.")
                return

            try:
                q_name = body.get("queue_name", "default")
                JobManager.pause_queue(q_name)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Pause Queue",
                    target=f"Queue {q_name}",
                    details="Paused task executions."
                )
                add_system_log("WARNING", f"Queue '{q_name}' paused.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 14. POST REST: Resume Queue
        elif path == "/api/queues/resume":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot resume queues.")
                return

            try:
                q_name = body.get("queue_name", "default")
                JobManager.resume_queue(q_name)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Resume Queue",
                    target=f"Queue {q_name}",
                    details="Resumed task executions."
                )
                add_system_log("INFO", f"Queue '{q_name}' resumed.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 14b. POST REST: Create Queue
        elif path == "/api/queues":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot create queues.")
                return

            try:
                q_name = body.get("queue_name")
                project_id = body.get("project_id")
                if project_id:
                    project_id = int(project_id)
                JobManager.create_queue(q_name, project_id)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Create Queue",
                    target=f"Queue {q_name}",
                    details=f"Created queue '{q_name}' under project ID {project_id}."
                )
                add_system_log("INFO", f"Queue '{q_name}' created successfully.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 14c. POST REST: Create Project
        elif path == "/api/projects":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot create projects.")
                return

            try:
                p_name = body.get("project_name")
                project = JobManager.create_project(p_name)
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Create Project",
                    target=f"Project {p_name}",
                    details=f"Created project '{p_name}' successfully."
                )
                add_system_log("INFO", f"Project '{p_name}' created successfully.")
                self._send_json({"success": True, "project_id": project.project_id})
            except Exception as e:
                self._send_error(500, str(e))

        # 15. POST REST: Restart Worker Simulation
        elif path == "/api/workers/restart":
            role = body.get("role", "Viewer")
            if role == "Viewer":
                self._send_error(403, "Viewer role cannot restart workers.")
                return

            try:
                worker_id = body.get("worker_id")
                database.insert_audit_log(
                    username=body.get("username", "Operator"),
                    role=role,
                    action="Restart Worker",
                    target=f"Worker {worker_id}",
                    details="Dispatched restart signal to worker thread."
                )
                add_system_log("WARNING", f"Reboot signal received for worker '{worker_id}'.")
                self._send_json({"success": True})
            except Exception as e:
                self._send_error(500, str(e))

        # 16. POST REST: Generate Report (CSV, JSON, TXT)
        elif path == "/api/reports/generate":
            try:
                timeframe = body.get("timeframe", "Daily")
                fmt = body.get("format", "TXT")
                role = body.get("role", "Viewer")
                
                # Fetch database data for audit report
                jobs = database.list_jobs()
                dlq = database.list_dlq()
                workers = database.list_workers()
                metrics = database.get_metrics()
                
                database.insert_audit_log(
                    username=body.get("username", "Viewer"),
                    role=role,
                    action="Generate Report",
                    target="ReportsEngine",
                    details=f"Generated {timeframe} report in {fmt} format."
                )

                if fmt == "JSON":
                    report_data = {
                        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "timeframe": timeframe,
                        "metrics": metrics,
                        "workers": [w.__dict__ for w in workers],
                        "dead_letter_queue": [d.__dict__ for d in dlq],
                        "recent_jobs": [j.__dict__ for j in jobs[:20]]
                    }
                    self._send_json(report_data)
                elif fmt == "CSV":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.end_headers()
                    csv_data = "Job_ID,Job_Name,Queue,Command,Schedule_Time,Status,Priority\n"
                    for j in jobs:
                        csv_data += f"{j.job_id},{j.job_name},{j.queue_name},{j.command},{j.schedule_time},{j.status},{j.priority}\n"
                    self.wfile.write(csv_data.encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    txt_data = f"===========================================\n"
                    txt_data += f" SCHEDULER SYSTEM REPORT ({timeframe.upper()})\n"
                    txt_data += f" Generated At: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    txt_data += f"===========================================\n"
                    txt_data += f"Metrics:\n"
                    for k, v in metrics.items():
                        txt_data += f"  {k}: {v}\n"
                    txt_data += f"\nTotal Jobs List Count: {len(jobs)}\n"
                    self.wfile.write(txt_data.encode('utf-8'))
            except Exception as e:
                self._send_error(500, str(e))

        # 17. POST REST: Change Password
        elif path == "/api/profile/password":
            try:
                email = body.get("email")
                curr = body.get("current_password")
                new_p = body.get("new_password")
                role = body.get("role")
                user = DEMO_USERS.get(email)
                if user and user["password"] == curr:
                    user["password"] = new_p
                    database.insert_audit_log(
                        username=user["name"],
                        role=role,
                        action="Change Password",
                        target="AuthSystem",
                        details="Successfully updated user password."
                    )
                    self._send_json({"success": True})
                else:
                    self._send_error(400, "Current password does not match.")
            except Exception as e:
                self._send_error(500, str(e))

        else:
            self._send_error(404, "Endpoint not found.")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _send_error(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode('utf-8'))


def run_web_server(port: int = 5000) -> threading.Thread:
    """Starts the REST server on a background daemon thread."""
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        pass

    server = ThreadingHTTPServer(("0.0.0.0", port), EnterpriseDashboardHandler)
    server.allow_reuse_address = True

    thread = threading.Thread(
        target=server.serve_forever,
        name="RESTWebServer",
        daemon=True
    )
    thread.start()
    logger.info(f"REST Dashboard server successfully started on background port {port}.")
    return thread
