import sqlite3
import unittest
from pathlib import Path

import pandas as pd

from app.services.akshare_service import AkshareService
from app.utils.data_quality import sanitize_daily_frame


class DummyAkshareSettings:
    adjust = "qfq"


class DummySettings:
    akshare = DummyAkshareSettings()


class MarketDataQualityTest(unittest.TestCase):
    def test_sanitize_daily_frame_removes_short_unadjusted_tail(self) -> None:
        frame = pd.DataFrame(
            [
                {"ts_code": "300760.SZ", "trade_date": "20260624", "close": 102.47, "pre_close": 102.73, "pct_chg": -0.25, "amount": 2479355.7},
                {"ts_code": "300760.SZ", "trade_date": "20260625", "close": 103.57, "pre_close": 102.47, "pct_chg": 1.08, "amount": 2344567.0},
                {"ts_code": "300760.SZ", "trade_date": "20260626", "close": 133.98, "pre_close": 138.16, "pct_chg": -3.03, "amount": 1447654322.04},
            ]
        )

        result = sanitize_daily_frame(frame)

        self.assertEqual(result.removed_trade_dates, ["20260626"])
        self.assertEqual(result.frame["trade_date"].tolist(), ["20260624", "20260625"])

    def test_adjusted_history_rejects_unadjusted_spot_snapshot(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        schema = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"
        conn.executescript(schema.read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO stock_daily(ts_code, trade_date, close, pre_close, pct_chg)
            VALUES ('300760.SZ', '20260625', 103.57, 102.47, 1.08)
            """
        )
        service = AkshareService.__new__(AkshareService)
        service.conn = conn
        service.settings = DummySettings()

        try:
            self.assertFalse(service._spot_daily_matches_history_scale("300760.SZ", "20260626", 138.16))
            self.assertTrue(service._spot_daily_matches_history_scale("300760.SZ", "20260626", 103.57))
            self.assertTrue(service._spot_daily_matches_history_scale("300760.SZ", "20260720", 138.16))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
