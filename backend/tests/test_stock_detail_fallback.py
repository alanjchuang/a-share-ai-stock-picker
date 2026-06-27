import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.stock_service import StockService


class StockDetailFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        schema = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"
        self.conn.executescript(schema.read_text(encoding="utf-8"))
        self.conn.execute(
            """
            INSERT INTO stocks(ts_code, symbol, name, industry, market)
            VALUES ('300760.SZ', '300760', '迈瑞医疗', '医疗器械', '创业板')
            """
        )
        self.conn.execute("INSERT INTO index_info(index_code, name, category) VALUES ('399006.SZ', '创业板指', '宽基')")
        self.conn.execute(
            "INSERT INTO index_members(index_code, ts_code, weight, in_date) VALUES ('399006.SZ', '300760.SZ', 5, '20240101')"
        )
        self.conn.execute(
            """
            INSERT INTO stock_daily(ts_code, trade_date, open, high, low, close, pct_chg, vol, amount, turnover_rate, volume_ratio)
            VALUES ('300760.SZ', '20240627', 288, 296, 286, 292.5, 1.8, 10000, 3000000, 1.2, 1.1)
            """
        )
        self.conn.execute(
            """
            INSERT INTO fundamentals(ts_code, trade_date, pe_ttm, pb, roe, revenue_yoy, circ_mv)
            VALUES ('300760.SZ', '20240627', 32.5, 8.6, 24.1, 12.8, 3500)
            """
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_detail_falls_back_when_factor_cache_missing(self) -> None:
        service = StockService(self.conn)
        with patch("app.services.background_jobs.submit_factor_refresh_job", return_value={}), patch(
            "app.services.stock_service.StockNewsSearchService"
        ) as news_service:
            news_service.return_value.ensure_recent_news.return_value = ([], [])

            detail = service.detail("300760.SZ")

        self.assertEqual(detail.base.ts_code, "300760.SZ")
        self.assertEqual(detail.base.name, "迈瑞医疗")
        self.assertEqual(detail.base.close, 292.5)
        self.assertEqual(detail.base.pe_ttm, 32.5)
        self.assertEqual(detail.base.roe, 24.1)
        self.assertIn("创业板指", detail.base.index_names)
        self.assertTrue(any("暂未进入因子缓存" in warning for warning in detail.data_warnings))


if __name__ == "__main__":
    unittest.main()
