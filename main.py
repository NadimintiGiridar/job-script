import os
import sys
import time
import datetime
from typing import Optional

import config
import database
from scheduler import SchedulerEngine
from job_manager import JobManager
import utils
import validator
from logger import logger

# ANSI color codes for rich CLI aesthetics
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_CYAN = "\033[36m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE = "\033[34m"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_relative_time(input_str: str) -> str:
    """
    Parses inputs like '+10s', '+5m', '+2h' into a format YYYY-MM-DD HH:MM:SS.
    If it's already a timestamp, returns it.
    """
    cleaned = input_str.strip().lower()
    if cleaned.startswith("+"):
        unit = cleaned[-1]
        try:
            value = int(cleaned[1:-1])
            now = datetime.datetime.now()
            if unit == 's':
                delta = datetime.timedelta(seconds=value)
            elif unit == 'm':
                delta = datetime.timedelta(minutes=value)
            elif unit == 'h':
                delta = datetime.timedelta(hours=value)
            else:
                raise ValueError("Invalid relative time unit. Use 's' (seconds), 'm' (minutes), or 'h' (hours).")
            return (now + delta).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            if "Invalid relative time" in str(e):
                raise e
            raise ValueError("Invalid relative time format. Examples: +10s, +5m, +1h")
    return input_str

def display_header(title: str):
    print(f"\n{COLOR_CYAN}{'=' * 50}{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_MAGENTA}  {title.center(46)}  {COLOR_RESET}")
    print(f"{COLOR_CYAN}{'=' * 50}{COLOR_RESET}\n")

def run_dashboard_view(engine: SchedulerEngine):
    """Prints a full real-time DevOps Operations Dashboard snapshot."""
    while True:
        clear_screen()
        metrics = database.get_metrics()
        status_str = f"{COLOR_GREEN}RUNNING{COLOR_RESET}" if engine.running else f"{COLOR_RED}STOPPED{COLOR_RESET}"
        
        print(f"{COLOR_CYAN}================================================================================{COLOR_RESET}")
        print(f" {COLOR_BOLD}{COLOR_MAGENTA}DEVOPS OPERATIONS DASHBOARD{COLOR_RESET} | Status: {status_str} | Time: {utils.get_current_time_str()}")
        print(f"{COLOR_CYAN}================================================================================{COLOR_RESET}")
        
        # Row 1: Metrics
        print(f"{COLOR_BOLD}SYSTEM METRICS:{COLOR_RESET}")
        print(f"  Total Jobs: {COLOR_BOLD}{metrics['Total']}{COLOR_RESET} | "
              f"Pending: {COLOR_YELLOW}{metrics['Pending']}{COLOR_RESET} | "
              f"Running: {COLOR_CYAN}{metrics['Running']}{COLOR_RESET} | "
              f"Completed: {COLOR_GREEN}{metrics['Completed']}{COLOR_RESET} | "
              f"Failed: {COLOR_RED}{metrics['Failed']}{COLOR_RESET} | "
              f"Cancelled: {COLOR_BLUE}{metrics['Cancelled']}{COLOR_RESET}")
        print(f"  DLQ Size: {COLOR_RED}{COLOR_BOLD}{metrics['DLQ']}{COLOR_RESET} | "
              f"Active Workers: {COLOR_BOLD}{metrics['ActiveWorkers']}{COLOR_RESET} | "
              f"Avg Job Duration: {COLOR_BOLD}{metrics['AvgDurationSeconds']}s{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'-' * 80}{COLOR_RESET}")
        
        # Row 2: Active Workers
        print(f"{COLOR_BOLD}WORKER POOL HEALTH:{COLOR_RESET}")
        workers = database.list_workers()
        if not workers:
            print("  No workers registered in database.")
        else:
            w_headers = ["Worker ID", "Status", "Started At", "Last Heartbeat"]
            w_rows = [[w.worker_id, 
                       f"{COLOR_GREEN}Active{COLOR_RESET}" if w.status == 'Active' else f"{COLOR_RED}Inactive{COLOR_RESET}", 
                       w.started_at, w.last_heartbeat] for w in workers]
            print(utils.format_table(w_headers, w_rows))
            
        print(f"{COLOR_CYAN}{'-' * 80}{COLOR_RESET}")
        
        # Row 3: Dead Letter Queue
        print(f"{COLOR_BOLD}DEAD LETTER QUEUE (DLQ) - Recent Failures:{COLOR_RESET}")
        dlq_list = database.list_dlq()
        if not dlq_list:
            print("  Dead letter queue is empty. System is healthy.")
        else:
            d_headers = ["DLQ ID", "Job ID", "Job Name", "Failed At", "Reason"]
            d_rows = [[d.dlq_id, d.job_id, d.job_name, d.failed_at, d.reason[:30] + '...' if len(d.reason) > 30 else d.reason] for d in dlq_list[:3]]
            print(utils.format_table(d_headers, d_rows))
            
        print(f"{COLOR_CYAN}{'-' * 80}{COLOR_RESET}")
        
        # Row 4: Recent Executions
        print(f"{COLOR_BOLD}RECENT EXECUTIONS HISTORY:{COLOR_RESET}")
        all_jobs = database.list_jobs()
        executed_jobs = [j for j in all_jobs if j.status in ('Completed', 'Failed', 'Running')]
        if not executed_jobs:
            print("  No executed jobs found.")
        else:
            j_headers = ["Job ID", "Name", "Queue", "Status", "Schedule Time", "Worker", "Duration", "Error"]
            j_rows = []
            for j in executed_jobs[:5]:
                # Find execution duration if completed
                execs = database.get_job_executions(j.job_id)
                dur_str = f"{execs[-1].duration}s" if execs and execs[-1].duration is not None else "N/A"
                err_str = j.error_message[:20] if j.error_message else "None"
                
                status_colored = j.status
                if j.status == 'Completed':
                    status_colored = f"{COLOR_GREEN}Completed{COLOR_RESET}"
                elif j.status == 'Failed':
                    status_colored = f"{COLOR_RED}Failed{COLOR_RESET}"
                elif j.status == 'Running':
                    status_colored = f"{COLOR_CYAN}Running{COLOR_RESET}"
                    
                j_rows.append([j.job_id, j.job_name, j.queue_name, status_colored, j.schedule_time, j.worker_id or "None", dur_str, err_str])
            print(utils.format_table(j_headers, j_rows))

        print("\nPress [Ctrl+C] or enter [q] then [Enter] to return to Main Menu.")
        val = input("Refresh speed: auto-update active. Input command: ")
        if val.strip().lower() == 'q':
            break

def add_job_ui():
    display_header("ADD NEW JOB")
    
    # Show active queues
    queues = JobManager.get_queues()
    print("Available Queues:")
    for q in queues:
        status_flag = f"{COLOR_GREEN}[Active]{COLOR_RESET}" if q.status == 'Active' else f"{COLOR_RED}[Paused]{COLOR_RESET}"
        print(f"  - {q.queue_name} {status_flag}")
        
    try:
        name = input("\nEnter Job Name: ").strip()
        command = input("Enter execution command (e.g. echo 'working' or python script.py): ").strip()
        
        print("\nSchedule Time:")
        print("  - Relative format: '+10s' (10 seconds), '+5m' (5 minutes), '+2h' (2 hours)")
        print("  - Absolute format: 'YYYY-MM-DD HH:MM:SS'")
        time_input = input("Enter Schedule Time: ").strip()
        schedule_time = parse_relative_time(time_input)
        
        queue = input("Enter Queue Name [default]: ").strip() or "default"
        
        priority_input = input("Enter Priority (0=Low, 1=Medium, 2=High) [0]: ").strip() or "0"
        priority = int(priority_input)
        
        retry_policy = input("Enter Retry Policy (Fixed, Linear, Exponential) [Fixed]: ").strip() or "Fixed"
        retry_policy = retry_policy.capitalize()
        
        max_retries_input = input("Enter Max Retries [3]: ").strip() or "3"
        max_retries = int(max_retries_input)
        
        retry_interval_input = input("Enter Retry Interval (seconds) [5]: ").strip() or "5"
        retry_interval = int(retry_interval_input)
        
        job_id = JobManager.add_job(
            job_name=name,
            command=command,
            schedule_time=schedule_time,
            queue_name=queue,
            priority=priority,
            retry_policy=retry_policy,
            max_retries=max_retries,
            retry_interval=retry_interval
        )
        print(f"\n{COLOR_GREEN}✓ Job added successfully! Job ID: {job_id} Scheduled for: {schedule_time}{COLOR_RESET}")
    except ValueError as e:
        print(f"\n{COLOR_RED}✗ Validation Error: {str(e)}{COLOR_RESET}")
    except Exception as e:
        print(f"\n{COLOR_RED}✗ Unexpected Error: {str(e)}{COLOR_RESET}")

def view_jobs_ui():
    display_header("JOB EXPLORER")
    jobs = JobManager.get_all_jobs()
    
    if not jobs:
        print("No jobs found in system database.")
        return
        
    headers = ["ID", "Job Name", "Queue", "Command", "Schedule Time", "Status", "Priority", "Retries"]
    rows = []
    for j in jobs:
        priority_str = "Low" if j.priority == 0 else "Medium" if j.priority == 1 else "High"
        
        status_colored = j.status
        if j.status == 'Completed':
            status_colored = f"{COLOR_GREEN}Completed{COLOR_RESET}"
        elif j.status == 'Failed':
            status_colored = f"{COLOR_RED}Failed{COLOR_RESET}"
        elif j.status == 'Running':
            status_colored = f"{COLOR_CYAN}Running{COLOR_RESET}"
        elif j.status == 'Pending':
            status_colored = f"{COLOR_YELLOW}Pending{COLOR_RESET}"
        elif j.status == 'Cancelled':
            status_colored = f"{COLOR_BLUE}Cancelled{COLOR_RESET}"

        rows.append([
            j.job_id, j.job_name, j.queue_name, j.command, j.schedule_time, 
            status_colored, priority_str, f"{j.retry_count}/{j.max_retries}"
        ])
        
    print(utils.format_table(headers, rows))
    
    print("\nJob Submenu:")
    print("  1. View Job Executions / Attempt Log")
    print("  2. Reschedule / Edit Job")
    print("  3. Cancel Pending Job")
    print("  4. Delete Job")
    print("  5. Back to Main Menu")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == "1":
        job_id_str = input("Enter Job ID: ").strip()
        try:
            job_id = int(job_id_str)
            job = JobManager.get_job_details(job_id)
            if not job:
                print(f"{COLOR_RED}Job not found.{COLOR_RESET}")
                return
            
            print(f"\n{COLOR_BOLD}Job Details:{COLOR_RESET}")
            print(f"  Name: {job.job_name} | Queue: {job.queue_name}")
            print(f"  Command: {job.command}")
            print(f"  Status: {job.status} | Scheduled: {job.schedule_time}")
            if job.error_message:
                print(f"  Last Error: {COLOR_RED}{job.error_message}{COLOR_RESET}")
                
            execs = JobManager.get_job_executions(job_id)
            print(f"\n{COLOR_BOLD}Execution Attempt History ({len(execs)}):{COLOR_RESET}")
            if not execs:
                print("  No attempts registered.")
            else:
                ex_headers = ["Attempt", "Worker", "Status", "Started At", "Completed At", "Duration", "Error"]
                ex_rows = [[
                    e.attempt_number, e.worker_id, 
                    f"{COLOR_GREEN}Completed{COLOR_RESET}" if e.status == 'Completed' else f"{COLOR_RED}Failed{COLOR_RESET}" if e.status == 'Failed' else f"{COLOR_CYAN}Running{COLOR_RESET}",
                    e.started_at, e.completed_at or "N/A", 
                    f"{e.duration}s" if e.duration else "N/A", 
                    e.error_message or "None"
                ] for e in execs]
                print(utils.format_table(ex_headers, ex_rows))
                
                # Show stdout/stderr for the last execution if requested
                show_out = input("\nWould you like to print stdout/stderr logs of the last attempt? (y/n): ").strip().lower()
                if show_out == 'y':
                    last_ex = execs[-1]
                    print(f"\n{COLOR_BOLD}--- STDOUT ---{COLOR_RESET}")
                    print(last_ex.stdout or "(Empty)")
                    print(f"{COLOR_BOLD}--- STDERR ---{COLOR_RESET}")
                    print(last_ex.stderr or "(Empty)")
        except ValueError:
            print(f"{COLOR_RED}Invalid Job ID format.{COLOR_RESET}")
            
    elif choice == "2":
        job_id_str = input("Enter Job ID to Edit: ").strip()
        try:
            job_id = int(job_id_str)
            print("\nLeave input empty to retain existing values.")
            name = input("Enter Job Name: ").strip() or None
            cmd = input("Enter Command: ").strip() or None
            
            time_input = input("Enter Schedule Time (e.g. +10s or absolute date): ").strip()
            sched = parse_relative_time(time_input) if time_input else None
            
            pri_str = input("Enter Priority (0/1/2): ").strip()
            priority = int(pri_str) if pri_str else None
            
            policy = input("Enter Retry Policy (Fixed/Linear/Exponential): ").strip() or None
            
            max_r_str = input("Enter Max Retries: ").strip()
            max_retries = int(max_r_str) if max_r_str else None
            
            interval_str = input("Enter Retry Interval (s): ").strip()
            interval = int(interval_str) if interval_str else None
            
            JobManager.edit_job(
                job_id=job_id, job_name=name, command=cmd, schedule_time=sched,
                priority=priority, retry_policy=policy, max_retries=max_retries, retry_interval=interval
            )
            print(f"{COLOR_GREEN}✓ Job edited successfully!{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Edit failed: {str(e)}{COLOR_RESET}")
            
    elif choice == "3":
        job_id_str = input("Enter Job ID to Cancel: ").strip()
        try:
            job_id = int(job_id_str)
            JobManager.cancel_job(job_id)
            print(f"{COLOR_GREEN}✓ Job cancelled.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Cancel failed: {str(e)}{COLOR_RESET}")
            
    elif choice == "4":
        job_id_str = input("Enter Job ID to Delete: ").strip()
        try:
            job_id = int(job_id_str)
            confirm = input(f"Are you sure you want to delete job {job_id}? (y/n): ").strip().lower()
            if confirm == 'y':
                JobManager.delete_job(job_id)
                print(f"{COLOR_GREEN}✓ Job deleted.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Delete failed: {str(e)}{COLOR_RESET}")

def manage_queues_ui():
    display_header("QUEUE MANAGER")
    queues = JobManager.get_queues()
    
    headers = ["Queue Name", "Status", "Created At"]
    rows = [[q.queue_name, f"{COLOR_GREEN}Active{COLOR_RESET}" if q.status == 'Active' else f"{COLOR_RED}Paused{COLOR_RESET}", q.created_at] for q in queues]
    print(utils.format_table(headers, rows))
    
    print("\nQueue Actions:")
    print("  1. Add Queue")
    print("  2. Pause Queue")
    print("  3. Resume Queue")
    print("  4. Back to Main Menu")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == "1":
        name = input("Enter Queue Name: ").strip()
        try:
            JobManager.create_queue(name)
            print(f"{COLOR_GREEN}✓ Queue created.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Failed: {str(e)}{COLOR_RESET}")
            
    elif choice == "2":
        name = input("Enter Queue Name to Pause: ").strip()
        try:
            JobManager.pause_queue(name)
            print(f"{COLOR_GREEN}✓ Queue paused. Workers will stop executing jobs in this queue.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Failed: {str(e)}{COLOR_RESET}")
            
    elif choice == "3":
        name = input("Enter Queue Name to Resume: ").strip()
        try:
            JobManager.resume_queue(name)
            print(f"{COLOR_GREEN}✓ Queue resumed. Workers will now claim jobs from this queue.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}✗ Failed: {str(e)}{COLOR_RESET}")

def search_jobs_ui():
    display_header("SEARCH JOBS")
    q = input("Enter keyword (matches job name, status, command, queue): ").strip()
    
    results = JobManager.search_jobs(q)
    if not results:
        print("No matching jobs found.")
        return
        
    headers = ["ID", "Job Name", "Queue", "Command", "Schedule Time", "Status", "Priority"]
    rows = []
    for j in results:
        priority_str = "Low" if j.priority == 0 else "Medium" if j.priority == 1 else "High"
        
        status_colored = j.status
        if j.status == 'Completed':
            status_colored = f"{COLOR_GREEN}Completed{COLOR_RESET}"
        elif j.status == 'Failed':
            status_colored = f"{COLOR_RED}Failed{COLOR_RESET}"
        elif j.status == 'Running':
            status_colored = f"{COLOR_CYAN}Running{COLOR_RESET}"
        elif j.status == 'Pending':
            status_colored = f"{COLOR_YELLOW}Pending{COLOR_RESET}"
        elif j.status == 'Cancelled':
            status_colored = f"{COLOR_BLUE}Cancelled{COLOR_RESET}"
            
        rows.append([j.job_id, j.job_name, j.queue_name, j.command, j.schedule_time, status_colored, priority_str])
        
    print(utils.format_table(headers, rows))

def generate_report_ui():
    display_header("REPORT GENERATOR")
    try:
        report_path = JobManager.generate_report()
        print(f"{COLOR_GREEN}✓ System Metrics Report generated successfully!{COLOR_RESET}")
        print(f"Saved location: {COLOR_BOLD}{report_path}{COLOR_RESET}")
        
        # Optionally view it
        view = input("Would you like to print the report summary on the console? (y/n): ").strip().lower()
        if view == 'y':
            print("\n")
            with open(report_path, "r", encoding="utf-8") as f:
                print(f.read())
    except Exception as e:
        print(f"{COLOR_RED}✗ Report generation failed: {str(e)}{COLOR_RESET}")

def main():
    # 1. Initialize DB
    database.initialize_database()
    
    # 2. Start REST Web Server on port 5000
    try:
        from web_server import run_web_server
        run_web_server(port=5000)
    except Exception as e:
        logger.exception("Failed to start Web Server")
    
    # 3. Start Scheduler Engine (automatically on startup)
    engine = SchedulerEngine(num_workers=3)
    engine.start()
    
    try:
        while True:
            # Recompute scheduler status indicator
            sched_status = f"{COLOR_GREEN}[RUNNING - 3 Workers]{COLOR_RESET}" if engine.running else f"{COLOR_RED}[STOPPED]{COLOR_RESET}"
            
            print(f"\n{COLOR_CYAN}=================================={COLOR_RESET}")
            print(f" {COLOR_BOLD}{COLOR_MAGENTA}PRODUCTION JOB SCHEDULER SYSTEM{COLOR_RESET}")
            print(f" Scheduler status: {sched_status}")
            print(f"{COLOR_CYAN}=================================={COLOR_RESET}")
            print("  1. Add Job")
            print("  2. Job Explorer (View, Edit, Reschedule, Cancel, Log)")
            print("  3. Manage Queues (List, Pause, Resume)")
            print("  4. Search Jobs")
            print("  5. View Operations Dashboard (DevOps Monitor)")
            print("  6. Toggle Background Scheduler Engine")
            print("  7. Generate System Report")
            print("  8. Exit")
            print(f"{COLOR_CYAN}=================================={COLOR_RESET}")
            
            try:
                choice = input("Enter choice: ").strip()
            except EOFError:
                logger.info("Stdin EOF detected. Running in headless mode. Keeping background threads alive...")
                while True:
                    time.sleep(3600)
            
            if choice == "1":
                add_job_ui()
            elif choice == "2":
                view_jobs_ui()
            elif choice == "3":
                manage_queues_ui()
            elif choice == "4":
                search_jobs_ui()
            elif choice == "5":
                try:
                    run_dashboard_view(engine)
                except KeyboardInterrupt:
                    pass  # Return to menu gracefully on Ctrl+C
            elif choice == "6":
                if engine.running:
                    engine.stop()
                    print(f"{COLOR_YELLOW}SchedulerEngine stopped.{COLOR_RESET}")
                else:
                    engine.start()
                    print(f"{COLOR_GREEN}SchedulerEngine started.{COLOR_RESET}")
            elif choice == "7":
                generate_report_ui()
            elif choice == "8":
                print("\nGracefully shutting down worker threads...")
                engine.stop()
                print("Goodbye!")
                break
            else:
                print(f"{COLOR_RED}Invalid option. Please choose between 1 and 8.{COLOR_RESET}")
                
            # Quick pause to let user read feedback
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt detected. Shutting down worker threads...")
        engine.stop()
        print("Goodbye!")

if __name__ == "__main__":
    # Ensure ANSI colors are supported on Windows consoles
    if sys.platform.startswith("win"):
        os.system("color")
    main()
