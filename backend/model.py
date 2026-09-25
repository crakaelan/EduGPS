import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from sentence_transformers import SentenceTransformer
    
BASE_DIR = Path(__file__).resolve().parent

# Load the BERT-based model
# Here we use 'all-MiniLM-L6-v2' for efficient sentence embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')

def create_embeddings():
    # Load processed data
    with (BASE_DIR / 'processed_books.json').open('r', encoding='utf-8') as f:
        books = json.load(f)

    # Extract just the abstracts
    abstracts = [book['abstract'] for book in books]

    # Generate embeddings (vector representations) for the abstracts
    print("Generating embeddings for abstracts...")
    embeddings = model.encode(abstracts, show_progress_bar=True)

    # Convert to list and save it as JSON
    output_path = BASE_DIR / 'embeddings.json'
    with NamedTemporaryFile('w', encoding='utf-8', dir=BASE_DIR, delete=False) as temp:
        json.dump(embeddings.tolist(), temp)
        temp_path = Path(temp.name)
    temp_path.replace(output_path)
    print("Embeddings created and saved to embeddings.json")

if __name__ == "__main__":
    create_embeddings()
