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

    def test_indic_profiles_recognize_their_scripts(self):
        samples = {
            "bn": "এটি একটি বাংলা বাক্য",
            "gu": "આ ગુજરાતી લખાણ છે",
            "hi": "यह हिन्दी वाक्य है",
            "kn": "ಇದು ಕನ್ನಡ ಪಠ್ಯವಾಗಿದೆ",
            "ml": "ഇത് മലയാളം വാചകമാണ്",
            "mr": "हे मराठी वाक्य आहे",
            "or": "ଏହା ଓଡ଼ିଆ ବାକ୍ୟ",
            "pa": "ਇਹ ਪੰਜਾਬੀ ਵਾਕ ਹੈ",
            "ta": "இது தமிழ் வாக்கியம்",
            "te": "ఇది తెలుగు వాక్యం",
            "ur": "یہ اردو جملہ ہے",
            "as": "এইটো এটা অসমীয়া বাক্য",
            "bho": "ई भोजपुरी वाक्य बा",
            "brx": "बेयो बर राव",
            "doi": "एह् डोगरी वाक्य ऐ",
            "kok": "हें कोंकणी वाक्य आसा",
            "mai": "ई मैथिली वाक्य अछि",
            "mni": "ꯃꯤꯇꯩ ꯂꯣꯟ",
            "lus": "Hei hi Mizo tawng a ni",
            "ne": "यो नेपाली वाक्य हो",
            "sd": "هي سنڌي جملو آهي",
        }
        for key, text in samples.items():
            with self.subTest(profile=key):
                self.assertGreater(target_script_ratio(text, get_profile(key)), 0.80)

    def test_unexpected_script_is_flagged_separately(self):
        findings, _, _ = inspect_text(
            "यह पूरा वाक्य देवनागरी में है",
            get_profile("bn"),
            Policy(profile="bn", min_script_ratio=0.20),
        )
        codes = {finding.code for finding in findings}
        self.assertIn("low_target_script_ratio", codes)
        self.assertIn("unexpected_script_ratio", codes)


if __name__ == "__main__":
    unittest.main()
