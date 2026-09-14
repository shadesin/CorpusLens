import json
import tempfile
import unittest
from pathlib import Path

from corpuslens.models import Policy
from corpuslens.pipeline import run_pipeline
from corpuslens.profiles import get_profile


class PipelineTests(unittest.TestCase):
    def test_clean_reconciles_and_explains_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.txt"
            source.write_text(
                "এটি একটি স্বাভাবিক বাংলা বাক্য।\n"
                "এটি একটি স্বাভাবিক বাংলা বাক্য।\n"
                "!!!!!!!!!!!!!!! repeated !!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                "যোগাযোগ test@example.com অথবা ০১৭১২৩৪৫৬৭৮ নম্বরে।\n",
                encoding="utf-8",
            )
            output = root / "out"
            result = run_pipeline(source, output, "clean", "txt", "text", get_profile("bn"), Policy(profile="bn"))
            self.assertEqual(result.records_read, 4)
            self.assertEqual(result.records_read, result.records_kept + result.records_rejected)
            self.assertTrue(result.reconciliation_ok)
            self.assertEqual(result.findings_by_code["exact_duplicate"], 1)
            self.assertIn("<EMAIL>", (output / "cleaned.txt").read_text(encoding="utf-8"))
            rejects = [json.loads(line) for line in (output / "rejected.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(any(item["code"] == "exact_duplicate" for item in row["findings"]) for row in rejects))
            self.assertTrue((output / "report.html").is_file())
            self.assertTrue((output / "resolved-policy.json").is_file())

    def test_invalid_jsonl_is_rejected_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            source.write_text('{"text": "valid enough text"}\nnot json\n', encoding="utf-8")
            result = run_pipeline(source, root / "out", "analyze", "jsonl", "text", get_profile("generic"), Policy())
            self.assertEqual(result.records_read, 2)
            self.assertEqual(result.records_rejected, 1)
            self.assertEqual(result.findings_by_code["malformed_record"], 1)
            self.assertTrue(result.reconciliation_ok)

    def test_jsonl_cleaning_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            source.write_text('{"id": 7, "content": "  useful   text  "}\n', encoding="utf-8")
            output = root / "out"
            run_pipeline(source, output, "clean", "jsonl", "content", get_profile("generic"), Policy())
            cleaned = json.loads((output / "cleaned.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(cleaned, {"id": 7, "content": "useful text"})


if __name__ == "__main__":
    unittest.main()
