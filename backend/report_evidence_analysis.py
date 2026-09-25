import json
import os
import platform
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, util

from ranking import (
    stage_metadata_scores,
    title_family,
    title_family_exclusions,
)


BASE = Path(__file__).resolve().parent
OUTPUT = BASE.parent / "outputs" / "final-evaluation" / "report_evidence_analysis.json"
BOOKS = json.loads((BASE / "processed_books.json").read_text(encoding="utf-8"))
EMBEDDINGS = torch.tensor(
    json.loads((BASE / "embeddings.json").read_text(encoding="utf-8")),
    dtype=torch.float32,
)

STAGES = {
    "Foundation": "introductory fundamentals concepts beginner overview",
    "Core understanding": "core theory principles comprehensive explanation",
    "Applied practice": "practical projects examples implementation exercises",
    "Deeper study": "advanced in-depth specialist reference architecture",
}
QUERIES = [
    "Python programming",
    "distributed systems",
    "quantum physics",
    "molecular biology",
    "modern European history",
    "philosophy and ethics",
    "business strategy",
    "corporate finance",
]
WEIGHTS = {
    "baseline": (0.50, 0.15, 0.20, 0.15),
    "topic_heavy": (0.65, 0.10, 0.15, 0.10),
    "stage_heavy": (0.40, 0.25, 0.25, 0.10),
    "diversity_heavy": (0.45, 0.15, 0.20, 0.25),
}


