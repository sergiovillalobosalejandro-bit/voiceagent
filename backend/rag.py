import os
os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"

import re
import httpx
import numpy as np
import faiss
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer
from typing import Optional, List

RAG_URL = "https://en.wikipedia.org/wiki/Certificate_of_deposit"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 60
TOP_K = 3
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

FALLBACK_TEXT = """
A certificate of deposit (CD) is a time deposit sold by banks, thrift institutions, and credit unions.
CDs are similar to savings accounts in that they are insured "money in the bank" and thus virtually risk-free.
They differ from savings accounts in that the CD has a specific, fixed term (often three months, six months,
or one to five years) and usually a fixed interest rate. The bank expects the CD to be held until maturity,
at which time the funds can be withdrawn together with accrued interest.

In exchange for the customer depositing the money for an agreed term, institutions usually offer higher
interest rates than they do on accounts from which customers may withdraw on demand. The customer must
understand that the penalty for early withdrawal could be high.

CDs are available in various terms from 1 month to 10 years. The interest rate is typically fixed for
the term of the CD. Some CDs have variable rates or rates tied to an index such as the stock market.
CDs are generally issued by commercial banks and are insured by the FDIC up to $250,000 per depositor.

In Colombia, CDs are known as CDTs (Certificados de Depósito a Término). Colombian CDTs are issued by
banks and financial institutions, offering fixed interest rates for terms typically ranging from 30 to
360 days, though longer terms are available. The minimum investment amount varies by institution but
typically starts around $500,000 COP.

CDTs in Colombia are considered low-risk investments. The interest earned is subject to withholding tax
(retención en la fuente). Rates vary based on the term length, the amount invested, and market conditions.
As of recent data, CDT rates in Colombia range from 8% to 12% annually depending on the term and institution.
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
