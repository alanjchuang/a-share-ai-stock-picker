import unittest

from app.models.schemas import StockScore
from app.services.recommendation_service import RecommendationService


class RecommendationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RecommendationService.__new__(RecommendationService)
        self.candidates = [
            StockScore(
                ts_code="600000.SH",
                symbol="600000",
                name="Test Bank",
                industry="Banking",
                rating="A",
                ai_score=82.4,
                sentiment_score=58,
            )
        ]

    def test_items_from_llm_accepts_chinese_confidence_label(self) -> None:
        items = self.service._items_from_llm(
            [
                {
                    "ts_code": "600000.SH",
                    "action": "watch",
                    "reason": "factor rank is strong",
                    "risk": "valuation needs review",
                    "confidence": "中",
                }
            ],
            self.candidates,
            limit=8,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].confidence, 65.0)
        self.assertEqual(items[0].source, "llm")

    def test_confidence_for_numeric_variants(self) -> None:
        self.assertEqual(self.service._confidence_for("88%", 50), 88.0)
        self.assertEqual(self.service._confidence_for(0.82, 50), 82.0)
        self.assertEqual(self.service._confidence_for("91.26", 50), 91.3)

    def test_confidence_for_unknown_value_falls_back_to_ai_score(self) -> None:
        self.assertEqual(self.service._confidence_for("unknown", 73.26), 73.3)
        self.assertEqual(self.service._confidence_for(None, 73.26), 73.3)


if __name__ == "__main__":
    unittest.main()
