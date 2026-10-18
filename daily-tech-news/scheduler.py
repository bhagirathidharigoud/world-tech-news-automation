# ─────────────────────────────────────────────────────────────────
#  scheduler.py
#
#  PURPOSE:
#  Run the daily news pipeline automatically at a configured time.
#  This is the automation engine of the entire project.
#
#  HOW TO RUN:
#      python scheduler.py
#
#  The scheduler will:
#    1. Run the job IMMEDIATELY on startup (so you can test it).
#    2. Schedule the job to run every day at NEWS_SCHEDULE_HOUR:MINUTE.
#    3. Keep running until you press Ctrl+C.
#
#  SCHEDULE CONFIGURATION (in .env):
#      NEWS_SCHEDULE_HOUR=6
#      NEWS_SCHEDULE_MINUTE=0
# ─────────────────────────────────────────────────────────────────

import signal                          # Handles Ctrl+C shutdown
import sys                             # System exit
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
# BlockingScheduler: keeps the Python process alive.
# The program does not exit — it waits for the next scheduled time.

from apscheduler.triggers.cron import CronTrigger
# CronTrigger: schedule a job by hour/minute, like a cron job.
# "Run at 06:00 every day" = CronTrigger(hour=6, minute=0)

from apscheduler.events import (
    EVENT_JOB_EXECUTED,   # Fired when a job finishes successfully
    EVENT_JOB_ERROR       # Fired when a job raises an exception
)

from config import (
    NEWS_SCHEDULE_HOUR,
    NEWS_SCHEDULE_MINUTE,
    validate_config
)
from database import connect_to_mongodb, disconnect_from_mongodb
from news_service import fetch_and_store_news
from briefing_service import generate_daily_briefing


# ── MODULE-LEVEL SCHEDULER INSTANCE ──────────────────────────────
# Created once at module level so the signal handler can
# access it to shut down cleanly on Ctrl+C.
scheduler = BlockingScheduler(timezone="UTC")


# ═════════════════════════════════════════════════════════════════
#  THE DAILY JOB
# ═════════════════════════════════════════════════════════════════

def daily_job():
    """
    The main job that runs every morning.

    Executes the complete pipeline in order:
      1. Connect to MongoDB
      2. Fetch latest news from API
      3. Store articles in MongoDB
      4. Generate the daily briefing
      5. Print the briefing to terminal
      6. Disconnect from MongoDB

    This function is registered with APScheduler.
    APScheduler calls it automatically at the scheduled time.

    Python concept — Functions as values:
        When we write:
            scheduler.add_job(func=daily_job, ...)
        We are passing the FUNCTION ITSELF as a value,
        not calling it (no parentheses).
        APScheduler stores the reference and calls it later.
    """
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\n" + "#" * 60)
    print(f"  DAILY JOB STARTED")
    print(f"  Time: {run_time}")
    print("#" * 60)

    # Python concept — try/finally:
    # The 'finally' block ALWAYS runs, even if an exception occurs
    # inside the 'try' block. This guarantees the MongoDB connection
    # is closed even if fetch or briefing generation fails.

    try:
        # ── STEP 1: Connect to MongoDB ────────────────────────────
        connected = connect_to_mongodb()
        if not connected:
            print("DAILY JOB ABORTED: Could not connect to MongoDB.")
            return

        # ── STEP 2 & 3: Fetch and store news ─────────────────────
        fetch_result = fetch_and_store_news()

        print(f"\nFetch complete:")
        print(f"  Fetched : {fetch_result['fetched']} articles")
        print(f"  Saved   : {fetch_result['saved']} new articles")
        print(f"  Skipped : {fetch_result['skipped']} duplicates")

        # ── STEP 4 & 5: Generate and print briefing ───────────────
        briefing = generate_daily_briefing()

        if briefing:
            print(f"\nBriefing generated for {briefing['briefing_date']}.")
        else:
            print("\nBriefing could not be generated.")

    except Exception as e:
        # Catch any unexpected error so the scheduler keeps running.
        # The job failing should NOT stop the scheduler.
        print(f"\nERROR in daily_job: {e}")
        print("The scheduler will continue and retry at the next scheduled time.")

    finally:
        # This runs whether the try block succeeded or failed.
        disconnect_from_mongodb()

    print("\n" + "#" * 60)
    print("  DAILY JOB COMPLETE")
    print("#" * 60 + "\n")


