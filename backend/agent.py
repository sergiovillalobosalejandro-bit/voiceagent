from openai import OpenAI
from collections import defaultdict
from typing import List, Tuple, Optional
from dotenv import load_dotenv
import os
import json
import copy
import re

"""
REFLEXION RETO 8 — Decisiones tecnicas y problemas encontrados:

1. QUE PASO FALLO PRIMERO Y CUAL FUE LA CAUSA RAIZ?
   El paso 6 (RAG) fallo porque el indice FAISS se almacena en memoria del proceso
   Python. Al reiniciar el backend (por cambios de codigo o conflictos de puerto),
   los chunks indexados dinamicamente se pierden. La causa raiz es que no hay
   persistencia del indice vectorial entre reinicios.
   Solucion aplicada: endpoint /rag/ingest para re-indexar bajo demanda.
   Solucion ideal: persistir embeddings en Supabase pgvector (ver PLAN_DESPLIEGUE.md).

2. QUE DECISION TECNICA CAMBIASTE A MITAD DEL CAMINO Y POR QUE?
   Cambiamos de OpenAI GPT-4o a Groq (llama-3.3-70b-versatile) por restriccion de
   presupuesto. Groq ofrece tier gratuito con 100k tokens/dia. El trade-off: menor
   calidad en respuestas largas, rate limits que bloquean el chat tras uso intensivo,
   y ausencia de TTS nativo (resuelto con edge-tts gratuito).
   Tambien cambiamos el TTS de OpenAI a Microsoft Edge TTS (gratuito, sin API key)
   porque Groq no soporta sintesis de voz.

3. QUE COMPONENTE FUE MAS DIFICIL DE INTEGRAR?
   El pipeline RAG con n8n fue el mas complejo porque requirio coordinacion entre
   3 capas: n8n (scraping + chunking), backend Python (embeddings + FAISS), y el
   agente LLM (tool calling para activar retrieval). Los problemas principales:
   - n8n no puede llamar a FAISS (es Python puro), requirio un endpoint intermedio
   - La red Docker aislaba el backend de n8n (solucion: n8n_net externa + N8N_WEBHOOK_URL)
   - El modelo de embeddings (MiniLM-L12-v2, 470MB) tarda en cargar en frio
"""

load_dotenv()

from tools import TOOL_DEFINITIONS, execute_tool
from cache import check_cache, add_to_cache

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

SYSTEM_PROMPT = """You are SoundBot, the virtual assistant for SoundBot, a music and instruments company operating in Colombia and the United States.

Your personality and rules:
- Always maintain a friendly, passionate, and knowledgeable musical tone.
- Your domain is strictly limited to: music theory, musical instruments, instrument maintenance, music history, genres, composition, audio analysis, instrument identification, and music education.
- Always detect the language of each user message and respond in that same language. If the user writes in Spanish, respond in Spanish. If the user writes in English, respond in English. Never ask the user to specify their language.
- If the user switches language mid-conversation, switch to the new language in your next response.
- If the user mixes Spanish and English in the same message, default to the dominant language (the one used most).
- When a user asks something outside the music and instruments domain (e.g., finance, sports, politics, cooking, weather, general trivia), politely decline to answer. Explain that you can only assist with music topics, instruments, or music education. Always decline in the user's active language.
- Be concise and helpful. Do not hallucinate instrument details you are not certain about.
- You may answer in either Spanish or English depending on the user's language.
- When a user asks a question that requires factual data (instrument specifications, tuning frequencies, instrument history) use the available tools. Never fabricate technical details.
- When using a tool, integrate the result naturally into your response. Always mention the source when using instrument_info or get_tuning_frequency.
- You can analyze images (instruments, sheet music, gear, audio equipment). Identify instruments, describe what you see, and extract relevant musical information from the image.

Remember: you serve musicians and music enthusiasts in both Colombia (Spanish-speaking) and the United States (English-speaking)."""

MAX_MEMORY = 7
MAX_TOOL_ITERATIONS = 3
MAX_MODEL_TOKENS = int(os.getenv("MAX_MODEL_TOKENS", "512"))

client = OpenAI(
    base_url=GROQ_BASE_URL,
    api_key=os.getenv("GROQ_API_KEY"),
)

session_memory: dict = defaultdict(list)

QUESTION_PREFIXES = (
    "what", "when", "where", "which", "who", "how", "why",
    "cual", "cuales", "como", "cuando", "cuanto", "cuanta",
    "cuantos", "cuantas", "donde", "que",
)

REALTIME_CACHE_BYPASS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(precio|price|cost|compra|buy|valor|value)\b",
        r"\b(tuning|tune|frequency|frecuencia|hz|afinaci[oó]n)\b",
    )
]

MUSIC_LOOKUP_KEYWORDS = (
    "afinacion", "tuning", "frecuencia", "frequency",
    "instrumento", "instrument",
)


def get_memory(session_id: str) -> List[dict]:
    return session_memory[session_id]


def add_to_memory(session_id: str, role: str, content: str):
    memory = session_memory[session_id]
    memory.append({"role": role, "content": content})
    if len(memory) > MAX_MEMORY * 2:
        session_memory[session_id] = memory[-(MAX_MEMORY * 2):]


