# AGENTS.md — The Doctor

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
| **Primary agent** | Michael-Macbook14 |
| **Git identity** | `Michael-Macbook14 <michael-macbook14@my-ai-team.dev>` |

---

## Project Overview

The Doctor receives audio notes (Urdu/Hindi) from Asad's father via Telegram/WhatsApp, transcribes them to English using Perplexity, extracts structured health data (blood sugar, meals, activity, medications), and displays everything on a simple dashboard.
