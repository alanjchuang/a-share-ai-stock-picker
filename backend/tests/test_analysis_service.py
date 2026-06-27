import unittest

from app.services.analysis_service import AnalysisService


class AnalysisServiceCoercionTest(unittest.TestCase):
    def test_nan_status_flags_are_treated_as_false(self) -> None:
        self.assertFalse(AnalysisService._flag(float("nan")))
        self.assertFalse(AnalysisService._flag(None))
        self.assertTrue(AnalysisService._flag(1))

    def test_numeric_helpers_do_not_return_nan(self) -> None:
        self.assertEqual(AnalysisService._num(float("nan")), 0)
        self.assertIsNone(AnalysisService._optional_float(float("nan")))


if __name__ == "__main__":
    unittest.main()
