"""Transparent keyword-retrieval baseline for comparison with BERT search."""

from dataclasses import dataclass

from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class TfidfIndex:
    vectorizer: TfidfVectorizer
    document_matrix: csr_matrix


def _document_text(book: dict) -> str:
    """Use the same primary evidence as BERT: the book abstract."""
    abstract = str(book.get("abstract") or "").strip()
    return abstract or str(book.get("title") or "").strip()


def build_tfidf_index(books: list[dict]) -> TfidfIndex | None:
    if not books:
        return None

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(_document_text(book) for book in books)
    return TfidfIndex(vectorizer=vectorizer, document_matrix=matrix)


def rank_tfidf(query: str, index: TfidfIndex, limit: int = 5) -> list[tuple[int, float]]:
    clean_query = query.strip()
    if not clean_query or limit <= 0:
        return []

    query_vector = index.vectorizer.transform([clean_query])
    scores = cosine_similarity(query_vector, index.document_matrix).ravel()
    ranked_indices = scores.argsort()[::-1][:limit]
    return [(int(book_index), float(scores[book_index])) for book_index in ranked_indices]
