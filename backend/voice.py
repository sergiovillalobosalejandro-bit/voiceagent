import asyncio
import io
import os
import math
import struct
import wave
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

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


async def _synthesize_async(text: str, voice: str) -> bytes:
    import ssl

    import aiohttp
    import edge_tts

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    try:
        edge_voice = VOICE_MAP.get(voice, "en-US-JennyNeural")
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


def synthesize_speech(text: str, voice: str = "alloy") -> bytes:
    try:
        return asyncio.run(_synthesize_async(text, voice))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_synthesize_async(text, voice))
        finally:
            loop.close()
    except Exception:
        return _build_fallback_audio(text)


def _build_fallback_audio(text: str) -> bytes:
    # Fallback tone to keep the audio contract available when TTS providers fail.
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
