import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.background_jobs import _stock_detail_refresh_task


class StockDetailRefreshFactorsTest(unittest.TestCase):
    def test_rebuilds_all_factors_after_global_cache_clear(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        schema = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"
        conn.executescript(schema.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO sync_jobs(id, job_type, status, message) VALUES (1, 'stock_detail_refresh', 'running', '')")
        conn.execute("INSERT INTO stocks(ts_code, symbol, name) VALUES ('300760.SZ', '300760', '迈瑞医疗')")
        conn.commit()

        try:
            with (
                patch("app.services.background_jobs._update_job"),
                patch("app.services.background_jobs.AkshareService") as akshare,
                patch("app.services.background_jobs.StockNewsSearchService") as search,
                patch("app.services.background_jobs.SentimentService") as sentiment,
                patch("app.services.background_jobs.DataQualityService") as quality,
                patch("app.services.background_jobs.FactorEngine") as factor_engine,
            ):
                akshare.return_value.sync_stock_detail.return_value = {"ts_code": "300760.SZ", "tables": {}}
                search.return_value.refresh_from_search.return_value = 0
                sentiment.return_value.refresh_stock_news.return_value = {"updated": 0}
                quality.return_value.clean_mixed_demo_rows.return_value = {"factor_cache_cleared": True}
                factor_engine.return_value.calculate_all.return_value = [
                    {"ts_code": "300760.SZ", "ai_score": 61.2, "rating": "C"},
                    {"ts_code": "600000.SH", "ai_score": 58.0, "rating": "C"},
                ]

                result = _stock_detail_refresh_task("300760.SZ")(conn, 1)

            factor_engine.return_value.calculate_all.assert_called_once()
            factor_engine.return_value.calculate_one.assert_not_called()
            self.assertEqual(result["factor"]["ts_code"], "300760.SZ")
            self.assertEqual(result["factor"]["ai_score"], 61.2)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
