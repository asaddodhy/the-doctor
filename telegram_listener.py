"""
The Doctor — Telegram Voice Listener

Receives voice notes from authorized Telegram users, transcribes via the
existing Perplexity bridge script (perplexity-stack/scripts/transcribe.py),
then passes the transcription to The Doctor's health data extraction pipeline.

Usage:
    python telegram_listener.py

Runs as a long-lived daemon alongside the dashboard.
"""

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ffmpeg available for audio conversion
FFMPEG = "ffmpeg"

# ── Add The Doctor's root to sys.path ───────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from processor import (
    DATA_DIR,
    HEALTH_DATA_FILE,
    TRANSCRIPT_FILE,
    transcribe as processor_transcribe,
    extract_health as processor_extract_health,
    load_json,
    save_json,
)

# ─── Environment ────────────────────────────────────────────────────────

# Load test .env if DOCTOR_ENV=test, otherwise load production .env
_env_file = ".env.test" if os.getenv("DOCTOR_ENV", "") == "test" else ".env"
load_dotenv(PROJECT_ROOT / _env_file)
print(f"  📋 Loaded config from: {_env_file}")
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

# ─── Audio Conversion ─────────────────────────────────────────────────


def convert_to_wav(audio_path: str) -> Optional[str]:
    """
    Convert audio file to WAV format using ffmpeg.
    Perplexity's GPT-4.5 model works with WAV but not OGG (Telegram's format).
    Returns path to converted WAV file, or None on failure.
    """
    wav_path = audio_path.rsplit(".", 1)[0] + "_converted.wav"
    try:
        result = subprocess.run(
            [FFMPEG, "-y", "-i", audio_path, "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  ⚠️  Audio conversion failed: {result.stderr.strip()}")
            return None
        print(f"  🔄 Converted to WAV: {wav_path}")
        return wav_path
    except Exception as e:
        print(f"  ⚠️  Audio conversion error: {e}")
        return None


# ─── Bridge Script Call ─────────────────────────────────────────────────


def transcribe_audio(audio_path: str) -> Optional[str]:
    """
    Transcribe audio via the bridge script.
    Delegates to processor.transcribe() which uses the working setup.
    """
    return processor_transcribe(audio_path)


# ─── Health Data Extraction from Text ───────────────────────────────────


def extract_health_from_transcription(transcription: str, recording_time: str) -> dict:
    """
    Extract health data from a transcription.
    Delegates to processor.extract_health() which uses the working setup.
    """
    return processor_extract_health(transcription, recording_time)


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
        "processed_at": datetime.now().isoformat(),
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
            "processed_at": datetime.now().isoformat(),
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

            # Step 0: Convert OGG to WAV (Perplexity GPT-4.5 doesn't support OGG)
            wav_path = convert_to_wav(tmp_path)
            audio_for_transcription = wav_path if wav_path else tmp_path

            # Step 1: Transcribe via bridge script
            await update.message.reply_text("🎤 Transcribing audio...")
            transcription = transcribe_audio(audio_for_transcription)

            if not transcription:
                await update.message.reply_text("❌ Transcription failed. Check server logs.")
                cleanup(tmp_path)
                return

            print(f"  ✅ Transcription ({len(transcription)} chars)")
            print(f"     Preview: {transcription[:200]}...")

            # Step 2: Extract health data and save
            filename = f"voice_{update.message.message_id}.ogg"
            await update.message.reply_text("🔍 Extracting health data...")
            extracted = extract_health_from_transcription(transcription, recording_time)
            save_results(filename, recording_time, transcription, extracted)

            # Reply with the transcription and health data
            preview = transcription[:1500]
            response = f"✅ Transcription:\n\n{preview}"
            if len(transcription) > 1500:
                response += "\n\n*(truncated — full text saved to dashboard)*"

            # Add health data summary if available
            if extracted and "extracted_data" in extracted:
                ed = extracted["extracted_data"]
                summary_lines = []
                if ed.get("blood_sugar"):
                    summary_lines.append(f"🩸 Blood Sugar: {ed['blood_sugar']}")
                if ed.get("meals"):
                    summary_lines.append(f"🍽️ Meals: {ed['meals']}")
                if ed.get("activity"):
                    summary_lines.append(f"🚶 Activity: {ed['activity']}")
                if ed.get("medications"):
                    summary_lines.append(f"💊 Medications: {ed['medications']}")
                if ed.get("symptoms"):
                    summary_lines.append(f"🤒 Symptoms: {ed['symptoms']}")
                if ed.get("mood"):
                    summary_lines.append(f"😊 Mood: {ed['mood']}")
                if summary_lines:
                    response += f"\n\n📋 **Health Data:**\n" + "\n".join(summary_lines)
                if extracted.get("summary"):
                    response += f"\n\n📝 {extracted['summary']}"

            dashboard_port = os.getenv("DOCTOR_DASHBOARD_PORT", "9001")
            response += f"\n\n📊 Dashboard: http://localhost:{dashboard_port}"
            await update.message.reply_text(response, parse_mode="Markdown")

            print(f"  ✅ Voice note processed successfully")

        except Exception as e:
            print(f"  ❌ Error processing voice note: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")

        finally:
            if "tmp_path" in locals():
                cleanup(tmp_path)
            if "wav_path" in locals() and wav_path:
                cleanup(wav_path)

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
