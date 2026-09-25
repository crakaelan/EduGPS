import unittest

import torch

import ingestion
from ranking import infer_book_profile, select_candidate, stage_metadata_score, title_family, title_family_exclusions


class IngestionStabilityTests(unittest.TestCase):
    def test_clean_text_removes_html_and_extra_space(self):
        self.assertEqual(ingestion.clean_text('<p>Hello   world</p>'), 'Hello world')

    def test_edition_identity_ignores_title_punctuation(self):
        first = (
            ingestion.normalise_identity('Clean Code'),
            tuple(sorted([ingestion.normalise_identity('A. Author')]))
        )
        second = (
            ingestion.normalise_identity('Clean-Code'),
            tuple(sorted([ingestion.normalise_identity('A Author')]))
        )
        self.assertEqual(first, second)

    def test_catalogue_merge_preserves_existing_and_adds_new_books(self):
        existing = [{
            'title': 'Python Basics', 'authors': ['A. Author'],
            'isbn': '111', 'abstract': 'Existing description', 'topics': ['Python']
        }]
        incoming = [{
            'title': 'Distributed Systems', 'authors': ['B. Author'],
            'isbn': '222', 'abstract': 'New description'
        }]
        merged, added = ingestion.merge_catalogues(existing, incoming, 'distributed systems')
        self.assertEqual(added, 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]['topics'], ['distributed systems'])

    def test_catalogue_merge_deduplicates_and_enriches_topic_attribution(self):
        existing = [{
            'title': 'Clean Code', 'authors': ['Robert Martin'],
            'isbn': '978-1', 'abstract': 'Existing description', 'topics': ['programming']
        }]
        incoming = [{
            'title': 'Clean Code: A Handbook', 'authors': ['Robert Martin'],
            'isbn': '9781', 'abstract': 'Duplicate description'
        }]
        merged, added = ingestion.merge_catalogues(existing, incoming, 'software engineering')
        self.assertEqual(added, 0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['topics'], ['programming', 'software engineering'])


class RankingStabilityTests(unittest.TestCase):
    def setUp(self):
        self.embeddings = torch.eye(6)
        self.topic_scores = torch.tensor([1.0, .9, .8, .7, .6, .5])

    def test_four_distinct_route_books_can_be_selected(self):
        selected = [0]
        for _ in range(4):
            choice, _ = select_candidate(
                self.topic_scores, self.topic_scores, self.embeddings,
                selected, range(6)
            )
            self.assertIsNotNone(choice)
            selected.append(choice)
        self.assertEqual(len(set(selected)), 5)

    def test_beginner_practical_profile_is_explainable(self):
        profile = infer_book_profile({
            "title": "Python for Complete Beginners",
            "abstract": "A hands-on introduction with practical projects and exercises.",
        })
        self.assertEqual(profile["estimated_level"], "Introductory")
        self.assertEqual(profile["content_orientation"], "Practice-focused")

    def test_advanced_theory_profile_is_explainable(self):
        profile = infer_book_profile({
            "title": "Advanced Systems Theory",
            "abstract": "A graduate reference covering principles, concepts, and theoretical models.",
        })
        self.assertEqual(profile["estimated_level"], "Advanced")
        self.assertEqual(profile["content_orientation"], "Theory-focused")

    def test_exhausted_pool_returns_none(self):
        choice, components = select_candidate(
            self.topic_scores, self.topic_scores, self.embeddings,
            [0, 1], [0, 1]
        )
        self.assertIsNone(choice)
        self.assertIsNone(components)

    def test_excluded_candidate_is_never_returned(self):
        choice, _ = select_candidate(
            self.topic_scores, self.topic_scores, self.embeddings,
            [0], range(6), excluded_indices=[1]
        )
        self.assertNotEqual(choice, 1)

    def test_title_family_ignores_subtitle_and_edition(self):
        self.assertEqual(
            title_family('Quantum Physics: A Beginner Guide, Second Edition'),
            title_family('Quantum Physics')
        )

    def test_selected_title_family_is_excluded(self):
        books = [
            {'title': 'Business Strategy'},
            {'title': 'Business Strategy: Third Edition'},
            {'title': 'Competitive Advantage'},
        ]
        self.assertEqual(title_family_exclusions(books, [0]), {0, 1})

    def test_beginner_book_is_stronger_foundation_than_deeper_study(self):
        book = {'title': 'Python for Complete Beginners', 'abstract': 'An introduction to programming basics.'}
        self.assertGreater(
            stage_metadata_score(book, 'Foundation'),
            stage_metadata_score(book, 'Deeper study')
        )

    def test_project_book_is_strong_applied_practice(self):
        book = {'title': 'Practical Python Projects', 'abstract': 'Hands-on exercises and implementation examples.'}
        self.assertGreaterEqual(stage_metadata_score(book, 'Applied practice'), 0.8)

    def test_advanced_reference_is_stronger_deeper_study(self):
        book = {'title': 'Advanced Systems Handbook', 'abstract': 'An in-depth specialist reference.'}
        self.assertGreater(
            stage_metadata_score(book, 'Deeper study'),
            stage_metadata_score(book, 'Foundation')
        )


if __name__ == '__main__':
    unittest.main()
