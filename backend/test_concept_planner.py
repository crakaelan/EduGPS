import importlib
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import torch
from concept_planner import (CONCEPTS, GOALS, build_plan, catalogue_evidence,
                             compare_starting_point, required_concepts, validate_graph)


def book(isbn, description, title=None):
    return {'isbn':isbn,'title':title or 'Python '+isbn,
            'abstract':description+' This educational book includes explanations and practical worked examples for readers studying the Python programming language at their own pace.'}


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.books=[book('a','Variables, data types and operators.'),
                    book('b','Control flow and loops. Lists and dictionaries.'),
                    book('c','Functions. File handling and exceptions.'),
                    book('d','Modules and classes.')]

    def assert_order(self, plan):
        available=set(plan['known_concepts'])
        for step in plan['steps']:
            for c in step['concepts']:
                self.assertTrue(set(CONCEPTS[c]['requires'])<=available,(c,available))
                self.assertNotIn(c,available)
                available.add(c)
        self.assertTrue(set(plan['required_concepts'])<=available)

    def test_all_profiles_and_budgets_preserve_order_and_limits(self):
        for goal in GOALS:
            for known in ([],['values'],['values','control','collections'],list(CONCEPTS)):
                for budget in (1,2,3,4):
                    with self.subTest(goal=goal,known=known,budget=budget):
                        plan=build_plan(self.books,[.8]*4,goal,known,budget)
                        self.assert_order(plan)
                        self.assertLessEqual(plan['books_used'],budget)
                        ids=[s['isbn'] for s in plan['steps'] if s['kind']=='book']
                        self.assertEqual(len(ids),len(set(ids)))

    def test_missing_book_concept_is_bridged_not_claimed_as_coverage(self):
        plan=build_plan([self.books[0]],[.9],goal='automation')
        self.assertIn('files',plan['bridge_concepts'])
        self.assertNotIn('files',plan['book_supported_concepts'])
        self.assert_order(plan)

    def test_cannot_jump_prerequisites_even_for_high_similarity(self):
        plan=build_plan([self.books[2]],[.99])
        self.assertEqual(plan['steps'][0]['kind'],'bridge')
        self.assert_order(plan)

    def test_self_report_does_not_imply_mastery_of_unchecked_concepts(self):
        plan=build_plan(self.books,[.8]*4,known=['functions'])
        self.assertIn('control',plan['remaining_concepts'])
        self.assertNotIn('functions',plan['remaining_concepts'])

    def test_all_known_needs_no_extra_reading(self):
        plan=build_plan(self.books,[.8]*4,known=list(CONCEPTS))
        self.assertEqual(plan['steps'],[])
        self.assertEqual(plan['books_used'],0)

    def test_exclusion_and_title_families_are_hard_constraints(self):
        books=[book('a','Variables.','Python Course: One'),book('b','Loops. Lists.','Python Course: Two')]
        p=build_plan(books,[.8,.8],excluded=['a'])
        self.assertNotIn('a',[s.get('isbn') for s in p['steps']])
        p=build_plan(books,[.8,.8])
        self.assertLessEqual(p['books_used'],1)

    def test_evidence_is_literal_not_substring_or_prerequisite_claim(self):
        b=book('a','Assumes prior knowledge of functions. Does not cover classes. Functional programming and classification. Variables and loops.')
        e=catalogue_evidence(b)
        self.assertNotIn('functions',e); self.assertNotIn('classes',e)
        self.assertIn('values',e)
        for item in e.values():
            self.assertIn(item['excerpt'],b['abstract'])
            self.assertIn(item['term'],item['excerpt'])

    def test_wrong_domain_sparse_or_irrelevant_books_cannot_fill_gaps(self):
        wrong={'title':'Botany','isbn':'z','abstract':'Variables and functions. '+'words '*25}
        sparse={'title':'Python','isbn':'x','abstract':'Variables'}
        p=build_plan([wrong,sparse,self.books[0]],[.9,.9,.1])
        self.assertEqual(p['books_used'],0)

    def test_invalid_goal_concept_and_budget_rejected(self):
        for kwargs in ({'goal':'music'},{'known':['made-up']},{'max_books':0},{'max_books':5}):
            with self.assertRaises(ValueError): build_plan(self.books,[.8]*4,**kwargs)

    def test_graph_cycle_and_unknown_node_fail_fast(self):
        for graph in ({'a':{'requires':['b']},'b':{'requires':['a']}},{'a':{'requires':['absent']}}):
            with self.assertRaises(ValueError): validate_graph(graph)

    def test_comparison_changes_only_declared_knowledge(self):
        p=compare_starting_point(self.books,[.8]*4,'automation',['values','control'],2)
        c=p['starting_point_comparison']
        self.assertEqual(c['without_known_concepts']-c['with_known_concepts'],2)
        self.assertEqual(p,compare_starting_point(self.books,[.8]*4,'automation',['values','control'],2))

    def test_more_budget_does_not_reduce_coverage_in_fixture(self):
        lengths=[len(build_plan(self.books,[.8]*4,max_books=b)['book_supported_concepts']) for b in range(1,5)]
        self.assertEqual(lengths,sorted(lengths))


class PlannerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_quality import FakeEncoder
        with patch('sentence_transformers.SentenceTransformer',return_value=FakeEncoder()):
            cls.api=importlib.import_module('main')

    def test_schema_and_input_validation(self):
        client=TestClient(self.api.app)
        self.assertEqual(client.get('/concept-map').status_code,200)
        for body in ({'goal':'music'},{'max_books':0},{'known_concepts':['invalid']}):
            self.assertEqual(client.post('/concept-plan',json=body).status_code,422)

    def test_endpoint_uses_catalogue_without_ingestion(self):
        from test_quality import FakeEncoder
        with patch.object(self.api,'model',FakeEncoder()), patch.object(self.api,'books',[book('a','Variables. Loops. Lists. Functions.')]), patch.object(self.api,'embeddings',torch.tensor([[1.,0.]])), patch.object(self.api.subprocess,'run') as run:
            response=TestClient(self.api.app).post('/concept-plan',json={'goal':'foundations'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['books_used'],1)
            run.assert_not_called()

    def test_empty_catalogue_returns_actionable_failure(self):
        with patch.object(self.api,'books',[]):
            response=TestClient(self.api.app).post('/concept-plan',json={})
            self.assertEqual(response.status_code,503)


if __name__=='__main__': unittest.main()
