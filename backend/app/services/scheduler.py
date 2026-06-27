from __future__ import annotations

import sqlite3

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import load_settings
from app.db.database import get_connection
from app.models.schemas import SyncRequest
from app.services.factor_engine import FactorEngine
from app.services.market_data_service import MarketDataService
from app.services.sentiment_service import SentimentService


scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def daily_sync_job() -> None:
    conn: sqlite3.Connection | None = None
    try:
        conn = get_connection()
        conn.execute("INSERT INTO sync_jobs(job_type, status, message) VALUES ('daily_sync', 'running', '')")
        MarketDataService(conn).sync(SyncRequest())
        SentimentService(conn).batch_refresh_existing(limit=300)
        FactorEngine(conn).calculate_all(force=True)
        conn.execute(
            """
            UPDATE sync_jobs
            SET status='success', message='同步完成', finished_at=CURRENT_TIMESTAMP
            WHERE id=(SELECT MAX(id) FROM sync_jobs WHERE job_type='daily_sync')
            """
        )
        conn.commit()
    except Exception as exc:
        if conn:
            conn.execute(
                """
                UPDATE sync_jobs
                SET status='failed', message=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=(SELECT MAX(id) FROM sync_jobs WHERE job_type='daily_sync')
                """,
                (str(exc),),
            )
            conn.commit()
    finally:
        if conn:
            conn.close()


def start_scheduler() -> None:
    settings = load_settings()
    if not settings.scheduler.enabled or scheduler.running:
        return
    try:
        trigger = CronTrigger.from_crontab(settings.scheduler.daily_sync_cron, timezone="Asia/Shanghai")
    except ValueError:
        trigger = CronTrigger(hour=18, minute=30, day_of_week="mon-fri", timezone="Asia/Shanghai")
    scheduler.add_job(daily_sync_job, trigger=trigger, id="daily_sync", replace_existing=True, max_instances=1)
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
