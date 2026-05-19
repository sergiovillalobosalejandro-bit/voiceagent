import os
os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"

import re
import httpx
import numpy as np
import faiss
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from typing import Optional, List

RAG_URL = "https://en.wikipedia.org/wiki/Musical_instrument"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 60
TOP_K = 3
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

FALLBACK_TEXT = """
A musical instrument is a device created or adapted to make musical sounds. In principle, any object that
produces sound can be considered a musical instrument. The history of musical instruments dates to the
beginnings of human culture. Early musical instruments may have been used for rituals and communication.

Musical instruments are classified into families based on how they produce sound:
- String instruments (chordophones): guitar, violin, piano, harp, bass. Sound is produced by vibrating strings.
- Wind instruments (aerophones): flute, saxophone, trumpet, clarinet, trombone. Sound is produced by vibrating air.
- Percussion instruments (membranophones and idiophones): drums, xylophone, cymbals, marimba. Sound is produced by striking.
- Electronic instruments (electrophones): synthesizer, theremin, electric guitar. Sound is produced electronically.

The guitar is a fretted string instrument with six strings. Standard tuning is EADGBE. It is used in virtually
all genres including rock, pop, jazz, classical, and blues. The acoustic guitar produces sound through a hollow
resonating body, while the electric guitar uses pickups and requires amplification.

The piano is a keyboard instrument with 88 keys. When a key is pressed, a felt hammer strikes tuned strings.
Invented around 1700 by Bartolomeo Cristofori, it is one of the most versatile instruments, capable of playing
melody, harmony, and bass simultaneously. It is central to classical music, jazz, and popular music.

The violin is a bowed string instrument with four strings tuned in perfect fifths (GDAE). It is the smallest
and highest-pitched instrument in the violin family, which also includes viola, cello, and double bass.
It is essential in classical orchestras and widely used in folk, jazz, and contemporary music.

A440 (A4 = 440 Hz) is the international standard tuning pitch adopted as ISO 16. Most modern orchestras and
instruments tune to this reference frequency. Historically, tuning standards varied significantly, from as
low as 415 Hz in Baroque period to 466 Hz in some modern European orchestras.

Drums are percussion instruments that provide the rhythmic foundation in most music. A standard drum kit
includes bass drum, snare, hi-hat, toms, and cymbals. The bass guitar (4 strings, EADG tuning one octave
below guitar) bridges rhythm and harmony, essential in funk, rock, and pop.

The flute is a woodwind instrument that produces sound from the flow of air across an opening. The saxophone
is a single-reed woodwind with a conical brass body, invented in the 1840s by Adolphe Sax, prominent in jazz.
The trumpet is a brass instrument with the highest register in its family, using three piston valves.
"""

_model = SentenceTransformer(EMBEDDING_MODEL)

_static_chunks: Optional[List[str]] = None
_static_index: Optional[faiss.IndexFlatIP] = None

_dynamic_chunks: Optional[List[str]] = None
_dynamic_index: Optional[faiss.IndexFlatIP] = None
_dynamic_source_url: Optional[str] = None


def _scrape(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "sup", "table"]):
            tag.decompose()
        text = soup.get_text()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception:
        return FALLBACK_TEXT


def _split_sentences(text: str) -> list:
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if len(s.strip()) > 20]


def _build_chunks(sentences: list, chunk_size: int, overlap: int) -> list:
    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) <= chunk_size:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)

    if len(chunks) < 3:
        return chunks

    overlapped = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        tail = prev[-overlap:] if len(prev) >= overlap else prev
        overlapped.append((tail + " " + chunks[i]).strip())

    return overlapped


def _build_index(chunks: List[str]) -> faiss.IndexFlatIP:
    embs = _model.encode(chunks, normalize_embeddings=True).astype(np.float32)
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)
    return index


def _warm_static_index():
    global _static_chunks, _static_index

    if _static_chunks is not None:
        return

    text = _scrape(RAG_URL)
    sentences = _split_sentences(text)
    _static_chunks = _build_chunks(sentences, CHUNK_SIZE, CHUNK_OVERLAP)
    _static_index = _build_index(_static_chunks)


def ingest_chunks(chunks_data: List[dict], source_url: str = "") -> dict:
    global _dynamic_chunks, _dynamic_index, _dynamic_source_url

    texts = [c.get("text", "") for c in chunks_data if c.get("text", "").strip()]
    if len(texts) < 3:
        return {"status": "error", "message": f"Se requieren al menos 3 chunks con contenido. Recibidos: {len(texts)}"}

    _dynamic_chunks = texts
    _dynamic_index = _build_index(texts)
    _dynamic_source_url = source_url

    return {
        "status": "ok",
        "chunks_indexed": len(texts),
        "source_url": source_url,
    }


def ingest_from_n8n(webhook_response: dict) -> dict:
    chunks = webhook_response.get("chunks", [])
    source_url = webhook_response.get("source_url", "")

    if not chunks:
        raw_content = webhook_response.get("content_preview", "")
        content_length = webhook_response.get("content_length", 0)
        if raw_content and content_length > 100:
            sentences = _split_sentences(raw_content)
            built_chunks = _build_chunks(sentences, CHUNK_SIZE, CHUNK_OVERLAP)
            if len(built_chunks) >= 3:
                chunks = [{"text": c, "chunk_index": i} for i, c in enumerate(built_chunks)]

    if not chunks or len(chunks) < 3:
        return {"status": "error", "message": "No se pudieron generar suficientes chunks del contenido"}

    return ingest_chunks(chunks, source_url)


def query_rag(question: str) -> str:
    _warm_static_index()

    chunks = _dynamic_chunks if _dynamic_chunks is not None else _static_chunks
    index = _dynamic_index if _dynamic_index is not None else _static_index

    q_emb = _model.encode([question], normalize_embeddings=True).astype(np.float32)
    scores, indices = index.search(q_emb, TOP_K)

    retrieved = []
    for idx in indices[0]:
        if 0 <= idx < len(chunks):
            retrieved.append(chunks[idx])

    return "\n\n---\n\n".join(retrieved)


def get_rag_status() -> dict:
    return {
        "static_chunks": len(_static_chunks) if _static_chunks else 0,
        "dynamic_chunks": len(_dynamic_chunks) if _dynamic_chunks else 0,
        "dynamic_source_url": _dynamic_source_url,
    }


def reset_rag(dynamic_only: bool = True) -> dict:
    global _dynamic_chunks, _dynamic_index, _dynamic_source_url
    global _static_chunks, _static_index

    previous_dynamic = len(_dynamic_chunks) if _dynamic_chunks else 0
    _dynamic_chunks = None
    _dynamic_index = None
    _dynamic_source_url = None

    reset_static = not dynamic_only
    if reset_static:
        _static_chunks = None
        _static_index = None

    return {
        "dynamic_chunks_cleared": previous_dynamic,
        "static_index_reset": reset_static,
    }
