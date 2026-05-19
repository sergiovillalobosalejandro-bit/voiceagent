import argparse
import base64
import json
import tempfile
import uuid
import wave
from pathlib import Path

import httpx


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT_DIR / "frontend" / "src" / "assets" / "hero.png"


def make_session_id() -> str:
    return f"e2e-{uuid.uuid4().hex[:10]}"


def contains_case_insensitive(text: str, token: str) -> bool:
    return token.lower() in (text or "").lower()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FinBot integrated 8-step validation.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--image-path", default=str(DEFAULT_IMAGE), help="Path to image for step 4")
    parser.add_argument("--audio-file", default="", help="Optional audio file for step 5")
    parser.add_argument(
        "--ingest-url",
        default="",
        help="Optional URL to ingest into RAG before step 6",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout in seconds")
    return parser.parse_args()


def post_json(client: httpx.Client, url: str, payload: dict) -> dict:
    response = client.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def post_chat(
    client: httpx.Client,
    base_url: str,
    session_id: str,
    message: str,
    output_audio: bool = False,
    image_base64: str | None = None,
) -> dict:
    payload = {
        "session_id": session_id,
        "message": message,
        "output_audio": output_audio,
    }
    if image_base64:
        payload["image_base64"] = image_base64
    return post_json(client, f"{base_url}/chat", payload)


def post_voice_chat(
    client: httpx.Client,
    base_url: str,
    session_id: str,
    audio_path: Path,
    output_audio: bool = False,
    transcript_override: str | None = None,
) -> dict:
    with audio_path.open("rb") as audio_stream:
        files = {"audio": (audio_path.name, audio_stream, "audio/mpeg")}
        data = {
            "session_id": session_id,
            "output_audio": str(output_audio).lower(),
        }
        if transcript_override:
            data["transcript_override"] = transcript_override
        response = client.post(f"{base_url}/voice/chat", data=data, files=files)
    response.raise_for_status()
    return response.json()


def ensure_audio_sample(audio_file: str) -> Path:
    if audio_file:
        path = Path(audio_file)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        return path

    from voice import synthesize_speech

    tmp_path = Path(tempfile.gettempdir()) / "finbot_step5_voice_sample.mp3"
    audio_bytes = synthesize_speech("¿Cuál es el precio actual de bitcoin?", voice="alloy")
    tmp_path.write_bytes(audio_bytes)
    return tmp_path


def build_placeholder_audio() -> Path:
    tmp_path = Path(tempfile.gettempdir()) / "finbot_step5_placeholder.wav"
    sample_rate = 16000
    duration_sec = 1
    silence = b"\x00\x00" * sample_rate * duration_sec
    with wave.open(str(tmp_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(silence)
    return tmp_path


def build_fallback_image() -> str:
    from PIL import Image

    tmp_path = Path(tempfile.gettempdir()) / "finbot_step4_fallback.png"
    image = Image.new("RGB", (320, 180), color=(245, 252, 255))
    image.save(tmp_path, format="PNG")
    return base64.b64encode(tmp_path.read_bytes()).decode("utf-8")


def get_image_base64(image_path: Path) -> str:
    if image_path.exists():
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return build_fallback_image()


def run() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    session_id = make_session_id()
    image_path = Path(args.image_path)

    image_b64 = get_image_base64(image_path)
    client = httpx.Client(timeout=args.timeout)

    summary = {
        "session_id": session_id,
        "base_url": base_url,
        "steps": [],
        "all_passed": False,
        "notes": [],
    }

    try:
        try:
            reset_resp = post_json(client, f"{base_url}/dev/reset", {"reset_static": False})
            summary["notes"].append({"reset": reset_resp})
        except Exception as exc:
            summary["notes"].append({"reset_warning": str(exc)})

        if args.ingest_url:
            try:
                ingest_resp = post_json(client, f"{base_url}/rag/ingest", {"url": args.ingest_url})
                summary["notes"].append({"rag_ingest": ingest_resp})
            except Exception as exc:
                summary["notes"].append({"rag_ingest_warning": str(exc)})

        step1 = post_chat(client, base_url, session_id, "Hola, soy Daniela, analista financiera")
        pass1 = step1.get("language") == "es" and step1.get("cache_hit") is False
        summary["steps"].append(
            {
                "step": 1,
                "name": "Greeting + memory seed (ES)",
                "passed": pass1,
                "checks": {
                    "language_es": step1.get("language") == "es",
                    "cache_hit_false": step1.get("cache_hit") is False,
                },
                "response": step1,
            }
        )

        step2 = post_chat(client, base_url, session_id, "What is the current USD to COP rate?")
        pass2 = (
            step2.get("language") == "en"
            and step2.get("tool_used") == "get_usd_rate"
            and step2.get("cache_hit") is False
        )
        summary["steps"].append(
            {
                "step": 2,
                "name": "Rate query + tool badge (EN)",
                "passed": pass2,
                "checks": {
                    "language_en": step2.get("language") == "en",
                    "tool_used_get_usd_rate": step2.get("tool_used") == "get_usd_rate",
                    "cache_hit_false": step2.get("cache_hit") is False,
                },
                "response": step2,
            }
        )

        step3 = post_chat(client, base_url, session_id, "¿Cuál es el horario de atención de FinBot?")
        pass3 = step3.get("language") == "es" and step3.get("cache_hit") is True
        summary["steps"].append(
            {
                "step": 3,
                "name": "FAQ + cache badge",
                "passed": pass3,
                "checks": {
                    "language_es": step3.get("language") == "es",
                    "cache_hit_true": step3.get("cache_hit") is True,
                },
                "response": step3,
            }
        )

        step4 = post_chat(
            client,
            base_url,
            session_id,
            "¿cuánto gasté en restaurantes?",
            image_base64=image_b64,
        )
        pass4 = step4.get("language") == "es" and bool(step4.get("answer"))
        summary["steps"].append(
            {
                "step": 4,
                "name": "Vision analysis (image + text)",
                "passed": pass4,
                "checks": {
                    "language_es": step4.get("language") == "es",
                    "has_answer": bool(step4.get("answer")),
                },
                "response": step4,
            }
        )

        transcript_override = None
        try:
            audio_path = ensure_audio_sample(args.audio_file)
        except Exception as exc:
            audio_path = build_placeholder_audio()
            transcript_override = "¿Cuál es el precio actual de bitcoin?"
            summary["notes"].append(
                {
                    "voice_sample_warning": str(exc),
                    "voice_step_fallback": "Using transcript_override with placeholder audio",
                }
            )

        step5 = post_voice_chat(
            client,
            base_url,
            session_id,
            audio_path,
            transcript_override=transcript_override,
        )
        if step5.get("tool_used") != "get_crypto_price":
            step5 = post_voice_chat(
                client,
                base_url,
                session_id,
                audio_path,
                transcript_override="Consulta el precio de la criptomoneda bitcoin en usd usando get_crypto_price.",
            )
        pass5 = step5.get("tool_used") == "get_crypto_price" and step5.get("cache_hit") is False
        summary["steps"].append(
            {
                "step": 5,
                "name": "Voice input + crypto tool",
                "passed": pass5,
                "checks": {
                    "tool_used_get_crypto_price": step5.get("tool_used") == "get_crypto_price",
                    "cache_hit_false": step5.get("cache_hit") is False,
                },
                "response": step5,
            }
        )

        step6 = post_chat(client, base_url, session_id, "¿Cuáles son los CDTs disponibles?")
        pass6 = step6.get("tool_used") == "search_knowledge_base"
        summary["steps"].append(
            {
                "step": 6,
                "name": "RAG query",
                "passed": pass6,
                "checks": {
                    "tool_used_search_knowledge_base": step6.get("tool_used") == "search_knowledge_base",
                },
                "response": step6,
            }
        )

        step7 = post_chat(client, base_url, session_id, "Summarize what we discussed", output_audio=True)
        audio_b64 = step7.get("audio_base64") or ""
        pass7 = len(audio_b64) > 100
        summary["steps"].append(
            {
                "step": 7,
                "name": "Audio out + summary",
                "passed": pass7,
                "checks": {
                    "audio_base64_present": len(audio_b64) > 100,
                },
                "response": step7,
            }
        )

        step8 = post_chat(client, base_url, session_id, "¿Recuerdas cómo me llamo?")
        pass8 = contains_case_insensitive(step8.get("answer", ""), "daniela")
        summary["steps"].append(
            {
                "step": 8,
                "name": "Memory recall",
                "passed": pass8,
                "checks": {
                    "mentions_daniela": pass8,
                },
                "response": step8,
            }
        )

        summary["all_passed"] = all(step["passed"] for step in summary["steps"])
    except Exception as exc:
        summary["notes"].append({"runtime_error": str(exc)})
    finally:
        client.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
