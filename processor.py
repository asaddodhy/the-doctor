"""
The Doctor — Audio Processor
Receives audio files (Urdu/Hindi), sends to Perplexity for transcription,
translates to English, and extracts structured health data.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add perplexity-web-wrapper to path for the client package
WRAPPER_PATH = Path.home() / "Documents" / "Development" / "perplexity-stack" / "perplexity-web-wrapper"
sys.path.insert(0, str(WRAPPER_PATH))

from perplexity_subscription_mcp import client as perplexity

# ── Config ──────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
COOKIES_PATH = Path.home() / ".config" / "perplexity" / "cookies.json"
TRANSCRIPT_FILE = DATA_DIR / "transcripts.json"
HEALTH_DATA_FILE = DATA_DIR / "health_data.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Audio Conversion ─────────────────────────────────────────────────

# Audio formats that Perplexity can handle (common web formats)
SUPPORTED_FORMATS = {".mp3", ".mp4", ".wav", ".m4a", ".aac", ".flac"}
TELEGRAM_FORMATS = {".ogg", ".oga"}  # Telegram uses OGG Opus

def convert_audio(audio_path: Path) -> Path:
    """
    Convert audio to MP3 if needed. Telegram sends OGG, WhatsApp may use various formats.
    Returns path to a MP3 file that Perplexity can handle.
    """
    suffix = audio_path.suffix.lower()
    
    # If already in a supported format, return as-is
    if suffix in SUPPORTED_FORMATS:
        return audio_path
    
    # Convert to MP3
    mp3_path = audio_path.with_suffix(".mp3")
    
    # If a converted version already exists, use it
    if mp3_path.exists():
        print(f"  ✓ Using existing converted file: {mp3_path.name}")
        return mp3_path
    
    print(f"  🔄 Converting {suffix} → .mp3...")
    import subprocess
    
    result = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-acodec", "libmp3lame", "-ab", "128k",
         "-y", str(mp3_path)],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Audio conversion failed: {result.stderr}")
    
    print(f"  ✓ Converted to {mp3_path.name}")
    return mp3_path


# ── Prompts ──────────────────────────────────────────────────────────

TRANSCRIPTION_PROMPT = """You are The Doctor's audio assistant. 

I am sending you an audio recording in Urdu/Hindi from an elderly diabetes patient.

Please do the following:
1. TRANSCRIBE the audio accurately in Roman Urdu (transliteration) if needed
2. TRANSLATE the content to English
3. Provide the full English transcription

Then EXTRACT the following structured information and present it in a table:

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
  "raw_transcript_urdu": "Roman Urdu transcription",
  "raw_transcript_english": "English translation",
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

# ── Perplexity Client Setup ─────────────────────────────────────────

def get_perplexity_client():
    """Initialize and return a Perplexity client with cookies."""
    if COOKIES_PATH.exists():
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cookies = perplexity.normalize_cookies(raw)
        print(f"  ✓ Loaded cookies from {COOKIES_PATH}")
    else:
        print(f"  ⚠️  No cookies found at {COOKIES_PATH}, using empty cookies")
        cookies = {}
    
    return perplexity.Client(cookies)


# ── Data Storage ─────────────────────────────────────────────────────

def load_json(path):
    """Load JSON file, return empty list/dict if not found."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return [] if path == TRANSCRIPT_FILE else {}


def save_json(path, data):
    """Save data to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved to {path.name}")


# ── Audio Processing ─────────────────────────────────────────────────

def process_audio(audio_path: str, recording_time: Optional[str] = None) -> dict:
    """
    Process an audio file through Perplexity.
    
    Args:
        audio_path: Path to the audio file
        recording_time: When the recording was made (auto if None)
    
    Returns:
        Dictionary with transcription and extracted health data
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
    
    # Convert audio if needed (Telegram/WhatsApp formats → MP3)
    audio_file = convert_audio(audio_file)
    
    # Read audio file
    print("📂 Reading audio file...")
    with open(audio_file, "rb") as f:
        audio_data = f.read()
    
    file_size_mb = len(audio_data) / (1024 * 1024)
    print(f"  ✓ Size: {file_size_mb:.1f} MB")
    
    # Initialize Perplexity client
    print("🔑 Initializing Perplexity client...")
    perp_client = get_perplexity_client()
    
    # Build the prompt
    prompt = TRANSCRIPTION_PROMPT.format(recording_time=recording_time)
    
    # Send to Perplexity
    print("📤 Sending to Perplexity for transcription + data extraction...")
    print("  (This may take 30-60 seconds for audio processing)\n")
    
    try:
        result = perp_client.search(
            query=prompt,
            mode="pro",
            model="sonar",
            files={audio_file.name: audio_data},
            stream=False,
            language="en",
        )
        
        print("  ✓ Response received from Perplexity\n")
        
        # Parse the response
        # The result structure depends on the API response format
        response_text = ""
        if isinstance(result, dict):
            response_text = result.get("answer", result.get("text", json.dumps(result)))
        elif isinstance(result, str):
            response_text = result
        else:
            response_text = str(result)
        
        # Try to extract JSON from the response
        extracted = try_extract_json(response_text)
        
        # Save the raw result
        save_result(audio_file.name, recording_time, response_text, extracted)
        
        return {
            "success": True,
            "filename": audio_file.name,
            "recording_time": recording_time,
            "raw_response": response_text,
            "extracted": extracted,
        }
    
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        return {
            "success": False,
            "filename": audio_file.name,
            "error": str(e),
        }


def try_extract_json(text: str) -> dict:
    """Try to extract JSON from Perplexity's response."""
    import re
    
    # Try to find JSON block
    json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON in code blocks
    json_block = re.search(r'```(?:json)?\s*\n?(\{.*?\})\n?\s*```', text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass
    
    return {"raw_text": text[:500]}


def save_result(filename, recording_time, response_text, extracted):
    """Save transcription and extracted data to storage."""
    
    # ── Save transcript ──
    transcripts = load_json(TRANSCRIPT_FILE)
    transcript_entry = {
        "id": len(transcripts) + 1,
        "filename": filename,
        "recording_time": recording_time,
        "processed_at": datetime.now().isoformat(),
        "raw_response": response_text,
    }
    transcripts.append(transcript_entry)
    save_json(TRANSCRIPT_FILE, transcripts)
    
    # ── Save extracted health data ──
    if extracted and "extracted_data" in extracted:
        health_data = load_json(HEALTH_DATA_FILE)
        if isinstance(health_data, dict):
            # Convert old format to list if needed
            entries = [health_data] if health_data else []
        else:
            entries = health_data
        
        entry = {
            "id": len(entries) + 1,
            "recording_time": recording_time,
            "processed_at": datetime.now().isoformat(),
            **extracted.get("extracted_data", {}),
            "summary": extracted.get("summary", ""),
            "raw_transcript": extracted.get("raw_transcript_english", ""),
        }
        entries.append(entry)
        save_json(HEALTH_DATA_FILE, entries)


# ── CLI Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="The Doctor — Process health audio notes")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--time", "-t", help="Recording time (default: now)", default=None)
    
    args = parser.parse_args()
    result = process_audio(args.audio_file, args.time)
    
    if result["success"]:
        print(f"\n✅ Processing complete!")
        print(f"📄 Transcript saved to: {TRANSCRIPT_FILE}")
        print(f"📊 Health data saved to: {HEALTH_DATA_FILE}")
    else:
        print(f"\n❌ Processing failed: {result.get('error', 'Unknown error')}")
