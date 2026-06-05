"""
The Doctor — Audio Processor

Two-step pipeline:
  Step 1 — Transcribe via Groq Whisper API (fast, reliable)
  Step 2 — Extract health data from transcription via Perplexity API server

Usage:
  uv run python3 processor.py <audio_file> [--time "2024-01-01 12:00:00"]
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────

# Groq Whisper STT
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/audio/transcriptions")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")

# Perplexity API server (local FastAPI server on port 8001)
PERPLEXITY_API_URL = os.getenv("PERPLEXITY_API_URL", "http://127.0.0.1:8001")

DATA_DIR = Path(__file__).parent / "data"

DOCTOR_ENV = os.getenv("DOCTOR_ENV", "")
_DATA_PREFIX = "test_" if DOCTOR_ENV == "test" else ""
TRANSCRIPT_FILE = DATA_DIR / f"{_DATA_PREFIX}transcripts.json"
HEALTH_DATA_FILE = DATA_DIR / f"{_DATA_PREFIX}health_data.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Transcription via Groq Whisper API ──────────────────────


def transcribe(audio_path: str) -> Optional[str]:
    """
    Transcribe audio using Groq Whisper API (only method).
    Returns transcription text, or None on failure.
    Error details are shown to the user — no silent fallback.
    """
    return _transcribe_with_groq(audio_path)


def _transcribe_with_groq(audio_path: str) -> Optional[str]:
    """Transcribe via Groq Whisper API (multipart/form-data POST).
    Errors are displayed to the user — no silent fallback."""
    if not os.path.isfile(audio_path):
        print(f"  ❌ Audio file not found: {audio_path}")
        return None

    print(f"  🎤 Transcribing with Groq Whisper ({GROQ_STT_MODEL})...")
    try:
        import requests
    except ImportError:
        print("  ❌ requests library not installed. Run: uv add requests")
        return None

    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/ogg")}
            data = {"model": GROQ_STT_MODEL}
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

            resp = requests.post(
                GROQ_API_URL,
                headers=headers,
                files=files,
                data=data,
                timeout=60,
            )

        if resp.status_code != 200:
            print(f"  ❌ Groq API error (HTTP {resp.status_code}): {resp.text[:200]}")
            return None

        result = resp.json()
        text = result.get("text", "").strip()
        if text:
            print(f"  ✅ Groq transcription ({len(text)} chars)")
            return text
        else:
            print("  ⚠️  Groq returned empty transcription")
            return None

    except Exception as e:
        print(f"  ❌ Groq transcription error: {e}")
        return None


# ── Step 2: Transcription Translation (via Perplexity API Server) ────

TRANSLATION_PROMPT = """You are a bilingual medical transcription assistant. A patient has sent a voice note in Urdu/Hindi mixed with some English. Below is the raw transcription from speech-to-text.

Please provide:
1. A clean Urdu version in proper Urdu script (اردو)
2. An English translation

IMPORTANT: Return ONLY valid JSON in this exact format with no extra text:
{
  "urdu": "clean urdu text here in urdu script",
  "english": "english translation here"
}

