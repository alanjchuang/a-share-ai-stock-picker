import unittest

from app.models.schemas import RangeFilter, ScreeningRequest, SentimentConditions
from app.services.screener_service import ScreenerService


class ScreenerServiceCoercionTest(unittest.TestCase):
    def test_to_stock_score_accepts_textual_score_labels(self) -> None:
        stock = ScreenerService._to_stock_score(
            {
                "ts_code": "600000.SH",
                "name": "测试银行",
                "close": "高",
                "sentiment_score": "高",
                "fundamental_score": "中高",
                "technical_score": "中",
                "capital_score": "低",
                "sentiment_factor_score": "较高",
                "ai_score": "高置信度",
            }
        )

        self.assertIsNone(stock.close)
        self.assertEqual(stock.sentiment_score, 85.0)
        self.assertEqual(stock.fundamental_score, 75.0)
        self.assertEqual(stock.technical_score, 65.0)
        self.assertEqual(stock.capital_score, 40.0)
        self.assertEqual(stock.sentiment_factor_score, 80.0)
        self.assertEqual(stock.ai_score, 85.0)

    def test_sentiment_condition_accepts_textual_score_labels(self) -> None:
        service = ScreenerService.__new__(ScreenerService)
        request = ScreeningRequest(sentiment=SentimentConditions(min_avg_score=80))
        condition = service._sentiment_condition(request)

        self.assertIsNotNone(condition)
        self.assertTrue(condition({"sentiment_score": "高"}))
        self.assertFalse(condition({"sentiment_score": "低"}))

    def test_range_checks_do_not_raise_on_textual_values(self) -> None:
        self.assertFalse(ScreenerService._in_range("高", RangeFilter(min=5, max=20)))


if __name__ == "__main__":
    unittest.main()
