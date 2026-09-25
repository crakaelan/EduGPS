from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from threading import Lock, RLock
from functools import wraps
import json
import torch
import subprocess
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer, util
from ranking import infer_book_profile, select_candidate, stage_metadata_scores, title_family_exclusions, candidate_evidence, learner_adjustment, explicit_language_match
from tfidf_baseline import build_tfidf_index, rank_tfidf
from feedback import FeedbackStore, MAX_SCORE_ADJUSTMENT, calibrated_scores
from concept_planner import public_schema, compare_starting_point, GOALS, CONCEPTS

app = FastAPI()
refresh_lock = Lock()
catalogue_lock = RLock()
Experience = Literal['any', 'beginner', 'experienced']
Goal = Literal['balanced', 'theory', 'practice']

def consistent_catalogue(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with catalogue_lock:
            return fn(*args, **kwargs)
    return wrapped
BASE_DIR = Path(__file__).resolve().parent
feedback_store = FeedbackStore(BASE_DIR / 'feedback.json')

# Enable CORS for Svelte frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Load model and data once at startup
model = SentenceTransformer('all-MiniLM-L6-v2')

STAGES = {
    "Foundation": "introductory fundamentals concepts beginner overview",
    "Core understanding": "core theory principles comprehensive explanation",
    "Applied practice": "practical projects examples implementation exercises",
    "Deeper study": "advanced in-depth specialist reference architecture",
}

class ReplacementRequest(BaseModel):
    anchor_isbn: str
    query: str
    stage: str
    used_isbns: list[str] = []
    rejected_isbns: list[str] = []
    experience: Experience = 'any'
    goal: Goal = 'balanced'

class FeedbackRequest(BaseModel):
    query: str
    isbn: str
    vote: Literal[-1, 0, 1]

class ConceptPlanRequest(BaseModel):
    goal: Literal['automation', 'organise', 'foundations'] = 'automation'
    known_concepts: list[str] = Field(default_factory=list, max_length=8)
    max_books: int = Field(default=3, ge=1, le=4)
    excluded_isbns: list[str] = Field(default_factory=list, max_length=254)

    @field_validator('known_concepts')
    @classmethod
    def recognised_concepts(cls, values):
        if set(values) - set(CONCEPTS):
            raise ValueError('Choose concepts from the supported Python concept map.')
        return sorted(set(values))


@app.get('/concept-map')
def get_concept_map():
    return public_schema()


@app.post('/concept-plan')
@consistent_catalogue
def get_concept_plan(request: ConceptPlanRequest):
    if not books:
        raise HTTPException(status_code=503, detail='The catalogue is empty. Add books before planning.')
    query = 'Python programming: ' + GOALS[request.goal]['label']
    scores = util.cos_sim(model.encode(query, convert_to_tensor=True), embeddings)[0].tolist()
    # Existing explicit Python-search rejection is respected in this separate mode.
    excluded = set(request.excluded_isbns)
    excluded.update(isbn for isbn,vote in feedback_store.votes_for_query('Python programming').items() if vote == -1)
    try:
        plan = compare_starting_point(books, scores, request.goal, request.known_concepts, request.max_books, excluded)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {**plan, 'catalogue_size':len(books), 'excluded_isbns':sorted(excluded)}

def load_catalogue():
    with (BASE_DIR / 'processed_books.json').open('r', encoding='utf-8') as f:
        loaded_books = json.load(f)
    with (BASE_DIR / 'embeddings.json').open('r', encoding='utf-8') as f:
        loaded_embeddings = torch.tensor(json.load(f))
    if len(loaded_books) != len(loaded_embeddings):
        raise RuntimeError("Book and embedding counts do not match.")
    return loaded_books, loaded_embeddings

try:
    books, embeddings = load_catalogue()
except FileNotFoundError:
    # A new checkout can build its first catalogue through /refresh-data.
    books, embeddings = [], torch.empty((0, 384))

tfidf_index = build_tfidf_index(books)

def topic_coverage(query: str) -> int:
    query_key = " ".join(query.lower().split())
    return sum(
        1 for book in books
        if query_key in {
            " ".join(str(topic).lower().split())
            for topic in book.get("topics", [])
        }
    )

@app.post("/refresh-data")
def refresh_data(query: str):
    global books, embeddings, tfidf_index
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="A topic query is required.")

    if not refresh_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A catalogue refresh is already running. Saved books remain available.")
    try:
        return perform_refresh(query)
    finally:
        refresh_lock.release()


