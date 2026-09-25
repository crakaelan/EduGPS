import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer, util

import ingestion
from ranking import select_candidate, stage_metadata_scores, title_family, title_family_exclusions


DOMAINS = {
    "programming": "Python programming",
    "science": "quantum physics",
    "humanities": "modern European history",
    "business": "business strategy",
}

STAGES = [
    ("Foundation", "introductory fundamentals concepts beginner overview"),
    ("Core understanding", "core theory principles comprehensive explanation"),
    ("Applied practice", "practical projects examples implementation exercises"),
    ("Deeper study", "advanced in-depth specialist reference architecture"),
]


def duplicate_count(books):
    seen = set()
    duplicates = 0
    for book in books:
        identity = (
            ingestion.normalise_identity(book.get("title", "")),
            tuple(sorted(ingestion.normalise_identity(author) for author in book.get("authors", []))),
        )
        if identity in seen:
            duplicates += 1
        seen.add(identity)
    return duplicates


def test_domain(domain, query, model, target_count):
    result = {"domain": domain, "query": query, "api_failure": None}
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "books.json"
            original_path = ingestion.DATA_FILE
            ingestion.DATA_FILE = output_path
            try:
                ingestion_started = time.perf_counter()
                ingestion.ingest(query, target_count=target_count)
                result["ingestion_ms"] = round((time.perf_counter() - ingestion_started) * 1000, 1)
            finally:
                ingestion.DATA_FILE = original_path
            books = json.loads(output_path.read_text(encoding="utf-8"))

        result["catalogue_size"] = len(books)
        result["duplicate_count"] = duplicate_count(books)

        embedding_started = time.perf_counter()
        embeddings = model.encode([book["abstract"] for book in books], convert_to_tensor=True)
        result["embedding_ms"] = round((time.perf_counter() - embedding_started) * 1000, 1)

        search_started = time.perf_counter()
        query_embedding = model.encode(query, convert_to_tensor=True)
        topic_scores = util.cos_sim(query_embedding, embeddings)[0]
        ranked = torch.argsort(topic_scores, descending=True).tolist()
        top_indices = ranked[:min(5, len(ranked))]
        result["search_ms"] = round((time.perf_counter() - search_started) * 1000, 1)
        result["top_recommendations"] = [
            {"title": books[index]["title"], "score": round(float(topic_scores[index]), 3)}
            for index in top_indices
        ]

        route_started = time.perf_counter()
        anchor_index = top_indices[0]
        candidate_pool = set(ranked[:min(20, len(ranked))])
        stage_embeddings = model.encode(
            [f"{query}: {prompt}" for _, prompt in STAGES], convert_to_tensor=True
        )
        stage_scores = util.cos_sim(stage_embeddings, embeddings)
        selected = [anchor_index]
        route = []
        for stage_index, (stage_name, _) in enumerate(STAGES):
            choice, components = select_candidate(
                topic_scores, stage_scores[stage_index], embeddings, selected, candidate_pool,
                title_family_exclusions(books, selected),
                stage_metadata_scores(books, stage_name)
            )
            if choice is None:
                break
            selected.append(choice)
            route.append({
                "stage": stage_name,
                "title": books[choice]["title"],
                "topic_score": round(components[0], 3),
                "stage_score": round(components[1], 3),
                "metadata_stage_signal": round(components[2], 3),
            })
        result["route_ms"] = round((time.perf_counter() - route_started) * 1000, 1)
        result["route_length"] = len(route)
        result["route"] = route
        result["repeated_title_families"] = len(route) - len({
            title_family(item["title"]) for item in route
        })

        unused_pool = candidate_pool - set(selected)
        replacement_capacity = min(3, len(unused_pool))
        result["replacement_options_per_stage_upper_bound"] = replacement_capacity
        result["replacement_exhaustion_risk"] = replacement_capacity < 3
        result["relevance_warnings"] = [
            item["title"] for item in route if item["topic_score"] < 0.25
        ]
        result["top5_low_relevance_count"] = sum(
            1 for index in top_indices if float(topic_scores[index]) < 0.25
        )
    except Exception as error:
        result["api_failure"] = f"{type(error).__name__}: {error}"
    result["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Run non-destructive EduGPS domain smoke tests.")
    parser.add_argument("--target-count", type=int, default=30)
    parser.add_argument("--output", default=str(Path(__file__).with_name("smoke_test_results.json")))
    args = parser.parse_args()

    if not os.getenv("GOOGLE_BOOKS_API_KEY"):
        raise SystemExit("GOOGLE_BOOKS_API_KEY is not configured in this terminal.")

    model = SentenceTransformer("all-MiniLM-L6-v2")
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_count_per_domain": args.target_count,
        "domains": [
            test_domain(domain, query, model, args.target_count)
            for domain, query in DOMAINS.items()
        ],
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
