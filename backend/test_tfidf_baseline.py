import unittest

from tfidf_baseline import build_tfidf_index, rank_tfidf


class TfidfBaselineTests(unittest.TestCase):
    def setUp(self):
        self.books = [
            {"title": "Distributed Systems", "abstract": "Distributed consensus, replication, and fault tolerance."},
            {"title": "Organic Chemistry", "abstract": "Organic reactions, molecular structure, and synthesis."},
            {"title": "Web Development", "abstract": "JavaScript browser applications and web development."},
        ]
        self.index = build_tfidf_index(self.books)

    def test_build_returns_none_for_empty_catalogue(self):
        self.assertIsNone(build_tfidf_index([]))

    def test_topic_terms_rank_matching_abstract_first(self):
        ranked = rank_tfidf("distributed consensus systems", self.index)
        self.assertEqual(ranked[0][0], 0)
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_limit_and_blank_query(self):
        self.assertEqual(len(rank_tfidf("chemistry", self.index, limit=2)), 2)
        self.assertEqual(rank_tfidf("   ", self.index), [])


if __name__ == "__main__":
    unittest.main()