def perform_refresh(query: str):
    global books, embeddings, tfidf_index

    catalogue_path = BASE_DIR / 'processed_books.json'
    embeddings_path = BASE_DIR / 'embeddings.json'
    previous_catalogue = catalogue_path.read_bytes() if catalogue_path.exists() else None
    previous_embeddings = embeddings_path.read_bytes() if embeddings_path.exists() else None
    previous_count = len(books)
    try:
        subprocess.run(
            [sys.executable, str(BASE_DIR / 'ingestion.py'), query],
            cwd=BASE_DIR, check=True, capture_output=True, text=True, timeout=180
        )
        subprocess.run(
            [sys.executable, str(BASE_DIR / 'model.py')],
            cwd=BASE_DIR, check=True, capture_output=True, text=True, timeout=300
        )
        new_books, new_embeddings = load_catalogue()
        new_index = build_tfidf_index(new_books)
        with catalogue_lock:
            books, embeddings, tfidf_index = new_books, new_embeddings, new_index
    except (subprocess.SubprocessError, OSError, ValueError, RuntimeError) as error:
        if previous_catalogue is not None:
            catalogue_path.write_bytes(previous_catalogue)
        if previous_embeddings is not None:
            embeddings_path.write_bytes(previous_embeddings)
        # Remove newly created partial files when there was no prior snapshot.
        if previous_catalogue is None:
            catalogue_path.unlink(missing_ok=True)
        if previous_embeddings is None:
            embeddings_path.unlink(missing_ok=True)
        detail = "Refresh failed. Your saved catalogue is still available. Please try again later."
        raise HTTPException(status_code=502, detail=detail) from error

    return {
        "message": "Catalogue expanded successfully!",
        "book_count": len(books),
        "added_count": len(books) - previous_count,
        "topic_coverage": topic_coverage(query),
    }


def format_recommendation(book: dict, score: float) -> dict:
    authors_data = book.get('authors') or book.get('author', [])
    author_str = ", ".join(authors_data) if isinstance(authors_data, list) else str(authors_data)
    isbn_data = book.get('isbn', 'N/A')
    if isinstance(isbn_data, list):
        isbn_str = isbn_data[0].get('identifier', 'N/A') if isbn_data else 'N/A'
    else:
        isbn_str = str(isbn_data or 'N/A')
    return {
        "title": book.get('title', 'Unknown Title'),
        "author": author_str or "Unknown Author",
        "isbn": isbn_str,
        "score": round(float(score), 4),
        "book_url": book.get('book_url') or f"https://books.google.com/books?vid=ISBN{isbn_str}",
        **infer_book_profile(book),
    }

def roadmap_topic_embedding(query: str, anchor_index: int) -> torch.Tensor:
    """Blend the learner's topic with the chosen starting book.

    The query keeps the route on-topic, while the anchor contribution ensures
    that choosing a different foundation can produce a genuinely different
    continuation.
    """
    anchor_embedding = embeddings[anchor_index]
    clean_query = query.strip()
    if not clean_query:
        return anchor_embedding
    query_embedding = model.encode(clean_query, convert_to_tensor=True)
    return 0.5 * query_embedding + 0.5 * anchor_embedding

