import unittest

from corpuslens.detectors import inspect_text, normalize_text, script_counts, symbol_ratio, target_script_ratio
from corpuslens.models import Policy
from corpuslens.profiles import get_profile


class DetectorTests(unittest.TestCase):
    def test_bengali_vowel_signs_are_not_symbols(self):
        # Regression for a real pipeline bug: combining vowel signs are marks,
        # not punctuation/symbol junk.
        self.assertLess(symbol_ratio("আমি বাংলায় কথা বলি।"), 0.20)

    def test_script_ratio_is_not_language_identification(self):
        ratio = target_script_ratio("বাংলায় machine learning", get_profile("bn"))
        self.assertIsNotNone(ratio)
        self.assertGreater(ratio, 0)
        self.assertLess(ratio, 1)

    def test_collects_multiple_findings(self):
        text = "�" + ("!" * 60)
        findings, _, _ = inspect_text(text, get_profile("generic"), Policy())
        codes = {finding.code for finding in findings}
        self.assertIn("broken_encoding", codes)
        self.assertIn("high_symbol_ratio", codes)
        self.assertIn("character_spam", codes)

    def test_normalization_is_nfc_and_collapses_whitespace(self):
        self.assertEqual(normalize_text("Cafe\u0301   text\n"), "Café text")

    def test_generic_profile_reports_non_latin_scripts(self):
        self.assertGreater(script_counts("தமிழ்")["Tamil"], 0)


if __name__ == "__main__":
    unittest.main()
