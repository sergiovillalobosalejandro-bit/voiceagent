# SoundBot — Multimodal Conversational AI Agent

A web application integrating a conversational AI agent for a music and instruments company operating in Colombia and the United States. Users interact with the agent by typing, speaking, or uploading images. The agent responds in text or voice and has access to real tools (function calling). The UI visually distinguishes when the agent uses a tool versus responding directly.

## Use Case

SoundBot is a virtual music assistant that helps users with:
- Instrument information and specifications (guitar, piano, violin, drums, bass, flute, saxophone, trumpet)
- Tuning frequencies and music theory
- Instrument identification from descriptions
- Music knowledge base queries (music history, composers, genres, theory)
- Image analysis of instruments, sheet music, and audio gear
- Voice input and output

## Architecture

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite |
| Backend | FastAPI (Python 3.12) |
| LLM Provider | Groq (llama-3.3-70b-versatile for text, llama-4-scout for vision) |
| Speech-to-Text | Groq Whisper large-v3 |
| Text-to-Speech | Microsoft Edge TTS (free, no API key) |
| Vector Database | FAISS (in-memory) |
| Embeddings | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) |
| Integration | n8n (optional, for webhook-based RAG ingestion) |

## Prerequisites

- Python 3.12+
- Node.js 20+
- Groq API key (free tier available at [console.groq.com](https://console.groq.com))
- n8n (optional, for RAG ingestion webhooks)

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd <repo-folder>
```

### 2. Configure environment

Copy the environment template and fill in your API key:

```bash
cp .env.example backend/.env
```

Edit `backend/.env` and set your `GROQ_API_KEY`:

```
GROQ_API_KEY=gsk_your_key_here
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Install frontend dependencies

```bash
cd ../frontend
npm install
```

### 5. Run the application

#### Option A: Single command (Windows PowerShell)

```powershell
.\start.ps1
```

#### Option B: Manual

```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

#### Option C: Docker Compose

```bash
docker-compose up
```

Open **http://localhost:5173** in your browser.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Main chat endpoint (text, image+text) |
| `POST` | `/voice/chat` | Voice chat endpoint (multipart audio upload) |
| `GET` | `/rag/status` | RAG index status |
| `POST` | `/rag/ingest` | Ingest a URL into the RAG pipeline |
| `GET` | `/cache/status` | Semantic cache status |
| `POST` | `/dev/reset` | Reset memory, cache, and RAG |

### Response Contract

Every response follows this format:

```json
{
  "answer": "string",
  "language": "es | en",
  "tool_used": "string | null",
  "cache_hit": true | false,
  "audio_base64": "string | null"
}
```

## Tools

The agent has 4 registered tools and decides autonomously when to use each one:

| Tool | Parameters | Description |
|---|---|---|
| `instrument_info` | `instrument_name` (string) | Returns detailed info about a musical instrument (tuning, family, range, description) |
| `get_tuning_frequency` | none | Returns the international standard tuning pitch (A4 = 440 Hz) and its history |
| `identify_instrument_from_description` | `description` (string) | Identifies a musical instrument from a text description |
| `search_music_knowledge` | `query` (string) | Queries the RAG knowledge base (music theory, history, composers, genres) |

## Semantic Cache

A two-tier semantic cache using cosine similarity on sentence embeddings (threshold: 0.90):

- **Static**: 5 pre-seeded bilingual FAQ entries (guitar tuning, piano keys, acoustic vs electric, A440 tuning, instrument maintenance)
- **Dynamic**: Up to 20 entries grown at runtime, oldest evicted first (FIFO)

Tuning/queries (instrument lookups, frequency queries) bypass the cache automatically.

## RAG (Retrieval-Augmented Generation)

- **Default source**: Wikipedia — Musical instrument
- **Ingestion**: Scrape URL → sentence splitting → chunking (max 600 chars, 60-char overlap, minimum 3 chunks) → FAISS IndexFlatIP
- **Retrieval**: Top 3 chunks returned per query
- Additional URLs can be ingested via `POST /rag/ingest`

## Memory

The agent maintains the last 7 messages (user + assistant pairs) per session. Session ID is generated client-side and sent with every request.

## System Prompt

The agent's behavior is defined by a system prompt with the following instructions:

1. **Identity**: SoundBot, virtual assistant for a music and instruments company in Colombia and the US
2. **Tone**: Friendly, passionate, and knowledgeable musical tone
3. **Domain restriction**: Strictly music theory, instruments, instrument maintenance, music history, genres, composition, and audio analysis. Politely declines out-of-domain queries
4. **Bilingual**: Automatically detects input language (Spanish/English) and responds in the same language
5. **No hallucination**: Must use tools for instrument data, tuning frequencies, and knowledge queries. Never fabricate technical details
6. **Tool integration**: Integrate tool results naturally. Always cite the source for instrument data
7. **Vision**: Can analyze images (instruments, sheet music, gear, audio equipment). Identify instruments from images
8. **Serving**: Both Colombia (Spanish-speaking) and US (English-speaking) musicians and music enthusiasts

## UI Features

- **Input modes**: Text, Voice, Image+Text
- **Output modes**: Text, Audio (TTS)
- **Tool badge**: Purple indicator displayed when the agent activates a tool, persisted in chat history
- **Cache badge**: Teal indicator displayed when the response comes from the semantic cache
- **Voice**: Built-in audio recorder (WebM) and audio player for TTS responses

## n8n Workflows (Optional)

Three exported workflows are provided in `n8n-workflows/`:

| File | Purpose |
|---|---|
| `finbot-crypto-price.json` | Music data API webhook (reusable template) |
| `finbot-rag-ingest.json` | Web scraping and chunking webhook |
| `finbot-tts.json` | TTS webhook (fallback, Edge TTS used directly in backend) |

Import into n8n and configure the webhook URLs.

## Environment Variables

See `.env.example` for the full list:

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | Groq API key |
| `GROQ_TEXT_MODEL` | No | `llama-3.3-70b-versatile` | LLM model for text |
| `GROQ_VISION_MODEL` | No | `meta-llama/llama-4-scout-17b-16e-instruct` | LLM model for vision |
| `MAX_MODEL_TOKENS` | No | `512` | Max response tokens |
| `N8N_WEBHOOK_URL` | No | `http://localhost:5678` | n8n webhook base URL |

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app, endpoints, response builder
│   ├── agent.py              # Core agent: system prompt, memory, chat loop
│   ├── tools.py              # Tool implementations and definitions
│   ├── cache.py              # Semantic cache with sentence-transformers
│   ├── rag.py                # RAG pipeline: scraping, chunking, FAISS
│   ├── voice.py              # STT (Whisper) and TTS (Edge TTS)
│   ├── models.py             # Pydantic request/response models
│   ├── validate_8_steps.py   # End-to-end integration test
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Main chat UI component
│   │   ├── App.css           # Chat UI styles
│   │   ├── main.jsx          # React entry point
│   │   └── index.css         # Global styles
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── n8n-workflows/            # n8n workflow JSON exports
├── n8n-mcp-bridge/           # MCP server bridging opencode ↔ n8n
├── docker-compose.yml
├── start.ps1                 # Windows startup script
├── .env.example
└── README.md
```
