import os
os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"

import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Optional, List

CACHE_THRESHOLD = 0.90
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model = SentenceTransformer(EMBEDDING_MODEL)

FAQ_ENTRIES = [
    {
        "question": "What is the standard tuning for a guitar?",
        "answer": "The standard tuning for a six-string guitar is E2 A2 D3 G3 B3 E4, from the lowest (thickest) string to the highest (thinnest). This is also known as EADGBE tuning. Alternate tunings like Drop D (DADGBE), Open G (DGDGBD), and DADGAD are popular in specific genres.",
    },
    {
        "question": "How many keys does a piano have?",
        "answer": "A standard full-size piano has 88 keys: 52 white keys and 36 black keys, spanning from A0 (27.5 Hz) to C8 (4186 Hz). Smaller keyboards may have 61 or 76 keys. Digital pianos and synthesizers come in various sizes from 25 to 88 keys.",
    },
    {
        "question": "What is the difference between acoustic and electric guitar?",
        "answer": "An acoustic guitar produces sound through a hollow body that resonates when the strings vibrate. An electric guitar uses electromagnetic pickups to convert string vibrations into an electrical signal that needs to be amplified through a speaker. Electric guitars typically have thinner strings, a solid body, and allow effects like distortion and reverb. Acoustic guitars are self-contained, portable, and require no amplification.",
    },
    {
        "question": "What is A440 tuning?",
        "answer": "A440 is the international standard tuning pitch where the A above middle C (A4) is tuned to 440 Hz. It was adopted as the ISO 16 standard in 1939. Most modern instruments and ensembles tune to A440, though historically tuning ranged from 415 Hz (Baroque period) to 466 Hz. Some European orchestras tune slightly higher, around 442-444 Hz.",
    },
    {
        "question": "How do I maintain my instrument?",
        "answer": "Instrument maintenance depends on the type. For string instruments: change strings regularly (every 1-3 months), clean the fretboard and body, control humidity (40-60%). For brass instruments: clean the mouthpiece daily, oil valves weekly, bathe the instrument monthly. For woodwinds: swab after each use, oil keys, check pads. For pianos: tune every 6 months, control humidity, keep away from direct sunlight. Always store instruments in their case when not in use.",
    },
]

_static_embeddings: Optional[np.ndarray] = None

_dynamic_entries: List[dict] = []
_dynamic_embeddings: Optional[np.ndarray] = None

MAX_DYNAMIC = 20


def _cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _warm_cache():
    texts = [faq["question"] for faq in FAQ_ENTRIES]
    return _model.encode(texts, normalize_embeddings=True)


def _get_embedding(text: str):
    return _model.encode([text], normalize_embeddings=True)[0]


def check_cache(query: str) -> Optional[str]:
    global _static_embeddings
    if _static_embeddings is None:
        _static_embeddings = _warm_cache()

    query_emb = _get_embedding(query)

    best_score = -1.0
    best_answer = None

    for i, cached_emb in enumerate(_static_embeddings):
        score = _cosine_similarity(query_emb, cached_emb)
        if score > best_score:
            best_score = score
            best_answer = FAQ_ENTRIES[i]["answer"]

    if _dynamic_embeddings is not None and _dynamic_entries:
        dynamic_limit = min(len(_dynamic_entries), len(_dynamic_embeddings))
        for i in range(dynamic_limit):
            score = _cosine_similarity(query_emb, _dynamic_embeddings[i])
            if score > best_score:
                best_score = score
                best_answer = _dynamic_entries[i]["answer"]

    if best_score >= CACHE_THRESHOLD:
        return best_answer

    return None


def add_to_cache(question: str, answer: str):
    global _dynamic_entries, _dynamic_embeddings

    if not question or not answer:
        return

    if len(_dynamic_entries) >= MAX_DYNAMIC:
        _dynamic_entries.pop(0)
        if _dynamic_embeddings is not None and len(_dynamic_embeddings) > 0:
            _dynamic_embeddings = _dynamic_embeddings[1:]

    emb = _get_embedding(question)
    _dynamic_entries.append({"question": question, "answer": answer})

    if _dynamic_embeddings is None:
        _dynamic_embeddings = np.array([emb])
    else:
        _dynamic_embeddings = np.vstack([_dynamic_embeddings, emb])


def get_cache_size() -> dict:
    return {
        "static_entries": len(FAQ_ENTRIES),
        "dynamic_entries": len(_dynamic_entries),
    }


def reset_cache(dynamic_only: bool = True) -> dict:
    global _static_embeddings, _dynamic_entries, _dynamic_embeddings

    previous_dynamic = len(_dynamic_entries)
    _dynamic_entries = []
    _dynamic_embeddings = None

    reset_static = not dynamic_only
    if reset_static:
        _static_embeddings = None

    return {
        "dynamic_entries_cleared": previous_dynamic,
        "static_embeddings_reset": reset_static,
    }