# ═════════════════════════════════════════════════════════════════
#  JOB EVENT LISTENERS
# ═════════════════════════════════════════════════════════════════

def _on_job_executed(event):
    """
    Called by APScheduler after a job finishes successfully.

    APScheduler concept — Events:
        APScheduler fires events at key moments (job started,
        job succeeded, job failed). We can attach listener
        functions to react to these events.

    Args:
        event: APScheduler event object with job details.
    """
    next_run = scheduler.get_job("daily_news_job")
    if next_run and next_run.next_run_time:
        next_str = next_run.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
        print(f"  Next scheduled run: {next_str}")


def _on_job_error(event):
    """
    Called by APScheduler if a job raises an unhandled exception.

    Args:
        event: APScheduler event object with exception details.
    """
    print(f"\n  SCHEDULER ERROR: Job '{event.job_id}' failed.")
    if event.exception:
        print(f"  Exception: {event.exception}")
    print("  Scheduler will continue and retry at the next scheduled time.\n")


# ═════════════════════════════════════════════════════════════════
#  GRACEFUL SHUTDOWN
# ═════════════════════════════════════════════════════════════════

def _handle_shutdown(signum, frame):
    """
    Handle Ctrl+C (SIGINT) and system termination (SIGTERM) cleanly.

    Without this, pressing Ctrl+C would crash the program with a
    messy traceback. With this, it shuts down gracefully.

    Python concept — signal module:
        The operating system sends signals to processes.
        SIGINT = Ctrl+C (interrupt)
        SIGTERM = system shutdown request
        signal.signal(SIGINT, handler) tells Python:
        "when Ctrl+C is pressed, call handler() instead of crashing"

    Args:
        signum: The signal number received.
        frame:  Current stack frame (not used here).
    """
    print("\n\nShutdown signal received. Stopping scheduler...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    disconnect_from_mongodb()
    print("Scheduler stopped. Goodbye.")
    sys.exit(0)


# ═════════════════════════════════════════════════════════════════
#  SCHEDULER SETUP AND START
# ═════════════════════════════════════════════════════════════════

def start_scheduler(run_now=True):
    """
    Configure and start the APScheduler.

    Args:
        run_now (bool): If True, run daily_job() immediately on
                        startup before waiting for the schedule.
                        Useful for testing — you don't have to wait
                        until 6 AM to see if everything works.

    APScheduler concept — CronTrigger:
        CronTrigger(hour=6, minute=0) means:
        "run at 06:00 every day"

        More examples:
        CronTrigger(hour=9, minute=30)       → 9:30 AM daily
        CronTrigger(hour="*/2", minute=0)    → every 2 hours
        CronTrigger(day_of_week="mon-fri")   → weekdays only

    APScheduler concept — BlockingScheduler:
        .start() blocks the current thread.
        The program stays alive and keeps checking:
        "Is it time to run a job yet?"
        This is why we run scheduler.py as a long-running process,
        not a one-off script.
    """

    # ── VALIDATE CONFIG BEFORE STARTING ──────────────────────────
    errors = validate_config()
    if errors:
        print("Configuration errors found. Fix these before starting the scheduler:")
        for error in errors:
            print(f"  [ERROR] {error}")
        sys.exit(1)

    # ── REGISTER SIGNAL HANDLERS ──────────────────────────────────
    # Python concept — signal.signal():
    # Map Ctrl+C and system termination to our clean shutdown function.
    signal.signal(signal.SIGINT,  _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    # ── ATTACH EVENT LISTENERS ────────────────────────────────────
    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error,    EVENT_JOB_ERROR)

    # ── REGISTER THE DAILY JOB ────────────────────────────────────
    # CronTrigger fires at the exact hour:minute every day.
    # The schedule is read from .env via config.py —
    # never hardcoded here.
    scheduler.add_job(
        func=daily_job,              # The function to call
        trigger=CronTrigger(
            hour=NEWS_SCHEDULE_HOUR,
            minute=NEWS_SCHEDULE_MINUTE
        ),
        id="daily_news_job",         # Unique ID for this job
        name="Daily Tech News Fetch",
        replace_existing=True        # Don't add duplicates on restart
    )

    # ── PRINT STARTUP BANNER ──────────────────────────────────────
    print("=" * 60)
    print("  DAILY GLOBAL TECH NEWS SCHEDULER")
    print("=" * 60)
    print(f"  Schedule  : Every day at "
          f"{NEWS_SCHEDULE_HOUR:02d}:{NEWS_SCHEDULE_MINUTE:02d} UTC")
    print(f"  Run now   : {run_now}")
    print(f"  Stop      : Press Ctrl+C")
    print("=" * 60)

    # ── RUN IMMEDIATELY IF REQUESTED ──────────────────────────────
    # run_now=True means we don't have to wait until tomorrow
    # morning to test that the full pipeline works.
    if run_now:
        print("\nRunning job immediately for testing...\n")
        daily_job()

    # Show the next scheduled run time.
    job = scheduler.get_job("daily_news_job")
    if job:
        # next_run_time is None until the scheduler starts,
        # so we calculate it manually for the display.
        print(f"\nNext automatic run: "
              f"{NEWS_SCHEDULE_HOUR:02d}:{NEWS_SCHEDULE_MINUTE:02d} UTC daily")

    print("\nScheduler is running. Press Ctrl+C to stop.\n")

    # ── START THE SCHEDULER ───────────────────────────────────────
    # .start() blocks here — the program will not exit.
    # APScheduler waits in the background and fires daily_job()
    # at the configured time every day.
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        # Ctrl+C was pressed — shut down cleanly.
        pass


# ═════════════════════════════════════════════════════════════════
#  MANUAL TRIGGER UTILITY
# ═════════════════════════════════════════════════════════════════

def run_once():
    """
    Run the daily job exactly once without starting the scheduler.

    Useful for:
    - Testing the pipeline manually
    - Running from a cron job outside of Python
    - Debugging a specific day's news

    Does NOT keep the process alive after the job finishes.
    """
    print("Running daily job once (no scheduler)...")
    daily_job()
    print("Done.")


# ═════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════

# Python concept — if __name__ == "__main__":
#
# Every Python file has a built-in variable called __name__.
# When you RUN a file directly:      python scheduler.py
#   → __name__ is set to "__main__"
# When another file IMPORTs this file:  from scheduler import run_once
#   → __name__ is set to "scheduler" (the module name)
#
# This block runs ONLY when the file is executed directly,
# NOT when it is imported. This prevents the scheduler from
# starting automatically just because another file imports it.

if __name__ == "__main__":

    import sys

    # Allow running with an optional argument:
    #   python scheduler.py        → start scheduler (runs job immediately)
    #   python scheduler.py once   → run job once and exit
    #   python scheduler.py norun  → start scheduler, skip immediate run

    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

        if mode == "once":
            # Run the job one time and exit.
            run_once()

        elif mode == "norun":
            # Start the scheduler but don't run immediately.
            # Wait for the scheduled time.
            start_scheduler(run_now=False)

        else:
            print(f"Unknown argument: {mode}")
            print("Usage:")
            print("  python scheduler.py         → start + run immediately")
            print("  python scheduler.py once    → run once and exit")
            print("  python scheduler.py norun   → start, wait for schedule")

    else:
        # Default: start scheduler and run immediately.
        start_scheduler(run_now=True)
