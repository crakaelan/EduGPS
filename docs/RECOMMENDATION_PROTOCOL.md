# Evaluation of the revised EduGPS

## Questions

1. Does full route ranking produce more appropriate stage assignments than topic-only ranking?
2. Do experience and goal preferences improve perceived suitability for the specified learner?
3. Can users find saved results, refresh explicitly, and understand an unfilled stage?

## Completed automated work

`backend/evaluate_quality.py` uses twelve existing topics across four domains, fixes the foundation for each within-topic comparison, and disables stored feedback. Full and topic-only ranking use identical candidate pools and eligibility checks. The ablation removes stage, metadata and diversity weights. The script saves a catalogue hash, full outputs, blank reviewer ratings and a separate method key.

Mean pairwise embedding similarity is a redundancy proxy. It must not be called educational quality. Bootstrap intervals resample paired topic-level differences 5,000 times using seed 3070. Twelve purposively selected topics are not a representative population sample. Warm in-process search timing excludes HTTP, rendering, ingestion and cold start.

## Blinded subject review still required

Give each reviewer only `blind-review.json`; keep the method key separate. Recruit reviewers with knowledge of the assigned subject and record expertise and conflicts. Seek two independent judgements per case where feasible; report the actual count and any missing ratings, rather than describing a target as a completed sample.

For each route rate topic relevance, stage suitability and progression from 1 (poor) to 5 (strong), with 3 meaning mixed evidence. Rate unnecessary overlap from 1 (little) to 5 (substantial). Consult descriptions and linked book listings; record when evidence is insufficient. Explain a weak placement concretely. Score complete and incomplete routes separately and report coverage alongside quality so abstaining cannot artificially improve the apparent result.

Use the topic as the paired unit, averaging multiple reviewers within each topic/method first. Present individual differences, median ratings, reviewer disagreement and a paired bootstrap interval. Treat ordinal-score mean differences cautiously. Do not claim significance from a large number of correlated book-level rows.

## Interface comparison still required

Compare the previous workflow with the revised saved-search/explicit-refresh workflow using a counterbalanced within-person study. Half the participants use each version first. Use different but matched topics to reduce practice effects. Include both novice and experienced participants; experience is a task-relevant characteristic, not a fixed learning-style label.

Tasks: obtain a shortlist; choose a foundation; explain why a stage is empty; recover after refresh failure; replace and recover a book. Record independent completion, time, assistance, errors and whether the user correctly understands saved versus refreshed results. Keep the failure simulation identical between conditions and disclose it after the task. Collect a brief neutral explanation of preferences.

Choose recruitment size based on available time and desired precision before collecting results. If the sample remains small, describe the study as formative and show individual paired outcomes. A/B infrastructure or a written protocol alone is not evidence that an A/B study occurred.

## Submission record

Keep earlier August/September results unchanged as historical evaluation. Describe the new features and automated results separately. Human route judgements and comparative interface results remain outstanding until actually collected.