def book_content_focus(book: dict, limit: int = 180) -> str:
    """Return a short, book-specific content excerpt for roadmap explanations."""
    description = " ".join(str(book.get("abstract") or "").split())
    if not description:
        return "The catalogue does not provide a detailed description for this book."
    first_sentence = description.split(". ", 1)[0].strip()
    if len(first_sentence) <= limit:
        return first_sentence.rstrip(".") + "."
    shortened = first_sentence[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return shortened + "…"

def roadmap_explanation(book: dict, stage: str, anchor_title: str) -> dict:
    """Return concise and expandable, description-backed route reasoning."""
    stage_reasons = {
        "Foundation": "Start with this book to establish the route’s initial context.",
        "Core understanding": "Use this book to develop the subject’s central ideas and principles.",
        "Applied practice": "Use this book to connect those ideas to examples, exercises, or practical work.",
        "Deeper study": "Use this book to continue into more detailed or specialised material.",
    }
    progression_reasons = {
        "Foundation": "This is the starting book you selected for the roadmap.",
        "Core understanding": f"Suggested as a conceptual continuation after “{anchor_title}”; prerequisite order has not been verified.",
        "Applied practice": f"Suggested for practical exploration after “{anchor_title}”; suitability depends on your prior knowledge.",
        "Deeper study": f"Suggested for further study after “{anchor_title}”, based on descriptive signals rather than verified prerequisites.",
    }
    stage_reason = stage_reasons[stage]
    return {
        "rationale": stage_reason,
        "stage_reason": stage_reason,
        "content_focus": book_content_focus(book),
        "progression_reason": progression_reasons[stage],
        "explanation_basis": "Estimated from the catalogue description and roadmap stage signals.",
        **infer_book_profile(book),
    }

@consistent_catalogue
def bert_recommendations(query: str, use_feedback: bool = True, experience: Experience = 'any', goal: Goal = 'balanced', evidence_filter: bool = True):
    if not query.strip():
        raise HTTPException(status_code=400, detail="A topic query is required.")
    if not books:
        raise HTTPException(
            status_code=503,
            detail="The catalogue is empty. Refresh data for a topic before searching."
        )
    # 1. Embed query
    query_embedding = model.encode(query, convert_to_tensor=True)
    
    # 2. Calculate cosine similarity
    raw_scores = util.cos_sim(query_embedding, embeddings)[0]
    scores, votes = calibrated_scores(raw_scores, books, query, feedback_store) if use_feedback else (raw_scores, {})
    preferences = torch.tensor([learner_adjustment(book, experience, goal) for book in books], device=scores.device)
    scores = scores + preferences
    
    # 3. Treat an explicit "not useful" vote as a hard exclusion for this
    # exact query. Positive votes remain a deliberately small calibration.
    eligible_indices = [
        index for index, book in enumerate(books)
        if votes.get(str(book.get('isbn') or ''), 0) != -1
        and (not evidence_filter or candidate_evidence(book, float(raw_scores[index]))['eligible'])
        and (not evidence_filter or explicit_language_match(book, query))
    ]
    top_results = sorted(
        eligible_indices,
        key=lambda index: float(scores[index]),
        reverse=True,
    )[:5]
    
    # 4. Format in a readable manner
    recommendations = []
    for idx in top_results:
        book = books[idx]
        recommendations.append(format_recommendation(book, scores[idx]))
        recommendations[-1]['semantic_similarity'] = round(float(raw_scores[idx]), 4)
        recommendations[-1]['preference_adjustment'] = round(float(preferences[idx]), 4)
    excluded_recommendations = [
        format_recommendation(book, scores[index])
        for index, book in enumerate(books)
        if votes.get(str(book.get('isbn') or ''), 0) == -1
    ]
    return {
        "method": "BERT cosine similarity" + (" with bounded explicit-feedback calibration" if use_feedback else " (uncalibrated)"),
        "feedback_applied": bool(votes),
        "recommendations": recommendations,
        "excluded_recommendations": excluded_recommendations,
        "evidence_notice": "Results use catalogue descriptions, not verified learning outcomes." if len(recommendations) == 5 else "Fewer than five books meet the topic and description checks. Try refreshing or broadening your topic.",
        "preferences": {"experience": experience, "goal": goal},
    }


@app.get("/search")
@consistent_catalogue
def get_recommendations(query: str, experience: Experience = 'any', goal: Goal = 'balanced'):
    result = bert_recommendations(query, use_feedback=True, experience=experience, goal=goal)
    return {
        **result,
        "catalogue_size": len(books),
        "topic_coverage": topic_coverage(query),
    }


@app.post("/feedback")
def record_feedback(request: FeedbackRequest):
    if not any(str(book.get('isbn') or '') == request.isbn.strip() for book in books):
        raise HTTPException(status_code=404, detail="Book was not found in the current catalogue.")
    try:
        saved = feedback_store.record(request.query, request.isbn, request.vote)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "message": "Preference removed." if saved["vote"] == 0 else "Preference saved.",
        "query": saved["query"],
        "isbn": saved["isbn"],
        "vote": saved["vote"],
        "score_adjustment": MAX_SCORE_ADJUSTMENT * saved["vote"],
    }


@app.get("/feedback")
def get_feedback(query: str):
    return {"query": query.strip(), "votes": feedback_store.votes_for_query(query)}


@app.get("/search/tfidf")
@consistent_catalogue
def get_tfidf_recommendations(query: str):
    """Return the keyword baseline over the same catalogue used by BERT."""
    if not books or tfidf_index is None:
        raise HTTPException(
            status_code=503,
            detail="The catalogue is empty. Refresh data for a topic before searching."
        )
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="A topic query is required.")

    ranked = rank_tfidf(clean_query, tfidf_index, limit=min(5, len(books)))
    return {
        "method": "TF-IDF unigram/bigram cosine similarity over book abstracts",
        "recommendations": [
            format_recommendation(books[index], score) for index, score in ranked
        ],
    }


