import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "final-evaluation"
TOPICS = [
    ("Programming", "Python programming"),
    ("Programming", "distributed systems"),
    ("Programming", "natural language processing"),
    ("Science", "quantum physics"),
    ("Science", "molecular biology"),
    ("Science", "climate science"),
    ("Humanities", "modern European history"),
    ("Humanities", "philosophy and ethics"),
    ("Humanities", "Shakespeare studies"),
    ("Business", "business strategy"),
    ("Business", "corporate finance"),
    ("Business", "operations management"),
]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def timed_request(method, path, **kwargs):
    started = time.perf_counter()
    response = requests.request(method, f"{BASE_URL}{path}", timeout=120, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return response, elapsed_ms


def latency_summary(values):
    return {
        "count": len(values),
        "mean_ms": round(statistics.fmean(values), 2),
        "median_ms": round(statistics.median(values), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "max_ms": round(max(values), 2),
    }


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    latencies = {"search": [], "roadmap": [], "replacement": []}
    checks = []

    # Warm the model and HTTP path without including this request in measurements.
    requests.get(f"{BASE_URL}/search", params={"query": "warmup"}, timeout=120).raise_for_status()

    for domain, query in TOPICS:
        query_result = {"domain": domain, "query": query}
        search_data = None
        for repeat in range(3):
            response, elapsed = timed_request("GET", "/search", params={"query": query})
            latencies["search"].append(elapsed)
            passed = response.status_code == 200
            checks.append({"query": query, "operation": f"search_{repeat + 1}", "passed": passed})
            if not passed:
                query_result.setdefault("errors", []).append(response.text)
                continue
            search_data = response.json()
            books = search_data.get("recommendations", [])
            isbns = [str(book.get("isbn")) for book in books]
            checks.extend([
                {"query": query, "operation": f"search_count_{repeat + 1}", "passed": len(books) == 5},
                {"query": query, "operation": f"search_unique_{repeat + 1}", "passed": len(isbns) == len(set(isbns))},
            ])

        if not search_data or not search_data.get("recommendations"):
            results.append(query_result)
            continue

        foundation = search_data["recommendations"][0]
        response, elapsed = timed_request(
            "GET", "/roadmap",
            params={"isbn": foundation["isbn"], "query": query},
        )
        latencies["roadmap"].append(elapsed)
        roadmap_ok = response.status_code == 200
        checks.append({"query": query, "operation": "roadmap", "passed": roadmap_ok})
        if not roadmap_ok:
            query_result.setdefault("errors", []).append(response.text)
            results.append(query_result)
            continue

        roadmap = response.json()
        route = roadmap.get("route", [])
        route_isbns = [str(book.get("isbn")) for book in route]
        checks.extend([
            {"query": query, "operation": "route_length", "passed": len(route) == 4},
            {"query": query, "operation": "foundation_fixed", "passed": bool(route) and route_isbns[0] == str(foundation["isbn"])},
            {"query": query, "operation": "route_unique", "passed": len(route_isbns) == len(set(route_isbns))},
        ])

        replacement_ok = False
        if len(route) > 1:
            payload = {
                "anchor_isbn": str(foundation["isbn"]),
                "query": query,
                "stage": route[1]["stage"],
                "used_isbns": route_isbns,
                "rejected_isbns": [],
            }
            replace_response, replace_elapsed = timed_request("POST", "/roadmap/replace", json=payload)
            latencies["replacement"].append(replace_elapsed)
            replacement_ok = replace_response.status_code == 200
            if replacement_ok:
                replacement = replace_response.json()
                replacement_ok = replacement.get("exhausted") or (
                    str(replacement.get("isbn")) not in set(route_isbns)
                    and replacement.get("stage") == route[1]["stage"]
                )
            checks.append({"query": query, "operation": "replacement", "passed": replacement_ok})

        query_result.update({
            "catalogue_size": search_data.get("catalogue_size"),
            "topic_coverage": search_data.get("topic_coverage"),
            "route_length": len(route),
            "replacement_valid": replacement_ok,
        })
        results.append(query_result)

    passed = sum(check["passed"] for check in checks)
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "catalogue_size": max((item.get("catalogue_size") or 0 for item in results), default=0),
        "topics_tested": len(TOPICS),
        "requests_measured": sum(len(values) for values in latencies.values()),
        "checks_passed": passed,
        "checks_total": len(checks),
        "reliability_rate": round(passed / len(checks), 4),
        "latency": {name: latency_summary(values) for name, values in latencies.items()},
        "queries": results,
        "failed_checks": [check for check in checks if not check["passed"]],
    }
    (OUTPUT_DIR / "final_reliability_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    md = [
        "# EduGPS final reliability and latency test",
        "",
        f"- Catalogue size: {report['catalogue_size']} books",
        f"- Topics tested: {report['topics_tested']} across four domains",
        f"- Measured API requests: {report['requests_measured']}",
        f"- Functional checks passed: {passed}/{len(checks)} ({report['reliability_rate']:.1%})",
        "",
        "## Latency",
        "",
        "| Operation | Requests | Mean | Median | P95 | Maximum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, values in report["latency"].items():
        md.append(
            f"| {name.title()} | {values['count']} | {values['mean_ms']:.2f} ms | "
            f"{values['median_ms']:.2f} ms | {values['p95_ms']:.2f} ms | {values['max_ms']:.2f} ms |"
        )
    md.extend([
        "",
        "## Scope and interpretation",
        "",
        "Measurements were collected sequentially against a warm local FastAPI deployment. "
        "They exclude Google Books ingestion time and therefore represent interactive search, "
        "roadmap, and replacement performance after catalogue data is available.",
        "",
        "## Failed checks",
        "",
        "None." if not report["failed_checks"] else "\n".join(
            f"- {item['query']}: {item['operation']}" for item in report["failed_checks"]
        ),
    ])
    (OUTPUT_DIR / "final_reliability_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
