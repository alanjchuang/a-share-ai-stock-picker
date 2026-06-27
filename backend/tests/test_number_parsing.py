import unittest

from app.utils.number_parsing import coerce_score


class NumberParsingTest(unittest.TestCase):
    def test_coerce_score_handles_labels_and_text(self) -> None:
        self.assertEqual(coerce_score("高"), 85.0)
        self.assertEqual(coerce_score("高置信度"), 85.0)
        self.assertEqual(coerce_score("中等"), 65.0)
        self.assertEqual(coerce_score("低"), 40.0)

    def test_coerce_score_handles_percent_and_unit_interval(self) -> None:
        self.assertEqual(coerce_score("88%"), 88.0)
        self.assertEqual(coerce_score("91.26分"), 91.3)
        self.assertEqual(coerce_score(0.82), 82.0)

    def test_coerce_score_uses_default_for_unknown_text(self) -> None:
        self.assertEqual(coerce_score("无法判断", default=73.26), 73.3)


if __name__ == "__main__":
    unittest.main()
