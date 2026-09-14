import tempfile
import unittest
from pathlib import Path

from corpuslens.dedup import NearDeduplicator, jaccard, shingle_hashes, word_tokens


class NearDeduplicationTests(unittest.TestCase):
    def test_unicode_tokenizer_ignores_punctuation_not_script(self):
        self.assertEqual(word_tokens("বাংলা, नेपाली! தமிழ்?"), ["বাংলা", "नेपाली", "தமிழ்"])

    def test_jaccard_is_exact_over_shingles(self):
        first = shingle_hashes("one two three four five", 3)
        second = shingle_hashes("one two three four six", 3)
        self.assertAlmostEqual(jaccard(first, second), 0.5)

    def test_lsh_candidates_are_verified_before_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            deduplicator = NearDeduplicator(Path(directory) / "near.sqlite3", threshold=0.85)
            try:
                first = "the quick brown fox jumps over the lazy dog today"
                same_words = "the quick brown fox jumps over the lazy dog today!"
                unrelated = "corpus auditing explains why every rejected record disappeared"
                self.assertIsNone(deduplicator.observe(first, 1))
                match = deduplicator.observe(same_words, 2)
                self.assertIsNotNone(match)
                self.assertEqual(match.first_record, 1)
                self.assertEqual(match.similarity, 1.0)
                self.assertEqual(deduplicator.matches_found, 1)
                self.assertIsNone(deduplicator.observe(unrelated, 3))
                self.assertEqual(deduplicator.documents_indexed, 2)
            finally:
                deduplicator.close()


if __name__ == "__main__":
    unittest.main()
