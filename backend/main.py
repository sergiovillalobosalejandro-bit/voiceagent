import base64
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from models import ChatRequest, ChatResponse
from agent import chat, reset_memory
from voice import transcribe_audio, synthesize_speech
from rag import get_rag_status, reset_rag
from tools import ingest_rag_url
from cache import get_cache_size, reset_cache

app = FastAPI(title="SoundBot API")

_default_origins = "http://localhost:5173,http://localhost:3000,https://frontend-ruddy-nine-54.vercel.app"
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RagIngestRequest(BaseModel):
    url: str


class ResetRequest(BaseModel):
    reset_static: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/rag/status")
def rag_status():
    return get_rag_status()


@app.post("/rag/ingest")
def rag_ingest(req: RagIngestRequest):
    return ingest_rag_url(req.url)


@app.get("/cache/status")
def cache_status():
    return get_cache_size()


@app.post("/dev/reset")
def dev_reset(req: ResetRequest = ResetRequest()):
    dynamic_only = not req.reset_static
    return {
        "memory": reset_memory(),
        "cache": reset_cache(dynamic_only=dynamic_only),
        "rag": reset_rag(dynamic_only=dynamic_only),
    }


def _build_response(answer, language, tool_used, cache_hit, output_audio):
    audio_b64 = None
    if output_audio:
        audio_bytes = synthesize_speech(answer)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    return ChatResponse(
        answer=answer,
        language=language,
        tool_used=tool_used,
        cache_hit=cache_hit,
        audio_base64=audio_b64,
    )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    answer, language, tool_used, cache_hit = chat(
        req.session_id, req.message, req.image_base64
    )
    return _build_response(answer, language, tool_used, cache_hit, req.output_audio)


@app.post("/voice/chat", response_model=ChatResponse)
async def voice_chat_endpoint(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    output_audio: bool = Form(False),
    transcript_override: Optional[str] = Form(None),
):
    raw = await audio.read()
    transcription = (transcript_override or "").strip()
    if not transcription:
        transcription = transcribe_audio(raw, audio.filename or "audio.webm")

    answer, language, tool_used, cache_hit = chat(
        session_id, transcription, None
    )

    return _build_response(answer, language, tool_used, cache_hit, output_audio)
