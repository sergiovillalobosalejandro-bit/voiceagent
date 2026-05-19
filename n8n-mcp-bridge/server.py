"""
MCP Server puente entre opencode y n8n.
Expone los workflows de FinBot como herramientas MCP.
Usa HTTP transport (SSE) para conectar con opencode como MCP remoto.
"""
import base64
import json
import os
import httpx
from mcp.server.fastmcp import FastMCP

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678")
WEBHOOK_TIMEOUT = 30

mcp = FastMCP(
    "finbot-n8n-bridge",
    instructions="Puente MCP para FinBot — expone workflows de n8n como herramientas",
    host="0.0.0.0",
    port=5679,
)

@mcp.tool()
async def get_crypto_price(coin_id: str = "bitcoin", currency: str = "usd") -> dict:
    """Consulta el precio de una criptomoneda via CoinGecko (webhook n8n).
    Args:
        coin_id: ID de la cripto (ej: bitcoin, ethereum, cardano)
        currency: Moneda (ej: usd, cop, eur)
    """
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        resp = await client.post(
            f"{N8N_WEBHOOK_URL}/webhook/crypto-price",
            json={"coin_id": coin_id, "currency": currency},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def ingest_rag(url: str) -> dict:
    """Ingesta contenido de una URL para RAG: scrapea, chunkifica y genera embeddings.
    Args:
        url: URL de la pagina web a indexar
    """
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
        resp = await client.post(
            f"{N8N_WEBHOOK_URL}/webhook/rag-ingest",
            json={"url": url},
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def synthesize_speech(text: str, voice: str = "alloy") -> dict:
    """Convierte texto a audio (TTS) usando Microsoft Edge TTS gratuito.
    Devuelve JSON con audio_base64 (MP3) listo para usar.
    Args:
        text: Texto a sintetizar
        voice: Voz (alloy=en-US-Jenny, echo=en-US-Guy, fable=es-CO-Salome, onyx=es-CO-Gonzalo, nova=es-MX-Dalia, shimmer=en-US-Aria)
    """
    import ssl

    import aiohttp
    import edge_tts
    import edge_tts.communicate as comm_module

    voice_map = {
        "alloy": "en-US-JennyNeural",
        "echo": "en-US-GuyNeural",
        "fable": "es-CO-SalomeNeural",
        "onyx": "es-CO-GonzaloNeural",
        "nova": "es-MX-DaliaNeural",
        "shimmer": "en-US-AriaNeural",
    }
    edge_voice = voice_map.get(voice, "en-US-JennyNeural")

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    original_ssl_ctx = comm_module._SSL_CTX
    comm_module._SSL_CTX = ssl_context

    try:
        communicate = edge_tts.Communicate(text, edge_voice, connector=connector)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        audio_base64 = base64.b64encode(audio_data).decode("utf-8") if audio_data else ""
        return {
            "audio_base64": audio_base64,
            "format": "mp3",
            "text": text,
            "voice": voice,
        }
    finally:
        comm_module._SSL_CTX = original_ssl_ctx


@mcp.tool()
async def list_n8n_workflows() -> list:
    """Lista los workflows activos en n8n."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{N8N_WEBHOOK_URL}/healthz")
        workflows_resp = await client.get(
            f"{N8N_WEBHOOK_URL}/rest/workflows",
            headers={"accept": "application/json"},
        )
        if workflows_resp.status_code == 401:
            return [{"note": "n8n REST API requiere autenticacion. Usa los webhooks directamente."}]
        return workflows_resp.json() if workflows_resp.status_code == 200 else []


@mcp.resource("n8n://status")
async def n8n_status() -> str:
    """Estado actual de la conexion con n8n."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{N8N_WEBHOOK_URL}/healthz")
            if resp.status_code == 200:
                return json.dumps({"n8n": "online", "version": "2.14.2", "webhook_url": N8N_WEBHOOK_URL})
            return json.dumps({"n8n": "error", "status": resp.status_code})
    except Exception as e:
        return json.dumps({"n8n": "offline", "error": str(e)})


if __name__ == "__main__":
    print(f"[MCP Bridge] n8n webhook URL: {N8N_WEBHOOK_URL}")
    print("[MCP Bridge] Iniciando servidor MCP SSE en http://0.0.0.0:5679/sse ...")
    mcp.run(transport="sse")
