# EduGPS

EduGPS recommends books for a topic and builds a four-book learning route from a selected foundation. The Python/FastAPI backend uses sentence embeddings and cosine similarity; the Svelte frontend supports book replacement and query-specific feedback.

## Local setup on Windows

Use Python 3.12 (tested with 3.12.14) and Node.js 22.12 or newer. Run commands from this project folder in PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
```

Keep `backend/processed_books.json` and `backend/embeddings.json` together. They contain the saved catalogue and corresponding vectors. The first backend startup downloads `sentence-transformers/all-MiniLM-L6-v2` if it is not already cached, so internet access is initially required.

Start the backend in one terminal:

```powershell
$env:GOOGLE_BOOKS_API_KEY="YOUR_KEY_HERE"
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The key is optional for unauthenticated Google Books requests but is recommended to reduce quota-related failures. Never include a real key in submitted source files. The application reads the environment variable; it does not automatically load `.env` files.

Start the frontend in a second terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open the URL printed by Vite. The frontend currently expects the backend at `http://127.0.0.1:8000`. API documentation is at `http://127.0.0.1:8000/docs`.

## Demonstration

1. Search for `music theory`. Search uses the saved catalogue without calling Google Books. Select starting experience and learning goal before searching if desired.
2. Select one of the recommendations as the foundation and inspect the four route stages.
3. Replace a later-stage book and cycle back through the alternatives. The foundation remains fixed.
4. Choose a different foundation and compare the resulting route.
5. Mark a recommendation Not useful, repeat the query, and verify exclusion. Clicking an active feedback control again clears the vote. Rejection clears an existing route so its cached alternatives cannot restore the rejected title.
6. Use **Find more books online** to refresh separately. Existing results remain visible during a refresh or if it fails. Search again after a successful refresh.
7. If no distinct book passes the description and stage-evidence checks, the route identifies an unfilled stage. This is an intentional abstention, not a failed request.

Local votes are stored in `backend/feedback.json`; do not include personal testing preferences in a clean submission package. Saved-catalogue search requires the backend model to be available but not a Google Books request. Set `VITE_API_BASE_URL` before starting/building the frontend if the backend is hosted elsewhere.

## Verification

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
Set-Location ../frontend
npm run check
npm run build
```

`backend/final_reliability_test.py` supplies the separate endpoint benchmark. Inspect its setup before running it against an active backend. Evaluation scripts create results under `outputs/`. Historical reports and participant records are not included in this source repository.

## Evaluation and limitations

Run `python evaluate_quality.py` from `backend` to compare the full route ranking with a topic-only ablation on the same catalogue, anchors and eligibility gates. The script writes timestamped results, a paired topic-level bootstrap interval, and blank blinded review cases under `outputs/quality-evaluation`. Keep `review-key-private.json` away from reviewers until ratings are completed. The companion `docs/RECOMMENDATION_PROTOCOL.md` describes the human study still to conduct.

Experience and goal contribute bounded heuristic ranking adjustments (up to 0.08). Search eligibility requires cosine similarity of at least 0.20 and a description of at least 20 words; route eligibility also requires a positive stage signal and excludes introductory titles from Deeper study. These are prototype policies needing calibration, not probabilities or proof of pedagogical suitability. Existing historical metrics predate these changes and must not be relabelled as results for this build.

Refreshes are serialised within one backend process; search continues against the old in-memory snapshot until the new catalogue and index are ready. Subprocess timeouts and rollback preserve the previous files on handled failures. This does not provide crash-safe transactions across two files or multi-process coordination: run one worker for the prototype.

TF-IDF provides a lexical baseline for semantic retrieval. Precision@5 measures top-five relevance, not learning improvement. Stage assignments use metadata heuristics rather than verified prerequisite relationships. Google Books coverage varies by topic. The system is a local prototype; its current CORS configuration and fixed API address require review before public deployment.

## Submission contents

Include backend and frontend source, dependency manifests and lockfiles, the paired catalogue/embeddings, this README, and only the final report and supporting evidence required by the assessment brief. Exclude `.venv`, `node_modules`, caches, secrets, local feedback, and superseded drafts. Participant results must be traceable to original observations before being presented as empirical findings.
# Concept-aware Python planner

Choose **Plan Python around what I know** in the interface for the bounded extension. Select a concrete objective, known concepts and maximum books. The plan shows description excerpts, suggested concept order, official reference bridges, a starting-from-scratch comparison and book avoidance/replanning. **Save plan** exports JSON locally.

API: `GET /concept-map` and `POST /concept-plan` with `goal` (`automation`, `organise`, `foundations`), `known_concepts`, `max_books` (1–4) and optional `excluded_isbns`.

Rationale, source attribution, limitations and evaluation: [extension notes](docs/EXTENSION.md). Run `python evaluate_concepts.py` from `backend` for timestamped diagnostics. This mode suggests study order; it does not assess mastery or verify a book's chapter structure.
