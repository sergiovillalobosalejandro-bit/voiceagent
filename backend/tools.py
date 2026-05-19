import json
import os
import httpx
from rag import query_rag, ingest_from_n8n

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678")
USD_COP_RATE = 4150.0


def calculate_interest(principal: float, rate: float, years: float) -> dict:
    amount = principal * (1 + rate / 100) ** years
    interest = amount - principal
    return {
        "principal": principal,
        "annual_rate_percent": rate,
        "years": years,
        "final_amount": round(amount, 2),
        "interest_earned": round(interest, 2),
    }


def get_usd_rate() -> dict:
    return {
        "usd_cop_rate": USD_COP_RATE,
        "source": "Tasa de referencia interna / Internal reference rate",
    }


def get_crypto_price(crypto_id: str = "bitcoin", vs_currency: str = "usd") -> dict:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{N8N_WEBHOOK_URL}/webhook/crypto-price",
                json={"coin_id": crypto_id, "currency": vs_currency},
            )
            resp.raise_for_status()
            n8n_data = resp.json()
            price_data = n8n_data.get("price", {})
            if price_data:
                return price_data
            raise ValueError("Empty price from n8n")
    except Exception:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies={vs_currency}"
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()


def search_knowledge_base(query: str) -> dict:
    chunks = query_rag(query)
    return {"retrieved_chunks": chunks}


def ingest_rag_url(url: str) -> dict:
    try:
        with httpx.Client(timeout=45) as client:
            resp = client.post(
                f"{N8N_WEBHOOK_URL}/webhook/rag-ingest",
                json={"url": url},
            )
            resp.raise_for_status()
            n8n_data = resp.json()

        if n8n_data.get("status") != "ok":
            return {"status": "error", "message": n8n_data.get("message", "Error en webhook n8n")}

        result = ingest_from_n8n(n8n_data)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_interest",
            "description": "Calcula el interés compuesto sobre una inversión. Calculate compound interest on an investment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "principal": {"type": "number", "description": "Monto principal / Principal amount"},
                    "rate": {"type": "number", "description": "Tasa de interés anual en porcentaje / Annual interest rate as percentage (e.g., 8 for 8%)"},
                    "years": {"type": "number", "description": "Número de años / Number of years"},
                },
                "required": ["principal", "rate", "years"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_usd_rate",
            "description": "Obtiene la tasa de cambio actual USD/COP. Get the current USD to COP exchange rate.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": "Obtiene el precio actual de una criptomoneda desde CoinGecko. Get the current price of a cryptocurrency from CoinGecko.",
            "parameters": {
                "type": "object",
                "properties": {
                    "crypto_id": {"type": "string", "description": "ID de la criptomoneda (e.g., bitcoin, ethereum) / Cryptocurrency ID"},
                    "vs_currency": {"type": "string", "description": "Moneda de referencia (e.g., usd, cop) / Reference currency"},
                },
                "required": ["crypto_id", "vs_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Busca información financiera en la base de conocimiento interna (CDTs, certificados de depósito, productos de ahorro e inversión). Search financial information in the internal knowledge base (CDs, certificates of deposit, savings and investment products).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La pregunta o tema a buscar / The question or topic to search"},
                },
                "required": ["query"],
            },
        },
    },
]


TOOL_MAP = {
    "calculate_interest": calculate_interest,
    "get_usd_rate": get_usd_rate,
    "get_crypto_price": get_crypto_price,
    "search_knowledge_base": search_knowledge_base,
}


def execute_tool(name: str, args: dict) -> dict:
    fn = TOOL_MAP.get(name)
    if not fn:
        return {"error": f"Tool '{name}' no encontrada / not found"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}
