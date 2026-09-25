"""Controlled API tests: synthetic vectors test behaviour, not retrieval quality."""
import importlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import torch
from fastapi.testclient import TestClient
from feedback import FeedbackStore
from ranking import candidate_evidence, learner_adjustment, infer_book_profile


class FakeEncoder:
    def encode(self, text, **kwargs):
        return torch.tensor([[1., 0.]] * len(text)) if isinstance(text, list) else torch.tensor([1., 0.])


class QualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('sentence_transformers.SentenceTransformer', return_value=FakeEncoder()):
            cls.api = importlib.import_module('main')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        filler = ' This book explains the subject with detailed examples and discussion for readers who want to study the material in context.'
        self.books = [
            {'isbn': '0', 'title': 'Starting Book', 'abstract': 'Introduction basics beginners.' + filler},
            {'isbn': '1', 'title': 'Conceptual Treatment', 'abstract': 'Core concepts theory principles.' + filler},
            {'isbn': '2', 'title': 'Workshop', 'abstract': 'Practical projects exercises implementation.' + filler},
            {'isbn': '3', 'title': 'Specialist Study', 'abstract': 'Advanced graduate research reference.' + filler},
            {'isbn': '4', 'title': 'Sparse Book', 'abstract': 'Too short'},
        ]
        for name, value in {
            'books': self.books, 'embeddings': torch.tensor([[1., 0.]] * 5),
            'model': FakeEncoder(), 'feedback_store': FeedbackStore(Path(self.temp.name)/'feedback.json'),
            'BASE_DIR': Path(self.temp.name), 'tfidf_index': self.api.build_tfidf_index(self.books)
        }.items():
            p=patch.object(self.api,name,value); p.start(); self.addCleanup(p.stop)
        self.client=TestClient(self.api.app)

    def test_search_does_not_ingest_and_filters_sparse_books(self):
        with patch.object(self.api.subprocess,'run') as run:
            data=self.client.get('/search',params={'query':'subject'}).json()
        run.assert_not_called()
        self.assertEqual(len(data['recommendations']),4)
        self.assertNotIn('4',[b['isbn'] for b in data['recommendations']])

    def test_empty_query_and_invalid_preferences_are_rejected(self):
        self.assertEqual(self.client.get('/search',params={'query':'  '}).status_code,400)
        self.assertEqual(self.client.get('/search',params={'query':'x','experience':'expert'}).status_code,422)

    def test_preferences_change_ties_but_do_not_restore_rejections(self):
        self.api.feedback_store.record('subject','2',-1)
        data=self.client.get('/search',params={'query':'subject','goal':'practice'}).json()
        self.assertNotIn('2',[b['isbn'] for b in data['recommendations']])
        self.assertEqual(data['preferences']['goal'],'practice')
        self.assertGreater(learner_adjustment(self.books[2],goal='practice'),0)

    def test_complete_route_preserves_foundation_and_unique_books(self):
        data=self.client.get('/roadmap',params={'isbn':'0','query':'subject'}).json()
        self.assertTrue(data['complete'])
        self.assertEqual(data['route'][0]['isbn'],'0')
        self.assertEqual(len({b['isbn'] for b in data['route']}),4)

    def test_insufficient_stage_evidence_returns_explicit_gap(self):
        self.books[3]['title']='Unspecified Book'
        self.books[3]['abstract']='A descriptive overview.'+' neutral words'*25
        data=self.client.get('/roadmap',params={'isbn':'0','query':'subject'}).json()
        self.assertFalse(data['complete'])
        self.assertIn('Deeper study',[g['stage'] for g in data['missing_stages']])

    def test_replacement_applies_same_evidence_rules(self):
        data=self.client.post('/roadmap/replace',json={'anchor_isbn':'0','query':'subject','stage':'Deeper study','used_isbns':['0','3']}).json()
        self.assertTrue(data['exhausted'])

    def test_failed_refresh_restores_disk_and_keeps_live_search(self):
        for name in ('processed_books.json','embeddings.json'):
            (self.api.BASE_DIR/name).write_text('original',encoding='utf-8')
        def fail(*args,**kwargs):
            (self.api.BASE_DIR/'processed_books.json').write_text('partial')
            raise subprocess.TimeoutExpired('ingestion',180)
        with patch.object(self.api.subprocess,'run',side_effect=fail):
            self.assertEqual(self.client.post('/refresh-data',params={'query':'subject'}).status_code,502)
        self.assertEqual((self.api.BASE_DIR/'processed_books.json').read_text(),'original')
        self.assertEqual(self.client.get('/search',params={'query':'subject'}).status_code,200)

    def test_concurrent_refresh_rejected_while_search_available(self):
        entered, finish=Event(),Event()
        def refresh(query):
            entered.set(); finish.wait(5); return {'message':'done'}
        with patch.object(self.api,'perform_refresh',side_effect=refresh), ThreadPoolExecutor() as pool:
            first=pool.submit(self.client.post,'/refresh-data',params={'query':'x'})
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.client.post('/refresh-data',params={'query':'y'}).status_code,409)
                self.assertEqual(self.client.get('/search',params={'query':'x'}).status_code,200)
            finally: finish.set()
            self.assertEqual(first.result().status_code,200)

    def test_failed_first_refresh_removes_partial_files(self):
        def fail(*args,**kwargs):
            (self.api.BASE_DIR/'processed_books.json').write_text('partial')
            raise subprocess.CalledProcessError(1,'ingestion')
        with patch.object(self.api.subprocess,'run',side_effect=fail):
            self.client.post('/refresh-data',params={'query':'x'})
        self.assertFalse((self.api.BASE_DIR/'processed_books.json').exists())

    def test_unknown_profile_is_not_claimed_as_intermediate(self):
        self.assertEqual(infer_book_profile({'title':'Book','abstract':'Unspecified content'})['estimated_level'],'Unknown')
        self.assertFalse(candidate_evidence(self.books[1],0.05,'Core understanding')['eligible'])

    def test_introductory_title_not_promoted_by_advanced_marketing_copy(self):
        book={'title':'Understanding Basic Music Theory','abstract':'Advanced research reference graduate specialist. '+'content '*25}
        self.assertFalse(candidate_evidence(book,0.9,'Deeper study')['eligible'])


if __name__=='__main__': unittest.main()
