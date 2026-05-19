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

SYSTEM_PROMPT = """You are FinBot, the virtual assistant for FinBot, a fintech company operating in Colombia and the United States.

Your personality and rules:
- Always maintain a formal, professional, and courteous financial tone.
- Your domain is strictly limited to: personal finance, FinBot products and services, and customer support related to financial matters.
- Always detect the language of each user message and respond in that same language. If the user writes in Spanish, respond in Spanish. If the user writes in English, respond in English. Never ask the user to specify their language.
- If the user switches language mid-conversation, switch to the new language in your next response.
- If the user mixes Spanish and English in the same message, default to the dominant language (the one used most).
- When a user asks something outside the financial domain (e.g., sports, entertainment, politics, cooking, weather, general trivia), politely decline to answer. Explain that you can only assist with financial topics, FinBot products, or support inquiries. Always decline in the user's active language.
- Be concise and helpful. Do not hallucinate product details you are not certain about.
- You may answer in either Spanish or English depending on the user's language.
- When a user asks a question that requires current data (exchange rates, cryptocurrency prices) or calculations, use the available tools. Never fabricate numbers.
- When using a tool, integrate the result naturally into your response. Always mention the source when using get_usd_rate or get_crypto_price.
- You can analyze images (receipts, invoices, financial documents, charts). Describe what you see and extract relevant financial information from the image.

Remember: you serve clients in both Colombia (Spanish-speaking) and the United States (English-speaking)."""

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
        r"\b(usd|cop|eur|rate|exchange|tipo de cambio|trm|d[oó]lar)\b",
        r"\b(bitcoin|btc|ethereum|eth|crypto|cripto|precio hoy|price today)\b",
    )
]

CRYPTO_KEYWORDS = (
    "bitcoin", "btc", "ethereum", "eth", "crypto", "criptomoneda", "cripto",
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


def should_force_crypto_tool(user_message: str) -> bool:
    normalized = _normalize_text(user_message)
    return any(token in normalized for token in CRYPTO_KEYWORDS)


def detect_crypto_id(user_message: str) -> str:
    normalized = _normalize_text(user_message)
    if "ethereum" in normalized or " eth " in f" {normalized} ":
        return "ethereum"
    return "bitcoin"


def format_crypto_answer(tool_result: dict, crypto_id: str, language: str) -> str:
    price = None
    currency = "usd"

    if isinstance(tool_result, dict):
        nested = tool_result.get(crypto_id)
        if isinstance(nested, dict):
            if "usd" in nested:
                price = nested["usd"]
                currency = "usd"
            elif nested:
                first_currency = next(iter(nested.keys()))
                price = nested[first_currency]
                currency = first_currency
        elif "price" in tool_result:
            price = tool_result.get("price")
            currency = str(tool_result.get("currency", "usd")).lower()

    if price is None:
        if language == "en":
            return "I could not retrieve the cryptocurrency price at this moment. Please try again."
        return "No pude obtener el precio de la criptomoneda en este momento. Por favor intenta de nuevo."

    coin_label = crypto_id.upper()
    currency_label = currency.upper()

    if language == "en":
        return f"The current {coin_label} price is {price} {currency_label}, based on CoinGecko data."
    return f"El precio actual de {coin_label} es {price} {currency_label}, con datos de CoinGecko."


def estimate_dominant_language(text: str) -> str:
    import re
    words = re.findall(r'\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]+\b', text)
    if not words:
        return "es"

    es_count = 0
    en_count = 0

    es_pattern = re.compile(r'[áéíóúüñ]', re.IGNORECASE)
    en_indicators = re.compile(
        r'\b(the|is|are|was|were|have|has|had|will|would|can|could|should|may|might|do|does|did|what|when|where|which|who|how|why|this|that|these|those|and|but|or|of|in|on|at|to|for|with|from|by|about|than|it|its|not|no|yes|please|thanks|hello|hi|good|morning|afternoon|evening|rate|price|exchange|dollar|currency|investment|bank|account|transfer|payment|balance|credit|debit|loan|mortgage|tax|taxes|budget|savings|interest|stock|market|crypto|bitcoin|ethereum|wallet|transaction|fee|fees)\b',
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

    if not image_base64 and should_force_crypto_tool(normalized_message):
        crypto_id = detect_crypto_id(normalized_message)
        tool_result = execute_tool(
            "get_crypto_price",
            {"crypto_id": crypto_id, "vs_currency": "usd"},
        )
        assistant_message = format_crypto_answer(tool_result, crypto_id, language)
        add_to_memory(session_id, "assistant", assistant_message)
        return assistant_message, language, "get_crypto_price", False

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
