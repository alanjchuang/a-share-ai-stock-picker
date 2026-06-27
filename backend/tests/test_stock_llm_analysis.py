import unittest
from unittest.mock import patch

from app.models.schemas import StockDetail, StockScore
from app.services.stock_service import StockService


class DummySettings:
    llm = object()


def make_detail() -> StockDetail:
    base = StockScore(
        ts_code="600000.SH",
        symbol="600000",
        name="测试银行",
        industry="银行",
        rating="A",
        ai_score=82.4,
        fundamental_score=78,
        technical_score=70,
        capital_score=68,
        sentiment_factor_score=72,
        sentiment_score=66,
        sentiment_label="普通利好",
        pe_ttm=8.5,
        pb=0.8,
        roe=12.3,
    )
    return StockDetail(
        base=base,
        kline=[],
        financial_history=[],
        news=[],
        radar={"价值": 78, "成长": 12.3, "资金": 68, "舆情": 72},
        rating=base.rating,
        data_warnings=[],
    )


class StockLlmAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StockService.__new__(StockService)
        self.detail = make_detail()
        self.service.detail = lambda ts_code: self.detail

    def test_llm_analysis_uses_llm_json_when_available(self) -> None:
        with patch("app.services.stock_service.load_settings", return_value=DummySettings()), patch(
            "app.services.stock_service.LlmClient"
        ) as llm_client:
            llm = llm_client.return_value
            llm.available = True
            llm.chat_json.return_value = {
                "summary": "评分靠前但需要持续跟踪估值与资金。",
                "key_points": ["AI评分靠前", "舆情偏正面"],
                "risks": "估值波动\n行业政策变化",
                "watch_items": ["资金流", "财报"],
                "questions": ["核心逻辑是否仍成立？"],
            }

            response = self.service.llm_analysis("600000.SH")

        self.assertEqual(response.source, "llm")
        self.assertEqual(response.ts_code, "600000.SH")
        self.assertEqual(response.key_points, ["AI评分靠前", "舆情偏正面"])
        self.assertEqual(response.risks, ["估值波动", "行业政策变化"])

    def test_llm_analysis_falls_back_when_llm_unavailable(self) -> None:
        with patch("app.services.stock_service.load_settings", return_value=DummySettings()), patch(
            "app.services.stock_service.LlmClient"
        ) as llm_client:
            llm = llm_client.return_value
            llm.available = False

            response = self.service.llm_analysis("600000.SH")

        self.assertEqual(response.source, "fallback")
        self.assertIn("LLM未配置", " ".join(response.risks))
        self.assertTrue(response.key_points)

    def test_llm_analysis_falls_back_when_llm_raises(self) -> None:
        with patch("app.services.stock_service.load_settings", return_value=DummySettings()), patch(
            "app.services.stock_service.LlmClient"
        ) as llm_client:
            llm = llm_client.return_value
            llm.available = True
            llm.chat_json.side_effect = RuntimeError("bad json")

            response = self.service.llm_analysis("600000.SH")

        self.assertEqual(response.source, "fallback")
        self.assertIn("bad json", " ".join(response.risks))


if __name__ == "__main__":
    unittest.main()
