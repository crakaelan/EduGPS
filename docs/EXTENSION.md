# EduGPS concept-aware Python planning

## Decision and originality

The extension is a bounded Python study planner alongside broad-topic book discovery. Its contribution is the combination of learner-declared knowledge, goal-dependent prerequisite closure, evidence-linked book selection, explicit reference bridges, counterfactual starting-point explanations and reversible book avoidance. Graph traversal and greedy coverage selection are established techniques; this is not a claim to invent either algorithm or to be the first prerequisite-aware recommender.

The research question is: **Does a concept-aware planner produce more useful, appropriately sequenced study suggestions than topic-only or stage-based retrieval for stated learner goals?** Automated diagnostics answer only part of this question. Independent human assessment remains required.

## What works

- Eight Python concept groups, three concrete objectives and a one-to-four-book limit.
- A project-authored directed acyclic prerequisite graph, validated for missing nodes and cycles.
- Goal closure and topological ordering; explicitly checked concepts are omitted. Checking an advanced concept does not silently imply knowledge of all its ancestors.
- Literal, word-bounded concept mentions in Python catalogue descriptions, with short source excerpts. Obvious prerequisite and negation clauses are excluded conservatively.
- Greedy selection: `0.75 × reachable remaining concept fraction + 0.25 × topic cosine similarity`. Constants are heuristics. Stable identifier tie-breaking, title-family deduplication, minimum description length and similarity gates, and explicit exclusions apply.
- Suggested within-book concept order is computed, not extracted from a verified table of contents. A selected book may require additional knowledge that its public description does not reveal.
- Official documentation references bridge missing book evidence or a reached book limit. Bridges are counted separately and never inflate book coverage.
- The same inputs are rerun without declared knowledge to expose what changed. This comparison does not estimate study time or learning gains.
- Avoid/replan and restore controls; JSON export contains the current plan and concept map. Changed inputs are visibly pending until rebuilt; stale-plan actions are disabled.
- No server-side learner profile is saved. Existing negative feedback for the exact normalised query `Python programming` also applies; other search-query feedback is not inferred.

## Sources and curation boundaries

Reviewed 25 September 2026. Concepts and reference links use the official Python documentation. The dependency edges and practice checks are project-authored design choices. Python's tutorial explicitly expects basic programming familiarity, so it is not presented as sufficient instruction for a complete programming novice.

| Concept | Reference | Project ordering rationale |
|---|---|---|
| Values | https://docs.python.org/3/tutorial/introduction.html | Initial building block |
| Control flow | https://docs.python.org/3/tutorial/controlflow.html | Expressions before branching/iteration |
| Collections | https://docs.python.org/3/tutorial/datastructures.html | Individual values before grouping them |
| Functions | https://docs.python.org/3/tutorial/controlflow.html#defining-functions | Behaviour before reusable functions |
| Files | https://docs.python.org/3/tutorial/inputoutput.html#reading-and-writing-files | Collections and iteration for record processing |
| Exceptions | https://docs.python.org/3/tutorial/errors.html | Branching between outcomes |
| Modules | https://docs.python.org/3/tutorial/modules.html | Reusable functions before module organisation |
| Classes | https://docs.python.org/3/tutorial/classes.html | Functions and collections before state/behaviour grouping |

## Initial real-catalogue diagnostic

Run `20260925T121202Z`: 254 books; 18 constructed scenarios (three goals × three knowledge profiles × two book limits). The catalogue hash and planner hash are saved with raw outputs. Feedback is isolated for the comparison.

| Method | Mean mention coverage | Scenarios with unsupported prerequisite mentions | Mean books |
|---|---:|---:|---:|
| Topic-only | 85.26% | 10/18 | 3.00 |
| Existing stage route | 94.44% | 10/18 | 2.67 |
| Concept planner | 100% | 0/18 | 1.22 |

These are **internal diagnostics using the same concept matcher and graph that guide selection**. Success is partly expected by construction and does not independently establish book quality, chapter order, instructional coverage, mastery or superiority. The broad descriptions of comprehensive books can make a small selection look complete. The scenarios reuse the same catalogue and goals; no independent-sample significance test is appropriate. There were no reference bridges in this particular run; shortage handling is covered by controlled tests and needs human assessment. Planner-only median was 90.57 ms, excluding embedding, HTTP and rendering. The endpoint also builds the starting-point comparison, so this is not endpoint latency.

Topic-only uses the same query, catalogue and basic eligibility gates. The existing route additionally uses its foundation and stage rules. All methods share the same maximum book count, but the baselines do not stop once concept coverage is reached. Consequently, fewer books is descriptive, not proof of superior efficiency. A fairer focused follow-up should compare with a coverage-stopping baseline and review both overly broad and narrow descriptions.

## Human review protocol

`blind-review.json` contains 54 unfilled, shuffled method cases; `review-key-private.json` is kept separate. Give independent reviewers the objective, known concepts and original descriptions, not the method key. Rate goal relevance, starting-level fit, progression and redundancy, and collect reasons for disagreement. Keep cases from the same goal/profile grouped for analysis rather than treating them as independent participants.

Book selection can be reviewed blind. Separately review the full plan, source bridges and explanation usability; that task cannot be fully blinded because the interfaces reveal their method. Include first-time participants, counterbalance task order, measure successful interpretation and recovery, and preserve all original observations. No ratings or participant outcomes have been filled in by the software.

## Verification and reproduction

- `python -m unittest discover -p "test_*.py"` from backend: 48 tests passed, including 15 extension tests. These cover all goal/profile/budget combinations in controlled fixtures, graph errors, unsupported prerequisites, missing evidence, exclusions, all-known input and API validation.
- `npm run check`: zero errors/warnings; `npm run build`: successful. Hosting adapter remains unconfigured.
- `python evaluate_concepts.py` creates timestamped real-catalogue results and review forms. It does not ingest books or overwrite prior evidence.
- Browser walkthrough verified initial planning, declared knowledge changing the plan, a pending-input warning disabling stale actions, source excerpts, the starting-from-scratch comparison, alternative scores, avoiding a specialised book and a one-book constraint producing a reference bridge. These are developer checks, not participant-study outcomes.
- The browser surfaced a Raspberry Pi-specific book for the general file-processing goal. Concept mentions can favour a specialised resource; avoidance resolves that particular choice but does not establish a general solution. Independent review should explicitly assess unwanted domain specialisation.

## Report status

The extension is described in `EduGPS_Final_Report_Concept_Extension.docx`, including its rationale, implementation, diagnostic results and limitations. The earlier four-participant study does not evaluate this planner.
