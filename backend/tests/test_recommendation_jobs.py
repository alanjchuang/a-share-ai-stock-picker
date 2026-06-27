import os
import tempfile
import time
import unittest
from unittest.mock import patch

from app.models.schemas import OneClickRecommendRequest, OneClickRecommendResponse, StockRecommendationItem
from app.db.database import get_connection
from app.services.recommendation_jobs import get_one_click_recommendation_job, list_one_click_recommendation_jobs, submit_one_click_recommendation_job


class RecommendationJobsTest(unittest.TestCase):
    def test_one_click_recommendation_runs_in_background_and_stores_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.toml")
            db_path = os.path.join(tmpdir, "jobs.sqlite3")
            with open(config_path, "w", encoding="utf-8") as file:
                file.write(f'[database]\npath = "{db_path}"\n')

            response = OneClickRecommendResponse(
                market_view="market ok",
                strategy="factor strategy",
                risk_preference="balanced",
                recommendations=[
                    StockRecommendationItem(
                        ts_code="600000.SH",
                        name="Test Bank",
                        rating="A",
                        ai_score=82.4,
                        action="watch",
                        reason="good factors",
                        risk="valuation",
                        confidence=85.0,
                        source="llm",
                    )
                ],
            )

            with patch.dict(os.environ, {"A_STOCK_CONFIG": config_path}), patch(
                "app.services.recommendation_jobs.RecommendationService.readiness_errors",
                return_value=[],
            ), patch(
                "app.services.recommendation_jobs.RecommendationService.one_click",
                return_value=response,
            ):
                submit_result = submit_one_click_recommendation_job(OneClickRecommendRequest(limit=1, include_search=False))
                self.assertTrue(submit_result["accepted"])
                job_id = int(submit_result["job_id"])

                deadline = time.time() + 5
                job = None
                while time.time() < deadline:
                    job = get_one_click_recommendation_job(job_id)
                    if job and job["status"] in {"success", "failed"}:
                        break
                    time.sleep(0.05)

                jobs = list_one_click_recommendation_jobs(limit=5)

            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "success")
            self.assertEqual(job["result"]["recommendations"][0]["confidence"], 85.0)
            self.assertEqual(jobs[0]["id"], job_id)
            self.assertEqual(jobs[0]["result"]["recommendations"][0]["ts_code"], "600000.SH")

    def test_stale_running_jobs_are_expired_when_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.toml")
            db_path = os.path.join(tmpdir, "jobs.sqlite3")
            with open(config_path, "w", encoding="utf-8") as file:
                file.write(f'[database]\npath = "{db_path}"\n')

            with patch.dict(os.environ, {"A_STOCK_CONFIG": config_path}):
                conn = get_connection()
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT NOT NULL DEFAULT 'one_click_recommendation',
                        status TEXT NOT NULL,
                        message TEXT DEFAULT '',
                        request_json TEXT DEFAULT '',
                        result_json TEXT DEFAULT '',
                        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        finished_at TEXT
                    )
                    """
                )
                cursor = conn.execute(
                    """
                    INSERT INTO recommendation_jobs(job_type, status, message, started_at)
                    VALUES ('one_click_recommendation', 'running', 'old task', datetime('now', '-31 minutes'))
                    """
                )
                conn.commit()
                job_id = int(cursor.lastrowid)
                conn.close()

                job = get_one_click_recommendation_job(job_id)
                jobs = list_one_click_recommendation_jobs(limit=5)

            self.assertEqual(job["status"], "failed")
            self.assertIn("任务已中断", job["message"])
            self.assertEqual(jobs[0]["status"], "failed")
            self.assertTrue(jobs[0]["finished_at"])

    def test_missing_config_returns_blocked_without_failed_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.toml")
            db_path = os.path.join(tmpdir, "jobs.sqlite3")
            with open(config_path, "w", encoding="utf-8") as file:
                file.write(f'[database]\npath = "{db_path}"\n')

            with patch.dict(os.environ, {"A_STOCK_CONFIG": config_path}), patch(
                "app.services.recommendation_jobs.RecommendationService.readiness_errors",
                return_value=["LLM 未配置"],
            ):
                submit_result = submit_one_click_recommendation_job(OneClickRecommendRequest(limit=1, include_search=False))
                jobs = list_one_click_recommendation_jobs(limit=5)

            self.assertFalse(submit_result["accepted"])
            self.assertEqual(submit_result["status"], "blocked")
            self.assertIn("LLM 未配置", submit_result["message"])
            self.assertEqual(jobs, [])

    def test_legacy_readiness_failure_is_reported_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.toml")
            db_path = os.path.join(tmpdir, "jobs.sqlite3")
            with open(config_path, "w", encoding="utf-8") as file:
                file.write(f'[database]\npath = "{db_path}"\n')

            with patch.dict(os.environ, {"A_STOCK_CONFIG": config_path}):
                conn = get_connection()
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendation_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT NOT NULL DEFAULT 'one_click_recommendation',
                        status TEXT NOT NULL,
                        message TEXT DEFAULT '',
                        request_json TEXT DEFAULT '',
                        result_json TEXT DEFAULT '',
                        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        finished_at TEXT
                    )
                    """
                )
                cursor = conn.execute(
                    """
                    INSERT INTO recommendation_jobs(job_type, status, message)
                    VALUES ('one_click_recommendation', 'failed', '一键荐股需要先完成配置：LLM 未配置')
                    """
                )
                conn.commit()
                job_id = int(cursor.lastrowid)
                conn.close()

                job = get_one_click_recommendation_job(job_id)
                jobs = list_one_click_recommendation_jobs(limit=5)

            self.assertEqual(job["status"], "blocked")
            self.assertEqual(jobs[0]["status"], "blocked")
            self.assertIn("LLM 未配置", jobs[0]["message"])


if __name__ == "__main__":
    unittest.main()
