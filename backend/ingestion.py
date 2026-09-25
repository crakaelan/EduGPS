import requests
import json
import re
import sys
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

DATA_FILE = Path(__file__).with_name("processed_books.json")

def normalise_identity(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()

def book_identity(book):
    """Return stable ISBN and title/author identities for cross-search deduplication."""
    isbn_key = re.sub(r'[^a-z0-9]+', '', str(book.get('isbn') or '').lower())
    edition_key = (
        normalise_identity(str(book.get('title') or '')),
        tuple(sorted(
            normalise_identity(str(author))
            for author in (book.get('authors') or [])
        )),
    )
    return isbn_key, edition_key

def merge_catalogues(existing_books, incoming_books, query):
    """Merge a fetched topic cohort into the persistent catalogue."""
    merged = [dict(book) for book in existing_books]
    isbn_lookup = {}
    edition_lookup = {}
    for index, book in enumerate(merged):
        isbn_key, edition_key = book_identity(book)
        if isbn_key and isbn_key != 'na':
            isbn_lookup[isbn_key] = index
        if edition_key[0]:
            edition_lookup[edition_key] = index

    topic = " ".join(query.split())
    added_count = 0
    for incoming in incoming_books:
        isbn_key, edition_key = book_identity(incoming)
        match_index = isbn_lookup.get(isbn_key) if isbn_key and isbn_key != 'na' else None
        if match_index is None:
            match_index = edition_lookup.get(edition_key)
        if match_index is not None:
            topics = list(merged[match_index].get('topics') or [])
            if topic and normalise_identity(topic) not in {
                normalise_identity(value) for value in topics
            }:
                topics.append(topic)
            merged[match_index]['topics'] = topics
            continue

        new_book = dict(incoming)
        new_book['topics'] = [topic] if topic else []
        merged.append(new_book)
        new_index = len(merged) - 1
        if isbn_key and isbn_key != 'na':
            isbn_lookup[isbn_key] = new_index
        if edition_key[0]:
            edition_lookup[edition_key] = new_index
        added_count += 1
    return merged, added_count

def write_json_atomic(path, data):
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as temp:
        json.dump(data, temp, indent=2, ensure_ascii=False)
        temp_path = Path(temp.name)
    temp_path.replace(path)

def clean_text(text):
    """"Clean the input text by removing HTML tags and special characters."""
    if not text: return ""
    clean = re.sub(r'<.*?>', '', text)  # Remove HTML tags
    return " ".join(clean.split())  # Remove extra whitespace

def fetch_books(query, start_index=0, max_results=40):
    params = {
        "q": query,
        "startIndex": start_index,
        "maxResults": max_results,
    }
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
    if api_key:
        params["key"] = api_key

    for attempt in range(3):
        response = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params,
            timeout=20,
        )
        if response.status_code == 429:
            raise RuntimeError(
                "Google Books rate limit reached. Check GOOGLE_BOOKS_API_KEY and try again later."
            )
        if response.status_code not in {500, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        if attempt < 2:
            time.sleep(2 ** attempt)

    response.raise_for_status()

def ingest(query, target_count=40):
    processed_data = []
    seen_isbns = set()
    seen_editions = set()

    # Google Books returns at most 40 records per request. Paginate until the
    # requested catalogue size is reached or the API has no more results.
    for start_index in range(0, target_count * 2, 40):
        try:
            items = fetch_books(query, start_index).get('items', [])
        except requests.RequestException:
            # A later page should not discard usable records from earlier pages.
            if processed_data:
                print(f'Warning: stopped at Google Books page {start_index // 40 + 1}.')
                break
            raise
        if not items:
            break

        for item in items:
            vol_info = item.get('volumeInfo', {})
            abstract = clean_text(vol_info.get('description', ''))
            identifiers = vol_info.get('industryIdentifiers', [])
            isbn = next(
                (entry.get('identifier') for entry in identifiers
                 if entry.get('type') == 'ISBN_13'),
                next((entry.get('identifier') for entry in identifiers), item.get('id', 'N/A'))
            )
            isbn_key = normalise_identity(str(isbn))
            edition_key = (
                normalise_identity(vol_info.get('title', '')),
                tuple(sorted(normalise_identity(author) for author in vol_info.get('authors', [])))
            )

            if (len(abstract) < 50 or isbn_key in seen_isbns
                    or edition_key in seen_editions):
                continue

            seen_isbns.add(isbn_key)
            seen_editions.add(edition_key)
            processed_data.append({
                "title": vol_info.get('title', 'N/A'),
                "authors": vol_info.get('authors', []) or ["Unknown Author"],
                "abstract": abstract,
                "isbn": isbn,
                "published_date": vol_info.get('publishedDate', ''),
                "thumbnail": vol_info.get('imageLinks', {}).get('thumbnail', '').replace('http://', 'https://'),
                "book_url": vol_info.get('infoLink')
                    or vol_info.get('previewLink')
                    or f"https://books.google.com/books?id={item.get('id', '')}"
            })
            if len(processed_data) >= target_count:
                break

        if len(processed_data) >= target_count:
            break

    if not processed_data:
        raise RuntimeError(f"No books with usable abstracts were found for '{query}'.")

    if DATA_FILE.exists():
        with DATA_FILE.open('r', encoding='utf-8') as stream:
            existing_data = json.load(stream)
    else:
        existing_data = []
    merged_data, added_count = merge_catalogues(existing_data, processed_data, query)
    write_json_atomic(DATA_FILE, merged_data)
    print(
        f'Fetched {len(processed_data)} usable books; added {added_count}; '
        f'catalogue now contains {len(merged_data)} books.'
    )
    return len(merged_data)
        
if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        raise SystemExit("Usage: python ingestion.py <topic>")
    ingest(query)
