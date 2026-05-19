import json
import os
import httpx
from rag import query_rag, ingest_from_n8n

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678")
STANDARD_TUNING = 440.0

INSTRUMENT_DB = {
    "guitar": {
        "name": "Guitar / Guitarra",
        "family": "String / Cuerda",
        "strings": 6,
        "standard_tuning": "E2 A2 D3 G3 B3 E4 (standard / estandar)",
        "range": "E2 to ~B5",
        "description": "The guitar is a fretted string instrument with six strings. It is one of the most popular instruments worldwide, used across virtually all genres from classical and flamenco to rock, pop, jazz, and blues. The acoustic guitar produces sound through a hollow body that resonates, while the electric guitar uses electromagnetic pickups to convert string vibrations into electrical signals. Common types include classical (nylon strings), acoustic (steel strings), and electric guitars.",
    },
    "piano": {
        "name": "Piano",
        "family": "Keyboard / Teclado",
        "keys": 88,
        "standard_tuning": "A4 = 440 Hz",
        "range": "A0 to C8",
        "description": "The piano is a keyboard instrument with 88 keys (52 white, 36 black) that produces sound by striking strings with felt hammers. Invented around 1700 by Bartolomeo Cristofori, it is one of the most versatile instruments, capable of playing melody, harmony, and bass simultaneously. The piano is central to classical music, jazz, and popular music. Types include grand, upright, and digital pianos.",
    },
    "violin": {
        "name": "Violin / Violin",
        "family": "String / Cuerda frotada",
        "strings": 4,
        "standard_tuning": "G3 D4 A4 E5",
        "range": "G3 to ~E7",
        "description": "The violin is the smallest and highest-pitched member of the bowed string family. It has four strings tuned in perfect fifths and is played with a bow or plucked (pizzicato). The violin is central to classical orchestras, chamber music, and is also widely used in folk, jazz, and contemporary music. Its expressive range makes it one of the most emotional instruments.",
    },
    "drums": {
        "name": "Drums / Bateria",
        "family": "Percussion / Percusion",
        "pieces": "Multiple / Multiple",
        "standard_tuning": "Not applicable / No aplica",
        "range": "Rhythmic / Ritmico",
        "description": "A drum kit (or drum set) is a collection of drums, cymbals, and other percussion instruments arranged for a single player. A standard kit includes a bass drum, snare drum, hi-hat, toms, and cymbals. Drums provide the rhythmic foundation in most modern music genres including rock, pop, jazz, funk, and Latin music. Electronic drum kits are also popular for practice and recording.",
    },
    "bass": {
        "name": "Bass Guitar / Bajo",
        "family": "String / Cuerda",
        "strings": 4,
        "standard_tuning": "E1 A1 D2 G2 (standard / estandar)",
        "range": "E1 to ~G4",
        "description": "The bass guitar is a string instrument that provides the low-end foundation in most musical ensembles. Usually with four strings tuned one octave lower than a guitar, the bass bridges rhythm and harmony. It is essential in funk, rock, jazz, R&B, pop, and Latin music. Techniques include fingerstyle, slap, pick playing, and tapping.",
    },
    "flute": {
        "name": "Flute / Flauta traversa",
        "family": "Woodwind / Viento madera",
        "keys": "16+ tone holes",
        "standard_tuning": "C instrument / Instrumento en C",
        "range": "B3 to ~C7",
        "description": "The Western concert flute is a transverse woodwind instrument made of metal (silver, nickel, or gold). Sound is produced by blowing air across the embouchure hole. The flute has a bright, clear tone and is prominent in classical orchestras, concert bands, and also appears in jazz and world music. The piccolo is its smaller, higher-pitched relative.",
    },
    "saxophone": {
        "name": "Saxophone / Saxofon",
        "family": "Woodwind / Viento madera",
        "types": "Soprano, Alto, Tenor, Baritone",
        "standard_tuning": "Eb (alto/baritone) or Bb (soprano/tenor)",
        "range": "~2.5 octaves per type",
        "description": "The saxophone is a single-reed woodwind instrument with a conical brass body, invented by Adolphe Sax in the 1840s. Despite being made of brass, it is classified as woodwind because of its reed mouthpiece. The saxophone family ranges from sopranino to contrabass, with alto and tenor being the most popular in jazz, classical, and popular music. It is known for its expressive, warm, and powerful tone.",
    },
    "trumpet": {
        "name": "Trumpet / Trompeta",
        "family": "Brass / Viento metal",
        "valves": 3,
        "standard_tuning": "Bb instrument / Instrumento en Sib",
        "range": "F#3 to ~C6",
        "description": "The trumpet is a brass instrument with the highest register in the brass family. Sound is produced by buzzing the lips into a cup-shaped mouthpiece, and pitch is changed with three piston valves. The trumpet is prominent in classical orchestras, jazz (where it had legendary players like Louis Armstrong and Miles Davis), marching bands, and Latin music.",
    },
}


