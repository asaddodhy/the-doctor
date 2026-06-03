# AGENTS.md — The Doctor

> **IMPORTANT — Read this first.** The full voice pipeline (Groq STT → Perplexity medical extraction → save → reply → thread delete) is already implemented in `processor.py` and `telegram_listener.py`. Michael-Macbook14 built and tested this. **Do NOT change the pipeline logic.** Your job is to:
> 1. Read and understand the code + pipeline below
> 2. Fix bugs if they arise
> 3. Improve the extraction prompt or add new medical fields as Asad requests
> 4. Keep the Perplexity API server running (port 8766)
>
> If you're unsure about any part of the pipeline, read `processor.py` and `telegram_listener.py` first before making changes.

## Co-work

All team rules, inbox, communication, and session files live in the `asaddodhy/co-work` repo.

**At the start of every session, read these files from co-work:**
1. `AGENTS.md` — canonical team rules
2. `INBOX.md` — check for new messages
3. `AGENT_QA.md` — check for announcements, tasks, questions

**How to read co-work files:**
```bash
cd ~/Documents/Development/co-work && git pull origin main
cat AGENTS.md
cat INBOX.md
cat AGENT_QA.md
```

---

## Project Config

| Setting | Value |
|---------|-------|
| **Repo** | `asaddodhy/the-doctor` |
| **Primary agent** | The-Doctor |
| **Git identity** | `The-Doctor <the-doctor@my-ai-team.dev>` |

---

## Project Overview

The Doctor receives audio notes (Urdu/Hindi) from Asad's father via Telegram/WhatsApp, transcribes them to English using **Groq Whisper API**, extracts structured health data (blood sugar, meals, activity, medications) via **Perplexity API server**, and displays everything on a simple dashboard.

---

## Pipeline (end-to-end)

```
Telegram voice message
  → Groq Whisper API (whisper-large-v3) — transcribes audio to text
    → Perplexity API server (localhost:8766) — extracts medical data as JSON
      → Save to data/transcripts.json + data/health_data.json
        → Reply to Telegram user with structured summary
          → Auto-delete Perplexity thread (cleanup)
```

### Key components

| Component | What it does | How to check |
|-----------|-------------|--------------|
| **Groq Whisper** | STT — transcribes audio (OGG direct, no conversion needed) | `curl https://api.groq.com/openai/v1/audio/transcriptions` |
| **Perplexity API server** | FastAPI wrapper on port 8766 — queries Perplexity AI via web API | `lsof -ti:8766` to check if running |
| **processor.py** | `transcribe()` + `extract_health()` — core pipeline functions | Main entry point for audio processing |
| **telegram_listener.py** | Telegram bot daemon — receives voice, runs pipeline, replies | Runs as part of `start-all.sh` |

### Startup

```bash
# Start all services (Perplexity API server + dashboard + WhatsApp + Telegram)
./start-all.sh start

# Or just the Perplexity API server
./start-perplexity-api.sh

# Test mode
DOCTOR_ENV=test ./start-all.sh start
```

### Required env vars (in .env)

```
GROQ_API_KEY=gsk_...                    # Groq Whisper STT
PERPLEXITY_API_URL=http://127.0.0.1:8766  # Local Perplexity API server
DOCTOR_BOT_TOKEN=...                     # Telegram bot token
DOCTOR_ALLOWED_USERS=...                 # Authorized Telegram user IDs
```

### Key files

| File | Purpose |
|------|---------|
| `telegram_listener.py` | Telegram bot — receives voice, orchestrates pipeline, replies |
| `processor.py` | `transcribe()` (Groq → fallback bridge) + `extract_health()` (Perplexity API) |
| `start-all.sh` | Manages all services (dashboard, WhatsApp, Perplexity API, Telegram) |
| `start-perplexity-api.sh` | Standalone launcher for Perplexity API server |
| `start-all-test.sh` | Test-mode variant for validation |
| `data/transcripts.json` | Stored transcriptions |
| `data/health_data.json` | Stored extracted health data (JSON) |
| `launchd/com.thedoctor.start-all.plist` | Launchd auto-start on boot |

### Thread cleanup

Every Perplexity query auto-deletes its thread after extraction (in `processor.py`). No manual cleanup needed.
