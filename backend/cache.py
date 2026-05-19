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
        "question": "¿Cuál es el horario de atención de FinBot?",
        "answer": "Nuestro horario de atención es de lunes a viernes de 8:00 a.m. a 6:00 p.m. y sábados de 9:00 a.m. a 1:00 p.m., hora colombiana. Para clientes en Estados Unidos, ofrecemos soporte telefónico 24/7.",
    },
    {
        "question": "¿Cómo puedo abrir una cuenta en FinBot?",
        "answer": "Para abrir una cuenta en FinBot, descargue nuestra app, complete el formulario con sus datos personales, verifique su identidad con su documento oficial y realice un depósito inicial mínimo de $50,000 COP o $10 USD.",
    },
    {
        "question": "¿Qué documentos necesito para solicitar un préstamo?",
        "answer": "Para solicitar un préstamo en FinBot necesita: documento de identidad vigente, comprobante de ingresos de los últimos 3 meses, extractos bancarios recientes y referencias personales o comerciales.",
    },
    {
        "question": "¿Cómo contacto al servicio de soporte de FinBot?",
        "answer": "Puede contactar a nuestro equipo de soporte por chat en vivo en la app, correo a soporte@finbot.co, o llamando al +57 301 732 5327 en Colombia y al +1 (305) 555-0123 en Estados Unidos.",
    },
    {
        "question": "¿FinBot cobra comisiones por transferencias internacionales?",
        "answer": "FinBot cobra una comisión del 1.5% por transferencias internacionales, con un mínimo de $5 USD. Las transferencias entre cuentas FinBot son gratuitas. Las transferencias locales en COP no tienen costo.",
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
