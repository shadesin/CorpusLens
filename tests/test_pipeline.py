import json
import tempfile
import unittest
from pathlib import Path

from corpuslens.models import Policy
from corpuslens.pipeline import LengthSketch, run_pipeline
from corpuslens.profiles import get_profile


class PipelineTests(unittest.TestCase):
    def test_length_sketch_is_bounded_and_reproducible(self):
        first = LengthSketch(limit=10)
        second = LengthSketch(limit=10)
        for value in range(1000):
            first.add(value)
            second.add(value)
        self.assertEqual(first.count, 1000)
        self.assertEqual(len(first.values), 10)
        self.assertEqual(first.values, second.values)
        self.assertNotEqual(first.values, list(range(10)))

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
            self.assertIn("0.20", result.script_threshold_preview)
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

    def test_optional_near_deduplication_rejects_verified_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.txt"
            source.write_text(
                "the quick brown fox jumps over the lazy dog today\n"
                "the quick brown fox jumps over the lazy dog today!\n"
                "corpus auditing explains every rejected record clearly\n",
                encoding="utf-8",
            )
            result = run_pipeline(
                source,
                root / "out",
                "analyze",
                "txt",
                "text",
                get_profile("generic"),
                Policy(near_dedup=True),
            )
            self.assertEqual(result.findings_by_code["near_duplicate"], 1)
            self.assertEqual(result.records_kept, 2)
            self.assertEqual(result.records_rejected, 1)
            self.assertGreaterEqual(result.deduplication_statistics["near_candidate_comparisons"], 1)

    def test_rejected_record_does_not_pollute_near_duplicate_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            words = "one two three four five six seven eight nine ten"
            source = root / "input.txt"
            source.write_text(("!" * 80) + words + "\n" + words + "\n", encoding="utf-8")
            result = run_pipeline(
                source,
                root / "out",
                "analyze",
                "txt",
                "text",
                get_profile("generic"),
                Policy(near_dedup=True),
            )
            self.assertEqual(result.records_rejected, 1)
            self.assertEqual(result.records_kept, 1)
            self.assertNotIn("near_duplicate", result.findings_by_code)


if __name__ == "__main__":
    unittest.main()
