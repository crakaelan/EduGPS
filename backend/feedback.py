"""Small, transparent preference store for the local research prototype."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import torch


MAX_SCORE_ADJUSTMENT = 0.04


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


class FeedbackStore:
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def record(self, query: str, isbn: str, vote: int) -> dict:
        if vote not in (-1, 0, 1):
            raise ValueError("Vote must be -1, 0, or 1.")
        clean_query = normalize_query(query)
        clean_isbn = isbn.strip()
        if not clean_query or not clean_isbn:
            raise ValueError("Query and ISBN are required.")

        entries = self._load()
        key = f"{clean_query}|{clean_isbn}"
        saved = {
            "query": clean_query,
            "isbn": clean_isbn,
            "vote": vote,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if vote == 0:
            entries.pop(key, None)
        else:
            entries[key] = saved
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as temp:
            json.dump(entries, temp, indent=2, ensure_ascii=False)
            temporary_path = Path(temp.name)
        temporary_path.replace(self.path)
        return saved

    def votes_for_query(self, query: str) -> dict[str, int]:
        clean_query = normalize_query(query)
        return {
            entry["isbn"]: int(entry["vote"])
            for entry in self._load().values()
            if entry.get("query") == clean_query and entry.get("vote") in (-1, 1)
        }


def calibrated_scores(
    raw_scores: torch.Tensor,
    books: list[dict],
    query: str,
    store: FeedbackStore,
) -> tuple[torch.Tensor, dict[str, int]]:
    """Apply a deliberately small exact-query preference adjustment."""
    votes = store.votes_for_query(query)
    adjusted = raw_scores.clone().float()
    for index, book in enumerate(books):
        isbn = str(book.get("isbn") or "")
        adjusted[index] += MAX_SCORE_ADJUSTMENT * votes.get(isbn, 0)
    return adjusted, votes
