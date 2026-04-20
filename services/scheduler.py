"""
Agent Scheduler - runs agent instances on their configured schedules.

Supports cron-style scheduling: pick a frequency (daily/weekly),
a day of week (for weekly), and a time of day. Uses APScheduler
CronTrigger for precise scheduling.
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


def schedule_agent_instance(instance_id: str, config: dict, run_fn):
    """Schedule an agent using config: schedule, schedule_day, schedule_time."""
    scheduler = get_scheduler()
    if not scheduler:
        return

    job_id = f"agent_{instance_id}"

    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    schedule = config.get("schedule", "manual")
    if schedule == "manual":
        return

    hour, minute = _parse_time(config.get("schedule_time", "08:00"))
    day_of_week = config.get("schedule_day", "mon")

    try:
        from apscheduler.triggers.cron import CronTrigger

        if schedule == "hourly":
            trigger = CronTrigger(minute=0)
        elif schedule == "daily":
            trigger = CronTrigger(hour=hour, minute=minute)
        elif schedule == "weekly":
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
        else:
            logger.warning(f"Unknown schedule type: {schedule}")
            return

        scheduler.add_job(
            run_fn,
            trigger,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,
        )
        label = _schedule_label(schedule, day_of_week, hour, minute)
        logger.info(f"Scheduled agent {instance_id}: {label}")
    except Exception as e:
        logger.error(f"Failed to schedule agent {instance_id}: {e}")


def _parse_time(time_str: str) -> tuple[int, int]:
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) % 24, int(parts[1]) % 60
    except (ValueError, IndexError):
        return 8, 0


def _schedule_label(schedule: str, day: str, hour: int, minute: int) -> str:
    time_str = f"{hour:02d}:{minute:02d}"
    if schedule == "hourly":
        return "Every hour"
    elif schedule == "daily":
        return f"Daily at {time_str}"
    elif schedule == "weekly":
        day_names = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
                     "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
        return f"Every {day_names.get(day, day)} at {time_str}"
    return schedule


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
