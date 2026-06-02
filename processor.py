"""
The Doctor — Audio Processor

Two-step pipeline:
  Step 1 — Transcribe via bridge script (same prompt as working setup)
  Step 2 — (Optional) Extract health data from transcription text

Usage:
  uv run python3 processor.py <audio_file> [--time "2024-01-01 12:00:00"]
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────

BRIDGE_SCRIPT = os.getenv(
    "DOCTOR_BRIDGE_SCRIPT",
    str(Path.home() / "Documents" / "Development" / "perplexity-stack" / "scripts" / "transcribe.py"),
)
BRIDGE_PYTHON = os.getenv(
    "DOCTOR_BRIDGE_PYTHON",
    str(Path.home() / "Documents" / "Development" / "perplexity-stack" / "perplexity-web-wrapper" / ".venv" / "bin" / "python3"),
)

DATA_DIR = Path(__file__).parent / "data"

DOCTOR_ENV = os.getenv("DOCTOR_ENV", "")
_DATA_PREFIX = "test_" if DOCTOR_ENV == "test" else ""
TRANSCRIPT_FILE = DATA_DIR / f"{_DATA_PREFIX}transcripts.json"
HEALTH_DATA_FILE = DATA_DIR / f"{_DATA_PREFIX}health_data.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Transcription via Bridge Script ─────────────────────────


def transcribe(audio_path: str) -> Optional[str]:
    """
    Call the existing Perplexity bridge script to transcribe an audio file.
    Uses the EXACT same prompt as the working setup (DEFAULT_PROMPT in transcribe.py).

    Returns transcription text, or None on failure.
    """
    if not os.path.isfile(BRIDGE_SCRIPT):
        print(f"  ❌ Bridge script not found: {BRIDGE_SCRIPT}")
        return None
    if not os.path.isfile(BRIDGE_PYTHON):
        print(f"  ❌ Bridge Python not found: {BRIDGE_PYTHON}")
        return None

    cmd = [BRIDGE_PYTHON, BRIDGE_SCRIPT, audio_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print("  ❌ Bridge script timed out after 120s")
        return None

    if result.returncode != 0:
        print(f"  ❌ Bridge script failed (exit {result.returncode}): {result.stderr.strip()}")
        return None

    try:
        data = json.loads(result.stdout)
        text = data.get("text", "")
        if text:
            return text
        print("  ⚠️  Bridge returned empty transcription")
        return None
    except json.JSONDecodeError as e:
        print(f"  ❌ Bridge output not valid JSON: {e}")
        print(f"     stdout: {result.stdout[:200]}")
        return None


# ── Step 2: Health Data Extraction (from text, no audio) ────────────

HEALTH_EXTRACTION_PROMPT = """You are The Doctor's health data assistant.

A transcription from my father's health audio note is provided below.
Please extract the following structured information:

| Field | Value | Notes |
|-------|-------|-------|
| Recording Time | {recording_time} | When the audio was sent |
| Mentioned Time |  | Any specific time mentioned in the note |
| Blood Sugar Level |  | If mentioned (e.g., 120 mg/dL) |
| Meals / Food |  | What was eaten, when |
| Physical Activity |  | Any exercise, walking, etc. |
| Medications |  | Any medicines taken |
| Symptoms |  | Any health complaints |
| Mood / Energy |  | How they're feeling |
| Other Notes |  | Anything else important |

