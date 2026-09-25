from collections.abc import Iterable
import re

import torch


STAGE_SIGNALS = {
    "Foundation": {
        "positive": ("beginner", "beginners", "introduction", "introductory", "fundamentals", "basics", "essential", "getting started", "first course"),
        "negative": ("advanced", "expert", "graduate", "research", "handbook", "reference"),
    },
    "Core understanding": {
        "positive": ("principles", "theory", "concepts", "comprehensive", "textbook", "foundations", "core", "understanding"),
        "negative": ("quick start", "cheat sheet", "advanced research"),
    },
    "Applied practice": {
        "positive": ("practical", "hands on", "project", "projects", "exercise", "exercises", "case study", "case studies", "implementation", "workbook", "examples"),
        "negative": ("pure theory", "historical survey"),
    },
    "Deeper study": {
        "positive": ("advanced", "expert", "graduate", "handbook", "reference", "research", "specialist", "architecture", "in depth", "definitive"),
        "negative": ("beginner", "beginners", "getting started", "basics", "quick start"),
    },
}

LEVEL_SIGNALS = {
    "introductory": (
        "beginner", "beginners", "introduction", "introductory", "fundamentals",
        "basics", "getting started", "first course", "for dummies",
    ),
    "advanced": (
        "advanced", "expert", "graduate", "research", "specialist", "in depth",
        "handbook", "reference",
    ),
}

ORIENTATION_SIGNALS = {
    "theory": (
        "theory", "theoretical", "principles", "concepts", "foundations",
        "models", "analysis",
    ),
    "practice": (
        "practical", "hands on", "project", "projects", "exercise", "exercises",
        "case study", "case studies", "implementation", "workbook", "recipes",
    ),
}


def _book_text(book: dict) -> str:
    return re.sub(
        r"[^a-z0-9]+", " ",
        f"{book.get('title', '')} {book.get('abstract', '')}".lower(),
    ).strip()


def infer_book_profile(book: dict) -> dict:
    """Infer cautious, explainable learning metadata from catalogue wording."""
    text = _book_text(book)
    introductory = sum(phrase in text for phrase in LEVEL_SIGNALS["introductory"])
    advanced = sum(phrase in text for phrase in LEVEL_SIGNALS["advanced"])
    theory = sum(phrase in text for phrase in ORIENTATION_SIGNALS["theory"])
    practice = sum(phrase in text for phrase in ORIENTATION_SIGNALS["practice"])

    if introductory > advanced:
        level = "Introductory"
        prerequisite = "No prior knowledge is clearly indicated by the catalogue description."
    elif advanced > introductory:
        level = "Advanced"
        prerequisite = "Foundational knowledge of the topic is likely to be helpful."
    elif introductory or advanced:
        level = "Intermediate"
        prerequisite = "Some familiarity with the topic may be helpful."
    else:
        level = "Unknown"
        prerequisite = "The description does not establish prerequisite knowledge."

    if practice > theory:
        orientation = "Practice-focused"
    elif theory > practice:
        orientation = "Theory-focused"
    elif practice or theory:
        orientation = "Balanced"
    else:
        orientation = "Unspecified"

    return {
        "estimated_level": level,
        "content_orientation": orientation,
        "prerequisite_note": prerequisite,
        "profile_basis": "Estimated from wording in the catalogue title and description.",
    }


def title_family(title: str) -> str:
    """Collapse subtitles and edition wording into a stable title identity."""
    base = (title or "").lower().split(":", 1)[0]
    base = re.sub(r"\([^)]*(edition|ed\.|volume|vol\.)[^)]*\)", " ", base)
    base = re.sub(
        r"\b(?:\d+(?:st|nd|rd|th)?|first|second|third|fourth|revised|updated)\s+edition\b",
        " ",
        base,
    )
    base = re.sub(r"\bvol(?:ume)?\.?\s+[a-z0-9ivx]+\b", " ", base)
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def title_family_exclusions(books: list[dict], selected_indices: Iterable[int]) -> set[int]:
    selected_families = {
        title_family(books[index].get("title", "")) for index in selected_indices
    }
    return {
        index for index, book in enumerate(books)
        if title_family(book.get("title", "")) in selected_families
    }


def stage_metadata_score(book: dict, stage: str) -> float:
    """Return an interpretable 0-1 stage signal from title and abstract wording."""
    signals = STAGE_SIGNALS[stage]
    text = re.sub(
        r"[^a-z0-9]+", " ",
        f"{book.get('title', '')} {book.get('abstract', '')}".lower(),
    ).strip()
    positive_matches = sum(1 for phrase in signals["positive"] if phrase in text)
    negative_matches = sum(1 for phrase in signals["negative"] if phrase in text)
    raw_score = 0.25 + 0.2 * positive_matches - 0.2 * negative_matches
    return round(max(0.0, min(1.0, raw_score)), 3)