@app.get("/search/compare")
@consistent_catalogue
def compare_search_methods(query: str):
    """Return both rankings from one immutable in-memory catalogue snapshot."""
    return {
        "query": query.strip(),
        "catalogue_size": len(books),
        "bert": bert_recommendations(query, use_feedback=False, evidence_filter=False),
        "tfidf": get_tfidf_recommendations(query),
    }

@app.get("/roadmap")
@consistent_catalogue
def get_roadmap(isbn: str, query: str = "", experience: Experience = 'any', goal: Goal = 'balanced'):
    if not books:
        raise HTTPException(status_code=503, detail="The catalogue is empty.")

    selected_index = next(
        (index for index, book in enumerate(books) if str(book.get('isbn')) == isbn),
        None
    )
    if selected_index is None:
        raise HTTPException(status_code=404, detail="Selected book was not found.")
    if feedback_store.votes_for_query(query).get(isbn) == -1:
        raise HTTPException(
            status_code=400,
            detail="This book is marked not useful for this topic. Clear that preference before using it as the foundation."
        )

    stages = list(STAGES.items())
    topic_embedding = roadmap_topic_embedding(query, selected_index)
    anchor_scores = util.cos_sim(topic_embedding, embeddings)[0]
    candidate_pool = set(torch.argsort(anchor_scores, descending=True)[:min(20, len(books))].tolist())
    anchor_title = books[selected_index].get('title', '')
    stage_embeddings = model.encode(
        [
            f"{query or anchor_title}; continue from {anchor_title}: {prompt}"
            for _, prompt in stages
        ],
        convert_to_tensor=True
    )
    stage_scores = util.cos_sim(stage_embeddings, embeddings)
    selected_indices = [selected_index]
    missing_stages = []
    preference_scores = torch.tensor([learner_adjustment(book, experience, goal) for book in books])
    anchor_book = books[selected_index]
    anchor_authors = anchor_book.get('authors', [])
    anchor_author = ", ".join(anchor_authors) if isinstance(anchor_authors, list) else str(anchor_authors)
    route = [{
        "step": 1,
        "stage": "Foundation",
        "title": anchor_book.get('title', 'Unknown Title'),
        "author": anchor_author or 'Unknown Author',
        "isbn": str(anchor_book.get('isbn') or 'N/A'),
        "published_date": anchor_book.get('published_date', ''),
        "thumbnail": anchor_book.get('thumbnail', ''),
        "book_url": anchor_book.get('book_url') or f"https://books.google.com/books?vid=ISBN{anchor_book.get('isbn', '')}",
        **roadmap_explanation(anchor_book, "Foundation", anchor_book.get('title', 'this book')),
        "relevance": round(float(anchor_scores[selected_index]), 3),
        "stage_fit": None,
        "metadata_stage_signal": None,
    }]
    negative_isbns = {
        book_isbn for book_isbn, vote in feedback_store.votes_for_query(query).items()
        if vote == -1 and book_isbn != isbn
    }
    negative_indices = {
        index for index, candidate in enumerate(books)
        if str(candidate.get('isbn') or '') in negative_isbns
    }

    # MMR-style selection: reward topical and stage relevance, while penalising
    # books that repeat material already present in the route.
    for stage_index, (stage_name, _) in enumerate(stages[1:], start=1):
        metadata_scores = stage_metadata_scores(books, stage_name)
        best_index, best_components = select_candidate(
            anchor_scores, stage_scores[stage_index], embeddings,
            selected_indices, {i for i in candidate_pool if candidate_evidence(books[i], float(anchor_scores[i]), stage_name)['eligible']},
            title_family_exclusions(books, selected_indices) | negative_indices,
            metadata_scores, preference_scores
        )

        if best_index is None:
            missing_stages.append({"stage": stage_name, "reason": "No distinct book meets the topic, description and stage-evidence checks. Refresh the catalogue or try a broader topic."})
            continue
        selected_indices.append(best_index)
        book = books[best_index]
        authors = book.get('authors', [])
        author = ", ".join(authors) if isinstance(authors, list) else str(authors)
        topic_relevance, stage_relevance, metadata_relevance = best_components
        route.append({
            "step": stage_index + 1,
            "stage": stage_name,
            "title": book.get('title', 'Unknown Title'),
            "author": author or 'Unknown Author',
            "isbn": str(book.get('isbn') or 'N/A'),
            "published_date": book.get('published_date', ''),
            "thumbnail": book.get('thumbnail', ''),
            "book_url": book.get('book_url') or f"https://books.google.com/books?vid=ISBN{book.get('isbn', '')}",
            **roadmap_explanation(book, stage_name, anchor_title),
            "relevance": round(topic_relevance, 3),
            "stage_fit": round(stage_relevance, 3),
            "metadata_stage_signal": round(metadata_relevance, 3),
        })

    return {
        "title": anchor_book.get('title', 'Learning roadmap'),
        "anchor": {
            "title": anchor_book.get('title', 'Unknown Title'),
            "author": anchor_book.get('authors', []),
            "book_url": anchor_book.get('book_url'),
        },
        "route": route,
        "missing_stages": missing_stages,
        "complete": len(route) == 4,
        "preferences": {"experience": experience, "goal": goal},
        "method": "Books balance the search topic, your selected foundation, learning-stage fit, and variety.",
    }