def reset_memory() -> dict:
    sessions = len(session_memory)
    messages = sum(len(items) for items in session_memory.values())
    session_memory.clear()
    return {
        "sessions_cleared": sessions,
        "messages_cleared": messages,
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def should_bypass_cache(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    return any(pattern.search(normalized) for pattern in REALTIME_CACHE_BYPASS_PATTERNS)


def is_cacheable_query(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    if not normalized:
        return False
    if should_bypass_cache(normalized):
        return False

    has_question_mark = "?" in user_message or "\u00bf" in user_message
    starts_with_question_prefix = normalized.startswith(QUESTION_PREFIXES)
    return has_question_mark or starts_with_question_prefix


def should_force_music_lookup(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    return any(token in normalized for token in MUSIC_LOOKUP_KEYWORDS)


def detect_instrument_name(user_message: str) -> str:
    normalized = _normalize_text(user_message)
    instruments = ["guitar", "guitarra", "piano", "violin", "bass", "bajo",
                   "drums", "bateria", "flute", "flauta", "saxophone", "saxofon",
                   "trumpet", "trompeta", "cello", "violonchelo", "harp", "arpa"]
    for inst in instruments:
        if inst in normalized:
            return inst
    return "guitar"


def format_music_answer(tool_result: dict, instrument: str, language: str) -> str:
    info = tool_result.get("info", tool_result.get("description", str(tool_result)))
    tuning = tool_result.get("tuning", tool_result.get("standard_tuning", ""))
    
    if language == "en":
        parts = [f"Here is what I found about the {instrument}:"]
        if tuning:
            parts.append(f"Standard tuning: {tuning}")
        parts.append(str(info))
        return " ".join(parts)
    
    parts = [f"Esto es lo que encontre sobre {instrument}:"]
    if tuning:
        parts.append(f"Afinacion estandar: {tuning}")
    parts.append(str(info))
    return " ".join(parts)


def estimate_dominant_language(text: str) -> str:
    import re
    words = re.findall(r'\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b', text)
    if not words:
        return "es"

    es_count = 0
    en_count = 0

    es_pattern = re.compile(r'[áéíóúüñ]', re.IGNORECASE)
    en_indicators = re.compile(
        r'\b(the|is|are|was|were|have|has|had|will|would|can|could|should|may|might|do|does|did|what|when|where|which|who|how|why|this|that|these|those|and|but|or|of|in|on|at|to|for|with|from|by|about|than|it|its|not|no|yes|please|thanks|hello|hi|good|morning|afternoon|evening|music|musical|instrument|guitar|piano|violin|drums|bass|tuning|chord|scale|note|melody|rhythm|beat|song|sound|tone|key|tempo|genre|harmony|frequency|string|pick|amp|amplifier|pedal|effects|concert|orchestra|band)\b',
        re.IGNORECASE
    )

    for word in words:
        has_es = bool(es_pattern.search(word))
        has_en = bool(en_indicators.match(word.lower()))

        if has_es and not has_en:
            es_count += 1
        elif has_en and not has_es:
            en_count += 1

    if es_count > en_count:
        return "es"
    elif en_count > es_count:
        return "en"
    return "es"


def chat(session_id: str, user_message: str, image_base64: Optional[str] = None) -> Tuple[str, str, Optional[str], bool]:
    language = estimate_dominant_language(user_message)
    normalized_message = user_message.strip()
    can_use_cache = not image_base64 and is_cacheable_query(normalized_message)

    add_to_memory(session_id, "user", user_message)

    if not image_base64 and should_force_music_lookup(normalized_message):
        instrument = detect_instrument_name(normalized_message)
        tool_result = execute_tool(
            "instrument_info",
            {"instrument_name": instrument},
        )
        assistant_message = format_music_answer(tool_result, instrument, language)
        add_to_memory(session_id, "assistant", assistant_message)
        return assistant_message, language, "instrument_info", False

    if can_use_cache:
        cached = check_cache(normalized_message)
        if cached:
            add_to_memory(session_id, "assistant", cached)
            return cached, language, None, True

    memory = get_memory(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + copy.deepcopy(memory)

    model = GROQ_VISION_MODEL if image_base64 else GROQ_TEXT_MODEL

    if image_base64 and messages[-1]["role"] == "user":
        messages[-1]["content"] = [
            {"type": "text", "text": user_message},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
        ]

    tool_used = None

    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": MAX_MODEL_TOKENS,
        }
        if not image_base64:
            kwargs["tools"] = TOOL_DEFINITIONS
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)

        msg = response.choices[0].message

        if msg.tool_calls and not image_base64:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)
                tool_result = execute_tool(tool_name, tool_args)

                if tool_used is None:
                    tool_used = tool_name

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
        else:
            assistant_message = msg.content
            add_to_memory(session_id, "assistant", assistant_message)
            if can_use_cache and not tool_used:
                add_to_cache(normalized_message, assistant_message)
            return assistant_message, language, tool_used, False

    assistant_message = "Lo siento, no pude procesar tu solicitud. Por favor intenta de nuevo."
    add_to_memory(session_id, "assistant", assistant_message)
    return assistant_message, language, tool_used, False