Return your response in this JSON format:
{{
  "raw_transcript_english": "the transcription",
  "extracted_data": {{
    "recording_time": "...",
    "mentioned_time": "...",
    "blood_sugar": "...",
    "meals": "...",
    "activity": "...",
    "medications": "...",
    "symptoms": "...",
    "mood": "...",
    "other_notes": "..."
  }},
  "summary": "One-line summary of the note"
}}
"""


def extract_health(transcription: str, recording_time: str) -> dict:
    """
    Send the transcription text to Perplexity for health data extraction.
    Uses the same MCP client (no audio, just text).
    """
    # Add perplexity-web-wrapper to path
    WRAPPER_PATH = Path.home() / "Documents" / "Development" / "perplexity-stack" / "perplexity-web-wrapper"
    sys.path.insert(0, str(WRAPPER_PATH))

    COOKIES_PATH = Path.home() / ".config" / "perplexity" / "cookies.json"

    from perplexity_subscription_mcp import client as perplexity

    cookies = {}
    if COOKIES_PATH.exists():
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cookies = perplexity.normalize_cookies(raw)

    perp_client = perplexity.Client(cookies)

    prompt = HEALTH_EXTRACTION_PROMPT.format(recording_time=recording_time)
    full_prompt = (
        f"Here is a transcription of my father's health audio note:\n\n"
        f"{transcription}\n\n---\n\n{prompt}"
    )

    print("  📤 Extracting health data from transcription...")
    try:
        result = perp_client.search(
            query=full_prompt,
            mode="pro",
            model="sonar",
            stream=False,
        )

        # Get thread UUID for cleanup
        thread_uuid = result.get("backend_uuid") if isinstance(result, dict) else None

        # Parse response — result can be dict with "answer" or "text" (list of steps)
        response_text = ""
        if isinstance(result, dict):
            answer = result.get("answer")
            if isinstance(answer, str) and len(answer) > 10:
                response_text = answer
            else:
                # Iterate through text steps to find FINAL answer
                text_steps = result.get("text", [])
                if isinstance(text_steps, list):
                    for step in text_steps:
                        if isinstance(step, dict) and step.get("step_type") == "FINAL":
                            content = step.get("content", {})
                            step_answer = content.get("answer") or content.get("text") or ""
                            if isinstance(step_answer, str) and len(step_answer) > 10:
                                response_text = step_answer
                                break
                if not response_text:
                    response_text = json.dumps(result)
        elif isinstance(result, str):
            response_text = result
        else:
            response_text = str(result)

        # Try to extract JSON from response
        extracted = _try_extract_json(response_text)

        # Delete the Perplexity thread to keep history clean
        if thread_uuid:
            try:
                perp_client.delete_thread(thread_uuid)
                print(f"  🗑️ Deleted Perplexity thread: {thread_uuid}")
            except Exception as del_err:
                print(f"  ⚠️  Failed to delete thread {thread_uuid}: {del_err}")

        return extracted

    except Exception as e:
        print(f"  ❌ Health extraction failed: {e}")
        return {"raw_text": transcription[:500]}


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

    # Try to find JSON object
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {"raw_text": text[:500]}


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
                  extract_health_data: bool = True) -> dict:
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
    print("▸ Step 1: Transcribing audio (via bridge script)...")
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

    # ── Step 2: Extract health data (optional) ──
    extracted = {}
    if extract_health_data:
        print("\n▸ Step 2: Extracting health data from transcription...")
        extracted = extract_health(transcription, recording_time)

        if extracted and "extracted_data" in extracted:
            health_data = load_json(HEALTH_DATA_FILE)
            if isinstance(health_data, dict):
                entries = [health_data] if health_data else []
            else:
                entries = health_data

            entry = {
                "id": len(entries) + 1,
                "recording_time": recording_time,
                "processed_at": datetime.now().isoformat(),
                **extracted.get("extracted_data", {}),
                "summary": extracted.get("summary", ""),
                "raw_transcript": extracted.get("raw_transcript_english", transcription),
            }
            entries.append(entry)
            save_json(HEALTH_DATA_FILE, entries)

    return {
        "success": True,
        "filename": audio_file.name,
        "recording_time": recording_time,
        "transcription": transcription,
        "extracted": extracted,
    }


# ── CLI Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="The Doctor — Process health audio notes")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--time", "-t", help="Recording time (default: now)", default=None)
    parser.add_argument("--no-extract", action="store_true",
                        help="Skip health data extraction (transcription only)")

    args = parser.parse_args()
    result = process_audio(args.audio_file, args.time, extract_health_data=not args.no_extract)

    if result["success"]:
        print(f"\n✅ Processing complete!")
        print(f"📄 Transcript saved to: {TRANSCRIPT_FILE}")
        if result.get("extracted") and result["extracted"].get("extracted_data"):
            print(f"📊 Health data saved to: {HEALTH_DATA_FILE}")
    else:
        print(f"\n❌ Processing failed: {result.get('error', 'Unknown error')}")
