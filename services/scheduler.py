"""
Agent Scheduler - runs agent instances on their configured schedules.

Uses APScheduler for lightweight cron-style scheduling within the
FastAPI process. Each active agent instance with a non-manual schedule
gets a periodic job that triggers its run() method.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            _scheduler = AsyncIOScheduler()
            logger.info("APScheduler initialized")
        except ImportError:
            logger.warning("apscheduler not installed — scheduled agents will not run automatically")
    return _scheduler


async def start_scheduler():
    scheduler = get_scheduler()
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("Agent scheduler started")


async def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Agent scheduler stopped")


SCHEDULE_INTERVALS = {
    "hourly": {"hours": 1},
    "daily": {"hours": 24},
    "weekly": {"weeks": 1},
}


def schedule_agent_instance(instance_id: str, schedule: str, run_fn):
    """Add or update a scheduled job for an agent instance."""
    scheduler = get_scheduler()
    if not scheduler:
        return

    job_id = f"agent_{instance_id}"

    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    if schedule == "manual" or schedule not in SCHEDULE_INTERVALS:
        return

    interval = SCHEDULE_INTERVALS[schedule]
    scheduler.add_job(
        run_fn,
        "interval",
        id=job_id,
        **interval,
        next_run_time=datetime.utcnow() + timedelta(minutes=1),
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(f"Scheduled agent {instance_id} to run {schedule}")


def unschedule_agent_instance(instance_id: str):
    scheduler = get_scheduler()
    if not scheduler:
        return
    job_id = f"agent_{instance_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Unscheduled agent {instance_id}")


def next_run_time(instance_id: str) -> Optional[str]:
    scheduler = get_scheduler()
    if not scheduler:
        return None
    job = scheduler.get_job(f"agent_{instance_id}")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