@app.post("/roadmap/replace")
@consistent_catalogue
def replace_route_book(request: ReplacementRequest):
    if request.stage not in STAGES:
        raise HTTPException(status_code=400, detail="Unknown learning stage.")
    if request.stage == "Foundation":
        raise HTTPException(status_code=400, detail="The foundation book is fixed to preserve the route's starting point.")

    anchor_index = next(
        (index for index, book in enumerate(books) if str(book.get('isbn')) == request.anchor_isbn),
        None
    )
    if anchor_index is None:
        raise HTTPException(status_code=404, detail="Starting book was not found.")

    excluded_isbns = set(request.used_isbns + request.rejected_isbns + [request.anchor_isbn])
    excluded_isbns.update(
        book_isbn for book_isbn, vote in feedback_store.votes_for_query(request.query).items()
        if vote == -1 and book_isbn != request.anchor_isbn
    )
    used_indices = [
        index for index, book in enumerate(books)
        if str(book.get('isbn')) in set(request.used_isbns + [request.anchor_isbn])
    ]
    query = request.query.strip()
    topic_embedding = roadmap_topic_embedding(query, anchor_index)
    anchor_scores = util.cos_sim(topic_embedding, embeddings)[0]
    candidate_pool = set(torch.argsort(anchor_scores, descending=True)[:min(20, len(books))].tolist())
    anchor_title = books[anchor_index].get('title', '')
    stage_embedding = model.encode(
        f"{request.query or anchor_title}; continue from {anchor_title}: {STAGES[request.stage]}",
        convert_to_tensor=True
    )
    stage_scores = util.cos_sim(stage_embedding, embeddings)[0]
    excluded_indices = [
        index for index, candidate in enumerate(books)
        if str(candidate.get('isbn')) in excluded_isbns
    ]
    excluded_indices = set(excluded_indices) | title_family_exclusions(books, excluded_indices)
    metadata_scores = stage_metadata_scores(books, request.stage)
    best_index, best_components = select_candidate(
        anchor_scores, stage_scores, embeddings, used_indices,
        {i for i in candidate_pool if candidate_evidence(books[i], float(anchor_scores[i]), request.stage)['eligible']}, excluded_indices, metadata_scores,
        torch.tensor([learner_adjustment(book, request.experience, request.goal) for book in books])
    )

    if best_index is None:
        return {
            "exhausted": True,
            "message": "No further distinct book meets the topic, description and stage-evidence checks. You can return to an earlier option."
        }

    book = books[best_index]
    authors = book.get('authors', [])
    author = ", ".join(authors) if isinstance(authors, list) else str(authors)
    topic_relevance, stage_relevance, metadata_relevance = best_components
    return {
        "exhausted": False,
        "stage": request.stage,
        "title": book.get('title', 'Unknown Title'),
        "author": author or 'Unknown Author',
        "isbn": str(book.get('isbn') or 'N/A'),
        "published_date": book.get('published_date', ''),
        "thumbnail": book.get('thumbnail', ''),
        "book_url": book.get('book_url') or f"https://books.google.com/books?vid=ISBN{book.get('isbn', '')}",
        **roadmap_explanation(book, request.stage, anchor_title),
        "relevance": round(topic_relevance, 3),
        "stage_fit": round(stage_relevance, 3),
        "metadata_stage_signal": round(metadata_relevance, 3),
    }
    
