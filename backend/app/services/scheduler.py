from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import load_settings
from app.services.background_jobs import run_scheduled_factor_cache_job, run_scheduled_sync_job


scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def daily_sync_job() -> None:
    run_scheduled_sync_job()


def factor_cache_refresh_job() -> None:
    run_scheduled_factor_cache_job()


def start_scheduler() -> None:
    settings = load_settings()
    if not settings.scheduler.enabled or scheduler.running:
        return
    try:
        trigger = CronTrigger.from_crontab(settings.scheduler.daily_sync_cron, timezone="Asia/Shanghai")
    except ValueError:
        trigger = CronTrigger(hour=18, minute=30, day_of_week="mon-fri", timezone="Asia/Shanghai")
    scheduler.add_job(daily_sync_job, trigger=trigger, id="daily_sync", replace_existing=True, max_instances=1)
    if settings.scheduler.factor_cache_refresh_minutes > 0:
        scheduler.add_job(
            factor_cache_refresh_job,
            trigger=IntervalTrigger(minutes=max(1, settings.scheduler.factor_cache_refresh_minutes), timezone="Asia/Shanghai"),
            id="factor_cache_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
