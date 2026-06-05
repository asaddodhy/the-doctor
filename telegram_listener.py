"""
The Doctor — Telegram Voice Listener

Receives voice notes from authorized Telegram users, transcribes via
Groq Whisper API, then translates to Urdu and English via Perplexity.

Usage:
    python telegram_listener.py

Runs as a long-lived daemon alongside the dashboard.
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ── Environment MUST be loaded BEFORE importing processor ───────────────
# processor.py reads env vars at module level (GROQ_API_KEY, etc.)
PROJECT_ROOT = Path(__file__).parent

_env_file = ".env.test" if os.getenv("DOCTOR_ENV", "") == "test" else ".env"
load_dotenv(PROJECT_ROOT / _env_file)
print(f"  📋 Loaded config from: {_env_file}")
BOT_TOKEN = os.getenv("DOCTOR_BOT_TOKEN", "")
ALLOWED_USERS_STR = os.getenv("DOCTOR_ALLOWED_USERS", "")
ALLOWED_USERS = {int(uid.strip()) for uid in ALLOWED_USERS_STR.split(",") if uid.strip()}

# ── Now import processor (it will see the env vars from above) ──────────
sys.path.insert(0, str(PROJECT_ROOT))

from processor import (
    DATA_DIR,
    TRANSCRIPT_FILE,
    GROQ_STT_MODEL,
    transcribe as processor_transcribe,
    translate_transcription as processor_translate,
    load_json,
    save_json,
)

# ─── Transcription via Groq Whisper ────────────────────────────────────


def transcribe_audio(audio_path: str) -> Optional[str]:
    """Transcribe audio using Groq Whisper API via processor."""
    return processor_transcribe(audio_path)


# ─── Transcription Translation (Urdu + English) ─────────────────────────


def translate_transcription_text(transcription: str) -> dict:
    """
    Translate transcription to Urdu and English via Perplexity.
    Delegates to processor.translate_transcription().
    """
    return processor_translate(transcription)


# ─── Save Results ────────────────────────────────────────────────────────


def save_results(filename: str, recording_time: str, transcription: str, translated: dict):
    """Save transcription and translated text to storage."""
    # Save transcript with translations
    transcripts = load_json(TRANSCRIPT_FILE)
    transcript_entry = {
        "id": len(transcripts) + 1,
        "filename": filename,
        "source": "telegram",
        "recording_time": recording_time,
        "processed_at": datetime.now().isoformat(),
        "transcription": transcription,
        "translated_urdu": translated.get("urdu", ""),
        "translated_english": translated.get("english", ""),
    }
    transcripts.append(transcript_entry)
    save_json(TRANSCRIPT_FILE, transcripts)


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

    print()
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

            # Step 1: Transcribe via Groq Whisper (handles OGG directly)
            await update.message.reply_text("🎤 Transcribing audio...")
            transcription = transcribe_audio(tmp_path)

            if not transcription:
                await update.message.reply_text("❌ Transcription failed. Check server logs.")
                cleanup(tmp_path)
                return

            print(f"  ✅ Transcription ({len(transcription)} chars)")
            print(f"     Preview: {transcription[:200]}...")

            # Step 2: Translate to Urdu + English via Perplexity
            filename = f"voice_{update.message.message_id}.ogg"
            await update.message.reply_text("🌐 Translating to Urdu and English...")
            translated = translate_transcription_text(transcription)
            save_results(filename, recording_time, transcription, translated)

            # Check if translation failed
            error_msg = translated.get("error", "")
            if error_msg:
                response = f"📝 **Transcription:**\n\n{transcription}\n\n⚠️ **Translation unavailable:** {error_msg}\n\nWant me to restart the Perplexity server? (send 'restart')"
                await update.message.reply_text(response, parse_mode="Markdown")
            else:
                # Reply with Urdu and English versions
                urdu_text = translated.get("urdu", "") or ""
                english_text = translated.get("english", "") or transcription

                response = "📝 **Transcription:**\n\n"
                if urdu_text:
                    response += f"**🇵🇰 Urdu:**\n{urdu_text}\n\n"
                response += f"**🇬🇧 English:**\n{english_text}"

                if len(response) > 4000:
                    response = response[:3997] + "..."

                await update.message.reply_text(response, parse_mode="Markdown")

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
