import unittest
from unittest.mock import patch

from app.models.schemas import NewsAnalyzeRequest
from app.services.sentiment_service import SentimentService


class SentimentServiceTest(unittest.TestCase):
    def test_llm_analyze_accepts_label_score(self) -> None:
        service = SentimentService.__new__(SentimentService)
        request = NewsAnalyzeRequest(ts_code="600000.SH", title="订单增长", content="公司披露新增订单。")

        with patch("app.services.sentiment_service.load_settings") as load_settings, patch(
            "app.services.sentiment_service.LlmClient"
        ) as llm_client:
            load_settings.return_value.llm = object()
            llm_client.return_value.chat_json.return_value = {
                "score": "高",
                "keywords": ["订单"],
                "reason": "订单催化",
            }

            result = service._llm_analyze(request)

        self.assertEqual(result.score, 85.0)
        self.assertEqual(result.label, "重大利好")


if __name__ == "__main__":
    unittest.main()