Raw transcription:
"""


def translate_transcription(transcription: str) -> dict:
    """
    Send the transcription text to the Perplexity API server for Urdu + English translation.
    Uses the local FastAPI server at PERPLEXITY_API_URL.
    Returns dict with 'urdu' and 'english' keys.
    """
    import urllib.request
    import urllib.parse

    query = f"{TRANSLATION_PROMPT}\n\n{transcription}"

    print("  📤 Translating transcription via Perplexity API server...")
    try:
        # Build URL with query params
        params = urllib.parse.urlencode({
            "q": query,
            "answer_only": "true",
            "mode": "auto",
        })
        url = f"{PERPLEXITY_API_URL}/api/query_sync?{params}"

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        answer = data.get("answer", "")
        thread_uuid = data.get("backend_uuid")

        if answer:
            print(f"  ✅ Translation received ({len(answer)} chars)")
        else:
            print("  ⚠️  Perplexity returned empty answer")
            return {"urdu": "", "english": "", "error": "Perplexity server returned an empty response."}

        # Parse JSON from answer (may be wrapped in markdown code block)
        translated = _try_extract_json(answer)

        # Delete the Perplexity thread to keep history clean
        if thread_uuid:
            try:
                delete_url = f"{PERPLEXITY_API_URL}/api/threads/{thread_uuid}"
                delete_req = urllib.request.Request(delete_url, method="DELETE")
                urllib.request.urlopen(delete_req, timeout=30)
                print(f"  🗑️ Deleted Perplexity thread: {thread_uuid}")
            except Exception as del_err:
                print(f"  ⚠️  Failed to delete thread {thread_uuid}: {del_err}")

        # Ensure we have the expected keys
        if "urdu" not in translated and "english" not in translated:
            # If JSON didn't have the right keys, server returned unexpected format
            return {"urdu": "", "english": "", "error": "Perplexity server returned an unexpected response."}

        return {
            "urdu": translated.get("urdu", ""),
            "english": translated.get("english", transcription),
        }

    except Exception as e:
        print(f"  ❌ Translation failed: {e}")
        return {"urdu": "", "english": "", "error": f"Perplexity server is not responding ({type(e).__name__})."}


def _try_extract_json(text: str) -> dict:
    """Try to extract JSON from Perplexity's response."""
    import re

    # Try JSON in code blocks first
    json_block = re.search(r"```(?:json)?\s*\n?(\{.*?\})\n?\s*```", text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object with urdu and english keys
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {"urdu": "", "english": text[:500]}


# ── Data Storage ─────────────────────────────────────────────────────


def load_json(path):
    if path.exists() and path.stat().st_size > 0:
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return [] if path == TRANSCRIPT_FILE else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved to {path.name}")


# ── Main Pipeline ────────────────────────────────────────────────────


def process_audio(audio_path: str, recording_time: Optional[str] = None,
                  translate: bool = True) -> dict:
    """
    Full pipeline: transcribe + optionally extract health data.

    Args:
        audio_path: Path to audio file
        recording_time: When recorded (auto if None)
        extract_health_data: Whether to do step 2 (default: True)

    Returns:
        Dict with success, transcription, and optionally extracted health data
    """
    audio_file = Path(audio_path)
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if recording_time is None:
        recording_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'='*60}")
    print(f"🎤 Processing: {audio_file.name}")
    print(f"🕐 Recording time: {recording_time}")
    print(f"{'='*60}\n")

    # ── Step 1: Transcribe ──
    print("▸ Step 1: Transcribing audio (via Groq Whisper)...")
    transcription = transcribe(str(audio_file))

    if not transcription:
        print("  ❌ Transcription failed")
        return {
            "success": False,
            "filename": audio_file.name,
            "error": "Transcription returned empty result",
        }

    print(f"  ✅ Transcription ({len(transcription)} chars)")
    print(f"     Preview: {transcription[:200]}...")

    # Save transcript
    transcripts = load_json(TRANSCRIPT_FILE)
    transcript_entry = {
        "id": len(transcripts) + 1,
        "filename": audio_file.name,
        "recording_time": recording_time,
        "processed_at": datetime.now().isoformat(),
        "transcription": transcription,
    }
    transcripts.append(transcript_entry)
    save_json(TRANSCRIPT_FILE, transcripts)

    # ── Step 2: Translate to Urdu + English (optional) ──
    translated = {}
    if translate:
        print("\n▸ Step 2: Translating transcription to Urdu + English...")
        translated = translate_transcription(transcription)

    return {
        "success": True,
        "filename": audio_file.name,
        "recording_time": recording_time,
        "transcription": transcription,
        "translated": translated,
    }


# ── CLI Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="The Doctor — Process health audio notes")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--time", "-t", help="Recording time (default: now)", default=None)
    parser.add_argument("--no-translate", action="store_true",
                        help="Skip translation (transcription only)")

    args = parser.parse_args()
    result = process_audio(args.audio_file, args.time, translate=not args.no_translate)

    if result["success"]:
        print(f"\n✅ Processing complete!")
        print(f"📄 Transcript saved to: {TRANSCRIPT_FILE}")
        if result.get("translated"):
            print(f"  🔤 Urdu: {result['translated'].get('urdu', '')[:80]}...")
            print(f"  🔤 English: {result['translated'].get('english', '')[:80]}...")
    else:
        print(f"\n❌ Processing failed: {result.get('error', 'Unknown error')}")
