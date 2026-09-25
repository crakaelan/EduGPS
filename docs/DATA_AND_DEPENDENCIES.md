# Data and dependencies

The bundled catalogue contains public book metadata and descriptions obtained through Google Books. Descriptions belong to their respective rights holders; inclusion does not assert ownership of book content. Source URLs are retained where available. `embeddings.json` contains vectors for the descriptions in catalogue order. Keep these files paired.

The application uses the sentence-transformers/all-MiniLM-L6-v2 model, downloaded separately on first use, and third-party dependencies listed in the manifests and lockfiles. Their respective licences apply. No additional licence grant for third-party metadata is implied by this repository.

Do not publish API credentials, raw participant records or local feedback. Review generated outputs before sharing them.
