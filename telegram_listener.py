"""
The Doctor — Telegram Voice Listener

Receives voice notes from authorized Telegram users, transcribes via the
existing Perplexity bridge script (perplexity-stack/scripts/transcribe.py),
then passes the transcription to The Doctor's health data extraction pipeline.

Usage:
    python telegram_listener.py

Runs as a long-lived daemon alongside the dashboard.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Add The Doctor's root to sys.path ───────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from processor import (
    DATA_DIR,
    HEALTH_DATA_FILE,
    TRANSCRIPT_FILE,
    get_perplexity_client,
    load_json,
    save_json,
    TRANSCRIPTION_PROMPT,
)

# ─── Environment ────────────────────────────────────────────────────────

load_dotenv(PROJECT_ROOT / ".env")
BOT_TOKEN = os.getenv("DOCTOR_BOT_TOKEN", "")
ALLOWED_USERS_STR = os.getenv("DOCTOR_ALLOWED_USERS", "")
ALLOWED_USERS = {int(uid.strip()) for uid in ALLOWED_USERS_STR.split(",") if uid.strip()}

# Path to the existing bridge script
BRIDGE_SCRIPT = os.getenv(
    "DOCTOR_BRIDGE_SCRIPT",
    str(Path.home() / "Documents" / "Development" / "perplexity-stack" / "scripts" / "transcribe.py"),
)
BRIDGE_PYTHON = os.getenv(
    "DOCTOR_BRIDGE_PYTHON",
    str(Path.home() / "Documents" / "Development" / "perplexity-stack" / "perplexity-web-wrapper" / ".venv" / "bin" / "python3"),
)

# ─── Bridge Script Call ─────────────────────────────────────────────────


def transcribe_audio(audio_path: str) -> Optional[str]:
    """
    Call the existing Perplexity bridge script to transcribe an audio file.

    Returns:
        Transcription text, or None on failure.
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


# ─── Health Data Extraction from Text ───────────────────────────────────


def extract_health_from_transcription(transcription: str, recording_time: str) -> dict:
    """
    Send the transcription text to Perplexity for health data extraction.

    Uses the same prompt template as processor.process_audio() but sends
    text only (no audio file), with the transcription provided as context.

    Returns extracted health data dict (may be empty if parsing fails).
    """
    prompt = TRANSCRIPTION_PROMPT.format(recording_time=recording_time)
    # Prepend the already-transcribed text
    full_prompt = (
        f"I already transcribed this audio. Here is the transcription:\n\n"
        f"{transcription}\n\n"
        f"---\n\n{prompt}"
    )

    print("  📤 Extracting health data from transcription...")
    perp_client = get_perplexity_client()

    try:
        result = perp_client.search(
            query=full_prompt,
            mode="pro",
            model="sonar",
            stream=False,
            language="en",
        )

        response_text = ""
        if isinstance(result, dict):
            response_text = result.get("answer", result.get("text", json.dumps(result)))
        elif isinstance(result, str):
            response_text = result
        else:
            response_text = str(result)

        # Try to extract JSON from response
        extracted = _try_extract_json(response_text)
        return extracted

    except Exception as e:
        print(f"  ❌ Health extraction failed: {e}")
        return {"raw_text": transcription[:500]}


