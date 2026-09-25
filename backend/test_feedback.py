import unittest
from pathlib import Path
from uuid import uuid4

import torch

from feedback import FeedbackStore, MAX_SCORE_ADJUSTMENT, calibrated_scores, normalize_query


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.feedback_path = Path(__file__).parent / f".test_feedback_{uuid4().hex}.json"
        self.store = FeedbackStore(self.feedback_path)

    def tearDown(self):
        self.feedback_path.unlink(missing_ok=True)

    def test_query_normalization(self):
        self.assertEqual(normalize_query("  Quantum   Physics "), "quantum physics")

    def test_repeat_vote_is_idempotent_and_switch_replaces_it(self):
        self.store.record("JavaScript", "123", 1)
        self.store.record(" javascript ", "123", 1)
        self.assertEqual(self.store.votes_for_query("JAVASCRIPT"), {"123": 1})
        self.store.record("javascript", "123", -1)
        self.assertEqual(self.store.votes_for_query("javascript"), {"123": -1})

    def test_zero_vote_removes_existing_preference(self):
        self.store.record("javascript", "123", 1)
        self.store.record("javascript", "123", 0)
        self.assertEqual(self.store.votes_for_query("javascript"), {})

    def test_calibration_is_bounded_and_query_specific(self):
        books = [{"isbn": "liked"}, {"isbn": "neutral"}]
        scores = torch.tensor([0.50, 0.51])
        self.store.record("astronomy", "liked", 1)
        adjusted, votes = calibrated_scores(scores, books, "astronomy", self.store)
        self.assertAlmostEqual(float(adjusted[0]), 0.50 + MAX_SCORE_ADJUSTMENT, places=6)
        self.assertAlmostEqual(float(adjusted[1]), 0.51, places=6)
        self.assertEqual(votes, {"liked": 1})
        other, _ = calibrated_scores(scores, books, "chemistry", self.store)
        self.assertTrue(torch.equal(other, scores))

    def test_invalid_vote_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.record("astronomy", "123", 2)


if __name__ == "__main__":
    unittest.main()
