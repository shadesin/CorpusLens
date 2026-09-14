import unittest
from pathlib import Path

from corpuslens.readers import infer_format


class ReaderTests(unittest.TestCase):
    def test_infers_format_beneath_gzip_suffix(self):
        self.assertEqual(infer_format(Path("corpus.jsonl.gz"), "auto"), "jsonl")
        self.assertEqual(infer_format(Path("corpus.ndjson.gz"), "auto"), "jsonl")
        self.assertEqual(infer_format(Path("corpus.txt.gz"), "auto"), "txt")

    def test_explicit_format_overrides_extension(self):
        self.assertEqual(infer_format(Path("corpus.txt.gz"), "jsonl"), "jsonl")


if __name__ == "__main__":
    unittest.main()
