import sqlite3
import unittest

from app.services.stock_news_search_service import StockNewsSearchService


class DummySearch:
    def __init__(self, available: bool) -> None:
        self.available = available


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE stock_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_code TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT,
            publish_time TEXT NOT NULL,
            sentiment_score REAL DEFAULT 50,
            sentiment_label TEXT DEFAULT '中性',
            keywords TEXT DEFAULT ''
        )
        """
    )
    return conn


def insert_news(conn: sqlite3.Connection, source: str) -> None:
    conn.execute(
        """
        INSERT INTO stock_news(ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
        VALUES ('000001.SZ', '演示新闻', '演示内容', ?, datetime('now'), 50, '中性', '')
        """,
        (source,),
    )
    conn.commit()


class StockNewsSearchServiceTest(unittest.TestCase):
    def test_unconfigured_search_does_not_return_demo_news(self) -> None:
        conn = make_conn()
        self.addCleanup(conn.close)
        insert_news(conn, "demo")
        service = StockNewsSearchService(conn)
        service.search = DummySearch(False)

        rows, warnings = service.ensure_recent_news("000001.SZ", "平安银行", days=15)

        self.assertEqual(rows, [])
        self.assertTrue(any("火山搜索未配置" in item for item in warnings))

    def test_locked_cache_write_returns_search_rows_in_memory(self) -> None:
        conn = make_conn()
        self.addCleanup(conn.close)
        insert_news(conn, "demo")
        service = StockNewsSearchService(conn)
        service.search = DummySearch(True)
        searched_rows = [
            {
                "id": -1,
                "ts_code": "000001.SZ",
                "title": "平安银行公告新闻",
                "content": "平安银行近期公告摘要",
                "source": "volc-search/测试站点",
                "publish_time": "2026-06-27 10:00:00",
                "sentiment_score": 50,
                "sentiment_label": "中性",
                "keywords": "",
            }
        ]
        service.search_latest = lambda *_args, **_kwargs: searched_rows

        def locked_persist(*_args: object, **_kwargs: object) -> int:
            raise sqlite3.OperationalError("database is locked")

        service.persist_news = locked_persist

        rows, warnings = service.ensure_recent_news("000001.SZ", "平安银行", days=15)

        self.assertEqual(rows, searched_rows)
        self.assertTrue(any("暂未缓存" in item for item in warnings))

    def test_stock_matching_accepts_name_or_symbol(self) -> None:
        self.assertTrue(StockNewsSearchService._matches_stock("平安银行发布公告", "平安银行", "000001"))
        self.assertTrue(StockNewsSearchService._matches_stock("000001 半年度业绩", "平安银行", "000001"))
        self.assertFalse(StockNewsSearchService._matches_stock("招商银行发布公告", "平安银行", "000001"))


if __name__ == "__main__":
    unittest.main()
