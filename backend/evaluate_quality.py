"""Reproducible component comparison; never fabricates relevance judgements.

Run from backend: python evaluate_quality.py
Uses cached model/catalogue, no ingestion, and an isolated empty feedback store.
Outputs a new timestamped directory so previous evidence is preserved.
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

import main as api
from feedback import FeedbackStore
from ranking import select_candidate, cosine_similarity
from final_reliability_test import TOPICS


def bootstrap(values, seed=3070):
    rng=random.Random(seed)
    draws=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(5000))
    return [round(draws[124],4),round(draws[4874],4)]


def redundancy(route):
    ids={str(b.get('isbn')):i for i,b in enumerate(api.books)}
    indices=[ids[b['isbn']] for b in route]
    pairs=[cosine_similarity(api.embeddings[a],api.embeddings[b]) for n,a in enumerate(indices) for b in indices[n+1:]]
    return statistics.mean(pairs) if pairs else None


def run():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(__file__).resolve().parent.parent/'outputs'/'quality-evaluation'/stamp
    out.mkdir(parents=True,exist_ok=False)
    rows=[]; reviews=[]; keys=[]; timings=[]; rng=random.Random(3070)
    original_feedback=api.feedback_store
    with tempfile.TemporaryDirectory() as tmp:
        api.feedback_store=FeedbackStore(Path(tmp)/'feedback.json')
        try:
            api.get_recommendations('music theory')  # warm-up excluded
            for domain,query in TOPICS:
                started=time.perf_counter()
                search=api.get_recommendations(query)
                timings.append((time.perf_counter()-started)*1000)
                if not search['recommendations']:
                    rows.append({'domain':domain,'query':query,'no_eligible_search_results':True}); continue
                anchor=search['recommendations'][0]['isbn']
                full=api.get_roadmap(anchor,query)
                def topic_only(*args,**kwargs):
                    kwargs['weights']=(1.,0.,0.,0.)
                    return select_candidate(*args,**kwargs)
                with patch.object(api,'select_candidate',side_effect=topic_only):
                    baseline=api.get_roadmap(anchor,query)
                profiles={}
                for level,goal in [('beginner','practice'),('experienced','theory')]:
                    ranked=api.get_recommendations(query,level,goal)
                    route=api.get_roadmap(anchor,query,level,goal)
                    profiles[f'{level}/{goal}']={'search_isbns':[b['isbn'] for b in ranked['recommendations']], 'route_isbns':[b['isbn'] for b in route['route']], 'complete':route['complete']}
                row={'domain':domain,'query':query,'anchor':anchor,'search_isbns':[b['isbn'] for b in search['recommendations']], 'full':full,'topic_only':baseline,'profiles':profiles,'full_redundancy':redundancy(full['route']),'topic_only_redundancy':redundancy(baseline['route'])}
                rows.append(row)
                variants=[('full',full),('topic_only',baseline)]; rng.shuffle(variants)
                for label,(name,result) in zip(('A','B'),variants):
                    case=f'{len(rows):02d}-{label}'
                    reviews.append({'case':case,'topic':query,'route':[{'stage':b['stage'],'title':b['title'],'book_url':b['book_url'],'description':next(x.get('abstract','') for x in api.books if str(x.get('isbn'))==b['isbn'])} for b in result['route']], 'unfilled_stages':[g['stage'] for g in result['missing_stages']], 'reviewer_id':None,'topic_relevance_1_to_5':None,'stage_suitability_1_to_5':None,'progression_1_to_5':None,'unnecessary_overlap_1_to_5':None,'comments':None})
                    keys.append({'case':case,'variant':name})
        finally: api.feedback_store=original_feedback
    evaluated=[r for r in rows if 'full' in r]
    diffs=[r['full_redundancy']-r['topic_only_redundancy'] for r in evaluated if r['full_redundancy'] is not None and r['topic_only_redundancy'] is not None]
    summary={'created_utc':stamp,'catalogue_size':len(api.books),'catalogue_sha256':hashlib.sha256((api.BASE_DIR/'processed_books.json').read_bytes()).hexdigest(),'topics':len(rows),'complete_full_routes':sum(r['full']['complete'] for r in evaluated),'complete_topic_only_routes':sum(r['topic_only']['complete'] for r in evaluated),'full_minus_baseline_redundancy_mean':statistics.mean(diffs) if diffs else None,'paired_topic_bootstrap_95_interval':bootstrap(diffs) if diffs else None,'search_mean_ms':statistics.mean(timings),'search_median_ms':statistics.median(timings),'profile_changes':sum(any(p['route_isbns']!=[b['isbn'] for b in r['full']['route']] or p['search_isbns']!=r['search_isbns'] for p in r['profiles'].values()) for r in evaluated),'scope':'Warm in-process timings, 12 purposively selected topics, feedback disabled. Same anchor, pool and eligibility checks across ablations. Lower embedding similarity is only a redundancy proxy, not proven learning quality. Bootstrap resamples topic-level differences; does not establish population generalisation. Human judgements remain blank.'}
    for name,data in [('results.json',rows),('summary.json',summary),('blind-review.json',reviews),('review-key-private.json',keys)]:
        (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2)); print(out)


if __name__=='__main__': run()
