from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    image_base64: Optional[str] = None
    output_audio: bool = False


class ChatResponse(BaseModel):
    answer: str
    language: str
    tool_used: Optional[str] = None
    cache_hit: bool = False
    audio_base64: Optional[str] = None
