import unittest
from ranking import explicit_language_match


class LanguageGuardTests(unittest.TestCase):
    def test_cross_language_and_unrelated_books_are_excluded(self):
        for title in ('Python Programming for Machine Learning', 'The Processes of Life', 'Java Programming'):
            self.assertFalse(explicit_language_match({'title': title}, 'javascript'))

    def test_aliases_case_and_description_are_supported(self):
        for query in ('JavaScript', 'learn JS', 'modern ECMAScript'):
            self.assertTrue(explicit_language_match({'abstract': 'Examples in JavaScript.'}, query))
        self.assertTrue(explicit_language_match({'title': 'TypeScript Essentials'}, 'learn TS'))

    def test_broad_topics_and_word_boundaries(self):
        self.assertTrue(explicit_language_match({'title': 'Python'}, 'web programming'))
        self.assertFalse(explicit_language_match({'title': 'JavaScripted'}, 'javascript'))
        self.assertFalse(explicit_language_match({'title': 'JavaScript'}, 'TypeScript'))


if __name__ == '__main__':
    unittest.main()
