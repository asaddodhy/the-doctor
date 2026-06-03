# The Doctor — Change Handbook

This is a **local-only** handoff file between Michael and The Doctor.
No GitHub, no git identity needed. Just read, act, and mark as read.

## How it works

1. **Michael** appends changes/instructions at the top of this file
2. **The Doctor** reads this at the start of every session
3. **The Doctor** marks each entry as `[x]` once read and understood
4. **The Doctor** can leave messages for Michael at the bottom

---

## Messages from the doctor (for Michael)

_Use this section to report errors, ask questions, or request changes._

- [ ] _(The doctor writes here when it finds issues or needs help)_

---

## Messages from Michael (for the doctor)

---

### 2026-06-02 — Full pipeline implemented (read before making changes)

**⚠️ DO NOT change the pipeline logic without asking Asad first.**

**Pipeline (already implemented):**
```
Telegram voice → Groq Whisper STT → Perplexity API server (port 8766)
  → Medical JSON extraction → Save + reply → Thread auto-delete
```

**Files changed:**
- `processor.py` — `transcribe()` (Groq), `extract_health()` (Perplexity API)
- `telegram_listener.py` — Groq STT, health extraction enabled, structured reply
- `start-all.sh` — Perplexity API server added as managed service
- `start-perplexity-api.sh` — NEW launcher for Perplexity API server
- `start-all-test.sh` — Added to repo (test-mode variant)
- `AGENTS.md` — Full pipeline docs + instructions for you
- `pyproject.toml` — Added `requests` dependency
- `.env.test` — Added `GROQ_API_KEY` placeholder

**Key behaviors:**
- Groq STT is PRIMARY. If it fails, error is shown to user (no silent fallback)
- OGG audio handled directly (no WAV conversion needed)
- After extraction, Perplexity thread is auto-deleted
- Perplexity API server must be running (port 8766) — started via `start-all.sh`

**Required env vars (in `.env`):**
```
GROQ_API_KEY=gsk_...           # Already set locally
PERPLEXITY_API_URL=http://127.0.0.1:8766
DOCTOR_BOT_TOKEN=...
DOCTOR_ALLOWED_USERS=...
```

**Read by The Doctor:** [ ]

---

### 2026-06-02 — Voice forwarding set up for OpenCode bot (reference)

This does NOT affect The Doctor, but good to know:
- OpenCode bot: voice → Groq STT → forwarded to OpenCode as user prompt
- No Perplexity, no extraction — just "as if typed it"
- Lives in npm package `voice.js` (not in this repo)

**Read by The Doctor:** [ ]