def _try_extract_json(text: str) -> dict:
    """Try to extract JSON from Perplexity's response."""
    import re

    # Try to find JSON block
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try JSON in code blocks
    json_block = re.search(r"```(?:json)?\s*\n?(\{.*?\})\n?\s*```", text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    return {"raw_text": text[:500]}


# ─── Save Results ────────────────────────────────────────────────────────


def save_results(filename: str, recording_time: str, transcription: str, extracted: dict):
    """Save transcription and extracted health data to storage."""
    # Save transcript
    transcripts = load_json(TRANSCRIPT_FILE)
    transcript_entry = {
        "id": len(transcripts) + 1,
        "filename": filename,
        "source": "telegram",
        "recording_time": recording_time,
        "processed_at": __import__("datetime").datetime.now().isoformat(),
        "transcription": transcription,
    }
    transcripts.append(transcript_entry)
    save_json(TRANSCRIPT_FILE, transcripts)

    # Save extracted health data
    if extracted and "extracted_data" in extracted:
        health_data = load_json(HEALTH_DATA_FILE)
        if isinstance(health_data, dict):
            entries = [health_data] if health_data else []
        else:
            entries = health_data

        entry = {
            "id": len(entries) + 1,
            "source": "telegram",
            "recording_time": recording_time,
            "processed_at": __import__("datetime").datetime.now().isoformat(),
            **extracted.get("extracted_data", {}),
            "summary": extracted.get("summary", ""),
            "raw_transcript": extracted.get("raw_transcript_english", transcription),
        }
        entries.append(entry)
        save_json(HEALTH_DATA_FILE, entries)


# ─── Telegram Bot Handler ────────────────────────────────────────────────


def start_bot():
    """Start the Telegram bot and listen for voice notes."""
    if not BOT_TOKEN:
        print("❌ DOCTOR_BOT_TOKEN not set in .env")
        print("   Get a token from @BotFather on Telegram, then:")
        print(f"   echo 'DOCTOR_BOT_TOKEN=your_token_here' >> {PROJECT_ROOT / '.env'}")
        sys.exit(1)

    try:
        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters, CommandHandler
    except ImportError:
        print("❌ python-telegram-bot not installed.")
        print("   Run: uv add python-telegram-bot")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("🏥 The Doctor — Telegram Voice Listener")
    print(f"{'='*60}")

    if ALLOWED_USERS:
        print(f"  👥 Allowed users: {', '.join(str(uid) for uid in ALLOWED_USERS)}")
    else:
        print("  ⚠️  No allowed users configured — anyone with the bot token can send messages")

    print(f"  🎤 Bridge script: {BRIDGE_SCRIPT}")
    print(f"  🐍 Bridge Python: {BRIDGE_PYTHON}")
    print()

    app = Application.builder().token(BOT_TOKEN).build()

    async def handle_voice(update, context):
        """Handle incoming voice messages."""
        user = update.effective_user
        user_id = user.id if user else None
        chat_id = update.effective_chat.id if update.effective_chat else None

        # Authorization check
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            print(f"  ⛔ Unauthorized voice note from user {user_id} ({user.full_name if user else '?'})")
            await update.message.reply_text("Sorry, you're not authorized to use this bot.")
            return

        print(f"\n  🎤 Voice note received from {user.full_name if user else '?'} (ID: {user_id})")
        await update.message.reply_text("🔄 Processing your voice note...")

        # Download the voice file
        voice = update.message.voice
        if not voice:
            await update.message.reply_text("❌ No voice data found.")
            return

        try:
            file = await voice.get_file()
            recording_time = update.message.date.strftime("%Y-%m-%d %H:%M:%S")

            # Download to temp file
            suffix = ".ogg"  # Telegram sends OGG Opus
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp_path = tmp.name
                await file.download_to_drive(tmp_path)

            print(f"  💾 Downloaded to: {tmp_path} ({os.path.getsize(tmp_path)} bytes)")

            # Step 1: Transcribe via bridge script
            await update.message.reply_text("🎤 Transcribing audio...")
            transcription = transcribe_audio(tmp_path)

            if not transcription:
                await update.message.reply_text("❌ Transcription failed. Check server logs.")
                cleanup(tmp_path)
                return

            print(f"  ✅ Transcription ({len(transcription)} chars)")
            print(f"     Preview: {transcription[:100]}...")

            # Step 2: Extract health data
            await update.message.reply_text("🏥 Extracting health data...")
            extracted = extract_health_from_transcription(transcription, recording_time)

            # Step 3: Save results
            filename = f"voice_{update.message.message_id}.ogg"
            save_results(filename, recording_time, transcription, extracted)

            # Step 4: Respond
            summary = extracted.get("summary", "") if isinstance(extracted, dict) else ""
            response = "✅ Done!\n\n"
            if summary:
                response += f"📋 {summary}\n\n"
            response += f"📊 Dashboard: http://localhost:9001"
            await update.message.reply_text(response)

            print(f"  ✅ Voice note processed successfully")

        except Exception as e:
            print(f"  ❌ Error processing voice note: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

        finally:
            if "tmp_path" in locals():
                cleanup(tmp_path)

    def cleanup(path):
        """Remove temp file."""
        try:
            os.unlink(path)
        except OSError:
            pass

    async def start_cmd(update, context):
        """Handle /start command."""
        user = update.effective_user
        user_id = user.id if user else None
        await update.message.reply_text(
            f"👋 Hello {user.first_name if user else ''}!\n\n"
            f"I'm The Doctor — send me a voice note and I'll transcribe it "
            f"and extract health data.\n\n"
            f"Your user ID is: `{user_id}`\n\n"
            f"Add this ID to `DOCTOR_ALLOWED_USERS` in the .env file to authorize yourself.",
            parse_mode="Markdown",
        )

    # Register handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Start
    print("  ✅ Bot started. Listening for voice notes...")
    print(f"  {'='*60}\n")
    app.run_polling(allowed_updates=["message"])


# ─── CLI Entry Point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    start_bot()
