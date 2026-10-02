import unittest
from upload.metrics import estimate_chunks


class ChunkEstimateTests(unittest.TestCase):
    def test_boundaries_and_overlap(self):
        for tokens, count in [(0, 0), (1, 1), (512, 1), (513, 2), (960, 2), (961, 3)]:
            with self.subTest(tokens=tokens):
                self.assertEqual(estimate_chunks("word " * tokens), count)

    def test_unicode_whitespace_and_empty_text(self):
        self.assertEqual(estimate_chunks("  \t\n"), 0)
        self.assertEqual(estimate_chunks("one\ttwo\nthree", 2, 1), 2)

    def test_invalid_window_is_rejected(self):
        for maximum, overlap in [(0, 0), (512, -1), (64, 64), (64, 65)]:
            with self.assertRaises(ValueError):
                estimate_chunks("text", maximum, overlap)
