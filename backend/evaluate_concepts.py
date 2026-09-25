"""Real-catalogue comparison, with no invented relevance or human judgements.

The metrics deliberately use the planner's own graph/matcher and are diagnostic,
not independent validation. Scenarios share a catalogue and are not independent
samples; no significance test or learning-outcome claim is made.
"""
import hashlib
import json
import random
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from sentence_transformers import util
import main as api
from concept_planner import CONCEPTS, GOALS, VERSION, build_plan, catalogue_evidence, required_concepts
from feedback import FeedbackStore


def diagnose(sequence, required, known, lookup):
    """Count missing prerequisites before each book, permitting within-book order.

    This is a graph diagnostic over mentions, not a claim of actual chapter order.
    """
    available=set(known); mentions=set(); missing=set()
    for isbn in sequence:
        found=set(catalogue_evidence(lookup[isbn])) & set(required)
        for c in required:
            if c in found and c not in available:
                missing.update(set(CONCEPTS[c]['requires'])-available-found)
        available.update(found); mentions.update(found)
    needed=set(required)-set(known)
    return {'mentioned_needed_concepts':len(mentions&needed), 'needed_concepts':len(needed),
            'coverage':len(mentions&needed)/len(needed) if needed else 1.,
            'unsupported_prerequisite_concepts':sorted(missing), 'books':len(sequence)}


def run():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(__file__).resolve().parent.parent/'outputs'/'concept-evaluation'/stamp
    out.mkdir(parents=True,exist_ok=False)
    lookup={str(b.get('isbn')):b for b in api.books}; rows=[]; reviews=[]; keys=[]; timings=[]
    profiles={'new':[], 'some':['values','control'], 'familiar':['values','control','collections','functions']}
    rng=random.Random(3070)
    with tempfile.TemporaryDirectory() as tmp, patch.object(api,'feedback_store',FeedbackStore(Path(tmp)/'feedback.json')):
        for goal, definition in GOALS.items():
            query='Python programming: '+definition['label']
            scores=util.cos_sim(api.model.encode(query,convert_to_tensor=True),api.embeddings)[0].tolist()
            ranked=sorted(range(len(api.books)),key=lambda i:(-scores[i],str(api.books[i].get('isbn',''))))
            from ranking import candidate_evidence
            eligible=[i for i in ranked if candidate_evidence(api.books[i],scores[i])['eligible']]
            existing=api.get_roadmap(str(api.books[eligible[0]]['isbn']),query)['route'] if eligible else []
            for profile,known in profiles.items():
                for budget in (2,4):
                    start=time.perf_counter(); plan=build_plan(api.books,scores,goal,known,budget)
                    timings.append((time.perf_counter()-start)*1000)
                    variants={
                        'topic_only':[str(api.books[i]['isbn']) for i in eligible[:budget]],
                        'current_route':[b['isbn'] for b in existing[:budget]],
                        'concept_plan':[s['isbn'] for s in plan['steps'] if s['kind']=='book']}
                    metrics={name:diagnose(ids,required_concepts(goal),known,lookup) for name,ids in variants.items()}
                    rows.append({'goal':goal,'profile':profile,'known':known,'budget':budget,
                                 'variants':variants,'metrics':metrics,'plan':plan})
                    options=list(variants.items()); rng.shuffle(options)
                    for label,(name,ids) in zip('ABC',options):
                        case=f'{len(rows):02d}-{label}'
                        # Evaluate book choice blind; bridge utility is a separate unblinded task.
                        reviews.append({'case':case,'objective':definition['task'],'known_concepts':known,'book_limit':budget,
                            'books':[{'title':lookup[i]['title'],'description':lookup[i].get('abstract',''),'url':lookup[i].get('book_url','')} for i in ids],
                            'reviewer_id':None,'goal_relevance_1_to_5':None,'starting_level_fit_1_to_5':None,
                            'progression_1_to_5':None,'redundancy_1_to_5':None,'comments':None})
                        keys.append({'case':case,'variant':name})
    summary={'created_utc':stamp,'graph_version':VERSION,'catalogue_size':len(api.books),
        'catalogue_sha256':hashlib.sha256((api.BASE_DIR/'processed_books.json').read_bytes()).hexdigest(),
        'planner_sha256':hashlib.sha256(Path(__file__).with_name('concept_planner.py').read_bytes()).hexdigest(),
        'scenarios':len(rows), 'profiles':profiles,
        'methods':{name:{'mean_mention_coverage':round(statistics.mean(r['metrics'][name]['coverage'] for r in rows),4),
                         'scenarios_with_unsupported_prerequisites':sum(bool(r['metrics'][name]['unsupported_prerequisite_concepts']) for r in rows),
                         'mean_books':round(statistics.mean(r['metrics'][name]['books'] for r in rows),2)} for name in variants},
        'concept_plan_bridge_counts':[len(r['plan']['bridge_concepts']) for r in rows],
        'planner_only_median_ms':round(statistics.median(timings),2),
        'scope':'18 constructed scenarios share three goals, profiles and catalogue. Own graph/matcher metrics are not independent educational evaluation. Bridges excluded from book coverage. Book sequences evaluated without external bridges. Timings exclude encoding, HTTP and rendering. Human ratings blank; no inference about learning gains.'}
    for name,data in [('summary.json',summary),('results.json',rows),('blind-review.json',reviews),('review-key-private.json',keys)]:
        (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2)); print(out)


if __name__=='__main__': run()