def instrument_info(instrument_name: str) -> dict:
    name_lower = instrument_name.lower().strip()
    if name_lower in INSTRUMENT_DB:
        return INSTRUMENT_DB[name_lower]
    for key, data in INSTRUMENT_DB.items():
        name_field = data["name"].lower()
        if name_lower in name_field or key in name_lower:
            return data
    return {
        "name": instrument_name,
        "info": f"I don't have detailed information about '{instrument_name}' yet. Try asking about guitar, piano, violin, drums, bass, flute, saxophone, or trumpet.",
    }


def get_tuning_frequency() -> dict:
    return {
        "standard_tuning_hz": STANDARD_TUNING,
        "description": "A4 = 440 Hz is the international standard tuning pitch (ISO 16). This frequency serves as the reference for tuning all instruments in an ensemble.",
        "history": "440 Hz was adopted as the standard in 1939. Historically, tuning varied from 415 Hz (Baroque) to 466 Hz (some modern European orchestras).",
    }


def identify_instrument_from_description(description: str) -> dict:
    description_lower = description.lower()
    matches = []
    for key, data in INSTRUMENT_DB.items():
        name = data["name"].lower()
        family = data["family"].lower()
        desc = data.get("description", "").lower()
        if any(word in description_lower for word in [key, name.split("/")[0].strip(), family.split("/")[0].strip()]):
            matches.append(data)
        elif any(word in description_lower for word in desc.split()[:10]):
            matches.append(data)
    
    if matches:
        return {"instruments_found": len(matches), "results": matches[:3]}
    return {"instruments_found": 0, "message": "No instrument matched that description. Try describing shape, family (string, wind, percussion, brass), number of strings, or sound characteristics."}


def search_music_knowledge(query: str) -> dict:
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
            "name": "instrument_info",
            "description": "Obtiene informacion detallada sobre un instrumento musical (afinacion, familia, rango, descripcion). Get detailed information about a musical instrument (tuning, family, range, description).",
            "parameters": {
                "type": "object",
                "properties": {
                    "instrument_name": {"type": "string", "description": "Nombre del instrumento (ej: guitar, piano, violin, drums, bass, flute, saxophone, trumpet) / Instrument name"},
                },
                "required": ["instrument_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tuning_frequency",
            "description": "Obtiene la frecuencia de afinacion estandar internacional (A4 = 440 Hz) y su historia. Get the international standard tuning frequency (A4 = 440 Hz) and its history.",
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
            "name": "identify_instrument_from_description",
            "description": "Identifica un instrumento musical a partir de una descripcion textual. Identify a musical instrument from a text description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Descripcion del instrumento a identificar / Description of the instrument to identify"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_music_knowledge",
            "description": "Busca informacion musical en la base de conocimiento interna (teoria musical, historia, compositores, generos). Search music information in the internal knowledge base (music theory, history, composers, genres).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La pregunta o tema musical a buscar / The music topic to search"},
                },
                "required": ["query"],
            },
        },
    },
]


TOOL_MAP = {
    "instrument_info": instrument_info,
    "get_tuning_frequency": get_tuning_frequency,
    "identify_instrument_from_description": identify_instrument_from_description,
    "search_music_knowledge": search_music_knowledge,
}


def execute_tool(name: str, args: dict) -> dict:
    fn = TOOL_MAP.get(name)
    if not fn:
        return {"error": f"Tool '{name}' no encontrada / not found"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}