def normalise(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def select_route(query_embedding, stage_embeddings, weights):
    topic_weight, stage_weight, metadata_weight, diversity_weight = weights
    topic_scores = util.cos_sim(query_embedding, EMBEDDINGS)[0]
    foundation = int(torch.argmax(topic_scores))
    blended = 0.5 * query_embedding + 0.5 * EMBEDDINGS[foundation]
    anchor_scores = util.cos_sim(blended, EMBEDDINGS)[0]
    candidate_pool = set(
        torch.argsort(anchor_scores, descending=True)[: min(20, len(BOOKS))].tolist()
    )
    semantic_stage_scores = util.cos_sim(stage_embeddings, EMBEDDINGS)
    selected = [foundation]
    components = []
    for stage_index, stage_name in enumerate(list(STAGES)[1:], start=1):
        metadata = stage_metadata_scores(BOOKS, stage_name)
        excluded = title_family_exclusions(BOOKS, selected) | set(selected)
        best = None
        best_score = float("-inf")
        best_parts = None
        for candidate in candidate_pool:
            if candidate in excluded:
                continue
            diversity = max(
                float(util.cos_sim(EMBEDDINGS[candidate], EMBEDDINGS[chosen])[0][0])
                for chosen in selected
            )
            topic = float(anchor_scores[candidate])
            stage = float(semantic_stage_scores[stage_index][candidate])
            meta = float(metadata[candidate])
            score = (
                topic_weight * topic
                + stage_weight * stage
                + metadata_weight * meta
                - diversity_weight * diversity
            )
            if score > best_score:
                best, best_score = candidate, score
                best_parts = {
                    "topic": round(topic, 4),
                    "semantic_stage": round(stage, 4),
                    "metadata_stage": round(meta, 4),
                    "diversity_similarity": round(diversity, 4),
                }
        if best is None:
            break
        selected.append(best)
        components.append(best_parts)
    return selected, components


def catalogue_quality():
    isbn_counts = Counter(normalise(book.get("isbn")) for book in BOOKS if book.get("isbn"))
    edition_counts = Counter(
        (
            normalise(book.get("title")),
            tuple(sorted(normalise(author) for author in book.get("authors", []))),
        )
        for book in BOOKS
    )
    family_counts = Counter(title_family(book.get("title", "")) for book in BOOKS)
    abstract_words = [len(str(book.get("abstract", "")).split()) for book in BOOKS]
    identifier_types = Counter()
    for book in BOOKS:
        value = str(book.get("isbn", ""))
        if re.fullmatch(r"\d{13}", value):
            identifier_types["ISBN-13"] += 1
        elif re.fullmatch(r"\d{10}", value):
            identifier_types["ISBN-10"] += 1
        elif ":" in value:
            identifier_types["Library identifier"] += 1
        else:
            identifier_types["Google volume or other"] += 1
    return {
        "records": len(BOOKS),
        "embedding_dimensions": len(EMBEDDINGS[0]),
        "exact_normalised_isbn_duplicate_groups": sum(v > 1 for v in isbn_counts.values()),
        "exact_title_author_duplicate_groups": sum(v > 1 for v in edition_counts.values()),
        "repeated_title_family_groups": sum(v > 1 for v in family_counts.values()),
        "books_in_repeated_title_families": sum(v for v in family_counts.values() if v > 1),
        "missing_or_unknown_author": sum(
            not book.get("authors")
            or all(str(a).strip().lower() == "unknown author" for a in book.get("authors", []))
            for book in BOOKS
        ),
        "missing_published_date": sum(not book.get("published_date") for book in BOOKS),
        "missing_thumbnail": sum(not book.get("thumbnail") for book in BOOKS),
        "missing_book_url": sum(not book.get("book_url") for book in BOOKS),
        "records_with_topics_field": sum(bool(book.get("topics")) for book in BOOKS),
        "abstract_words": {
            "minimum": min(abstract_words),
            "median": round(statistics.median(abstract_words), 1),
            "mean": round(statistics.mean(abstract_words), 1),
            "maximum": max(abstract_words),
        },
        "identifier_types": dict(identifier_types),
        "catalogue_file_kb": round((BASE / "processed_books.json").stat().st_size / 1024, 1),
        "embeddings_file_kb": round((BASE / "embeddings.json").stat().st_size / 1024, 1),
    }


def ranking_scalability(query_embedding):
    results = []
    for size in [50, 100, 150, 200, len(BOOKS)]:
        sample = EMBEDDINGS[:size]
        for _ in range(20):
            util.cos_sim(query_embedding, sample)
        timings = []
        for _ in range(250):
            started = time.perf_counter()
            scores = util.cos_sim(query_embedding, sample)[0]
            torch.topk(scores, k=min(5, size))
            timings.append((time.perf_counter() - started) * 1000)
        results.append({
            "catalogue_size": size,
            "median_ms": round(statistics.median(timings), 4),
            "p95_ms": round(sorted(timings)[int(len(timings) * 0.95) - 1], 4),
        })
    return results


def main():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    query_embeddings = model.encode(QUERIES, convert_to_tensor=True)
    sensitivity = {}
    baseline_routes = {}
    for query, query_embedding in zip(QUERIES, query_embeddings):
        stage_embeddings = model.encode(
            [f"{query}: {prompt}" for prompt in STAGES.values()],
            convert_to_tensor=True,
        )
        sensitivity[query] = {}
        for name, weights in WEIGHTS.items():
            route, components = select_route(query_embedding, stage_embeddings, weights)
            sensitivity[query][name] = {
                "isbns": [str(BOOKS[i].get("isbn")) for i in route],
                "titles": [BOOKS[i].get("title") for i in route],
                "components": components,
            }
            if name == "baseline":
                baseline_routes[query] = route

    summary = {}
    for name in WEIGHTS:
        if name == "baseline":
            continue
        overlaps = []
        identical = 0
        for query in QUERIES:
            base = sensitivity[query]["baseline"]["isbns"][1:]
            variant = sensitivity[query][name]["isbns"][1:]
            overlap = len(set(base) & set(variant)) / 3
            overlaps.append(overlap)
            identical += base == variant
        summary[name] = {
            "mean_later_stage_overlap": round(statistics.mean(overlaps), 3),
            "identical_routes_out_of_8": identical,
            "changed_routes_out_of_8": len(QUERIES) - identical,
        }

    evidence = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "environment": {
            "operating_system": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "sentence_transformers": __import__("sentence_transformers").__version__,
        },
        "catalogue_quality": catalogue_quality(),
        "scalability": ranking_scalability(query_embeddings[0]),
        "weight_sensitivity": {
            "queries": QUERIES,
            "weights": WEIGHTS,
            "summary": summary,
            "routes": sensitivity,
        },
    }
    OUTPUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
