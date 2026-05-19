import asyncio
import io
import os
import math
import struct
import wave
import threading
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger("voice")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client = OpenAI(
    base_url=GROQ_BASE_URL,
    api_key=os.getenv("GROQ_API_KEY"),
)

VOICE_MAP = {
    "alloy": "en-US-JennyNeural",
    "echo": "en-US-GuyNeural",
    "fable": "es-CO-SalomeNeural",
    "onyx": "es-CO-GonzaloNeural",
    "nova": "es-MX-DaliaNeural",
    "shimmer": "en-US-AriaNeural",
}


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename
    transcript = _client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=buffer,
        response_format="text",
    )
    return transcript.strip()


def _tts_edge(text: str, voice: str) -> bytes:
    import ssl
    import aiohttp
    import edge_tts

    edge_voice = VOICE_MAP.get(voice, "en-US-JennyNeural")

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async def _stream():
        try:
            try:
                communicate = edge_tts.Communicate(text, edge_voice, connector=connector)
            except TypeError:
                communicate = edge_tts.Communicate(text, edge_voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        finally:
            await connector.close()

    return asyncio.run(_stream())


def _tts_gtts(text: str, lang: str) -> bytes:
    from gtts import gTTS
    mp3_buffer = io.BytesIO()
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.write_to_fp(mp3_buffer)
    return mp3_buffer.getvalue()


def synthesize_speech(text: str, voice: str = "alloy") -> bytes:
    result = {"data": None}

    def _run():
        try:
            result["data"] = _tts_edge(text, voice)
        except Exception as e:
            logger.warning(f"Edge TTS failed: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=15)

    if result["data"]:
        return result["data"]

    try:
        lang = "es" if any(c in text for c in "áéíóúüñÁÉÍÓÚÜÑ") else "en"
        return _tts_gtts(text, lang)
    except Exception as e:
        logger.warning(f"gTTS failed: {e}")
        return _build_fallback_audio(text)


def _build_fallback_audio(text: str) -> bytes:
    sample_rate = 16000
    duration_sec = max(1.0, min(3.0, len(text) / 60.0))
    frequency = 440.0
    amplitude = 12000
    total_samples = int(sample_rate * duration_sec)

    pcm = bytearray()
    for i in range(total_samples):
        value = int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate)))
        pcm.extend(struct.pack("<h", value))

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(pcm))
    return output.getvalue()