def stage_metadata_scores(books: list[dict], stage: str) -> torch.Tensor:
    return torch.tensor([stage_metadata_score(book, stage) for book in books])


def cosine_similarity(left: torch.Tensor, right: torch.Tensor) -> float:
    left = left.float().flatten()
    right = right.float().flatten()
    denominator = torch.linalg.vector_norm(left) * torch.linalg.vector_norm(right)
    if float(denominator) == 0.0:
        return 0.0
    return float(torch.dot(left, right) / denominator)


def select_candidate(
    topic_scores: torch.Tensor,
    stage_scores: torch.Tensor,
    embeddings: torch.Tensor,
    selected_indices: list[int],
    candidate_pool: Iterable[int],
    excluded_indices: Iterable[int] = (),
    metadata_scores: torch.Tensor | None = None,
    preference_scores: torch.Tensor | None = None,
    weights: tuple[float, float, float, float] = (0.5, 0.15, 0.2, 0.15),
):
    """Select a relevant, stage-appropriate candidate without near-duplication."""
    excluded = set(excluded_indices) | set(selected_indices)
    best_index = None
    best_score = float("-inf")
    best_components = None

    for candidate_index in sorted(candidate_pool):
        if candidate_index in excluded:
            continue
        diversity_penalty = max(
            (
                cosine_similarity(embeddings[candidate_index], embeddings[chosen])
                for chosen in selected_indices
            ),
            default=0.0,
        )
        topic_relevance = float(topic_scores[candidate_index])
        stage_relevance = float(stage_scores[candidate_index])
        metadata_relevance = (
            float(metadata_scores[candidate_index]) if metadata_scores is not None else stage_relevance
        )
        combined_score = (
            weights[0] * topic_relevance
            + weights[1] * stage_relevance
            + weights[2] * metadata_relevance
            - weights[3] * diversity_penalty
            + (float(preference_scores[candidate_index]) if preference_scores is not None else 0.0)
        )
        if combined_score > best_score:
            best_index = candidate_index
            best_score = combined_score
            best_components = (topic_relevance, stage_relevance, metadata_relevance)

    return best_index, best_components


# Conservative prototype gates, not calibrated probabilities or educational guarantees.
MIN_TOPIC_SIMILARITY = 0.20
MIN_DESCRIPTION_WORDS = 20


def explicit_language_match(book: dict, query: str) -> bool:
    """Require named JS/TS topics in metadata; similarity alone can cross languages.

    This narrow guard is not a general relevance classifier. Broad topics retain
    semantic matching, and incidental mentions can still require human review.
    """
    groups = (("javascript", "java script", "ecmascript", "js"),
              ("typescript", "type script", "ts"))
    query_text = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    book_text = _book_text(book)
    for aliases in groups:
        pattern = r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b"
        if re.search(pattern, query_text) and not re.search(pattern, book_text):
            return False
    return True


def candidate_evidence(book: dict, topic_score: float, stage: str | None = None) -> dict:
    reasons = []
    if topic_score < MIN_TOPIC_SIMILARITY:
        reasons.append("Limited topic similarity")
    if len(str(book.get('abstract') or '').split()) < MIN_DESCRIPTION_WORDS:
        reasons.append("Description too short to assess")
    if stage and stage_metadata_score(book, stage) <= 0.25:
        reasons.append("No clear positive evidence for this learning stage")
    if stage == 'Deeper study' and re.search(r'\b(basic|basics|beginner|beginners|introductory|introduction)\b', str(book.get('title') or '').lower()):
        reasons.append("Introductory title conflicts with the deeper-study stage")
    return {"eligible": not reasons, "reasons": reasons,
            "basis": "Heuristic checks of topic similarity, description length and stage wording; not a confidence probability."}


def learner_adjustment(book: dict, experience: str = 'any', goal: str = 'balanced') -> float:
    """Bounded preference bonus; never changes eligibility or overrides rejection."""
    profile = infer_book_profile(book)
    score = 0.0
    if experience == 'beginner':
        score += 0.04 if profile['estimated_level'] == 'Introductory' else -0.04 if profile['estimated_level'] == 'Advanced' else 0
    elif experience == 'experienced':
        score += 0.04 if profile['estimated_level'] in ('Intermediate', 'Advanced') else 0
    desired = {'theory': 'Theory-focused', 'practice': 'Practice-focused'}.get(goal)
    if desired and profile['content_orientation'] == desired:
        score += 0.04
    return score
