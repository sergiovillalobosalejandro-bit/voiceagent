import os

os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFY", "1")

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_encoder = None


def get_encoder():
    """Carga el modelo una sola vez (compartido entre cache y RAG)."""
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(EMBEDDING_MODEL)
    return _encoder
