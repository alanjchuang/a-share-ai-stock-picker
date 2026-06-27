import os
import tempfile
import time
import unittest
from unittest.mock import patch

from app.models.schemas import OneClickRecommendRequest, OneClickRecommendResponse, StockRecommendationItem
from app.services.recommendation_jobs import get_one_click_recommendation_job, submit_one_click_recommendation_job


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

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "success")
        self.assertEqual(job["result"]["recommendations"][0]["confidence"], 85.0)


if __name__ == "__main__":
    unittest.main()
