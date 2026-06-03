"""
The Doctor — Dashboard
Simple web dashboard to view raw transcripts with Urdu/English translations.
"""

import json
import os
from pathlib import Path
from string import Template

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

# ── Config ──────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"

# Support test environment (DOCTOR_ENV=test) — use prefixed data files
DOCTOR_ENV = os.getenv("DOCTOR_ENV", "")
_DATA_PREFIX = "test_" if DOCTOR_ENV == "test" else ""
TRANSCRIPT_FILE = DATA_DIR / f"{_DATA_PREFIX}transcripts.json"

IS_TEST_MODE = DOCTOR_ENV == "test"

app = FastAPI(title="The Doctor — Dashboard" + (" (TEST MODE)" if IS_TEST_MODE else ""))


# ── HTML Template ───────────────────────────────────────────────────

HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Doctor — Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #f0f2f5; color: #1a1a2e; }
        .header { background: linear-gradient(135deg, #1a1a2e, #16213e);
                  color: white; padding: 2rem; text-align: center; }
        .header h1 { font-size: 2rem; } .header p { opacity: 0.8; margin-top: 0.5rem; }
        .stats { display: flex; gap: 1rem; justify-content: center; padding: 1.5rem;
                 max-width: 900px; margin: 0 auto; flex-wrap: wrap; }
        .stat-card { background: white; border-radius: 12px; padding: 1.2rem 2rem;
                     box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; flex: 1; min-width: 150px; }
        .stat-card .number { font-size: 2rem; font-weight: bold; color: #0f3460; }
        .stat-card .label { font-size: 0.85rem; color: #666; margin-top: 0.3rem; }
        .container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
        .transcript-card { background: white; border-radius: 12px; padding: 1rem; margin-bottom: 1rem;
                           box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .transcript-header { display: flex; gap: 1rem; align-items: center; margin-bottom: 0.5rem;
                             font-size: 0.85rem; color: #666; }
        .transcript-card pre { background: #f8f9fa; padding: 0.8rem; border-radius: 8px;
                               font-size: 0.8rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
        .badge { background: #0f3460; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; }
        .time { color: #999; font-size: 0.8rem; }
        .empty { text-align: center; padding: 3rem; color: #999; }
        @media (max-width: 768px) { .stats { flex-direction: column; } }
    </style>
</head>
<body>
    <div class="header">
        $test_banner
        <h1>The Doctor -- Dashboard</h1>
        <p>Audio note transcripts -- raw transcription with Urdu/English translation</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="number">$total_notes</div>
            <div class="label">Total Audio Notes</div>
        </div>
        <div class="stat-card">
            <div class="number" style="font-size:1rem">$last_update</div>
            <div class="label">Last Update</div>
        </div>
    </div>

    <div class="container">
        $transcript_cards
    </div>
</body>
</html>
""")


# ── Data Loading ─────────────────────────────────────────────────────

def load_data():
    """Load transcripts from the data file."""
    transcripts = []
    
    if TRANSCRIPT_FILE.exists():
        with open(TRANSCRIPT_FILE, "r") as f:
            try:
                transcripts = json.load(f)
            except json.JSONDecodeError:
                transcripts = []
    
    return transcripts





def build_transcript_cards(transcripts):
    """Build HTML transcript cards showing raw transcription, Urdu, and English."""
    if not transcripts:
        return '<div class="empty">No transcripts yet. Send an audio note to get started.</div>'
    
    cards = ""
    for t in reversed(transcripts[-50:]):
        tid = str(t.get('id', '-'))
        rtime = str(t.get('recording_time', '-'))
        ptime = str(t.get('processed_at', ''))[:19]
        transcription = str(t.get('transcription', ''))
        translated_urdu = str(t.get('translated_urdu', ''))
        translated_english = str(t.get('translated_english', ''))
        
        cards += '<div class="transcript-card">'
        cards += '<div class="transcript-header">'
        cards += '<span class="badge">#' + tid + '</span>'
        cards += '<span>' + rtime + '</span>'
        cards += '<span class="time">' + ptime + '</span>'
        cards += '</div>'
        cards += '<h3 style="margin: 0.5rem 0 0.25rem; font-size: 0.9rem; color: #333;">Raw Transcription</h3>'
        cards += '<pre>' + transcription + '</pre>'
        cards += '<h3 style="margin: 0.5rem 0 0.25rem; font-size: 0.9rem; color: #333;">Urdu Translation</h3>'
        cards += '<pre>' + translated_urdu + '</pre>'
        cards += '<h3 style="margin: 0.5rem 0 0.25rem; font-size: 0.9rem; color: #333;">English Translation</h3>'
        cards += '<pre>' + translated_english + '</pre>'
        cards += '</div>'
    
    return '<div class="transcripts-list">' + cards + '</div>'


# ── Routes ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page."""
    transcripts = load_data()
    
    total_notes = len(transcripts)
    last_update = str(transcripts[-1].get('processed_at', '')[:10]) if transcripts else "No data yet"
    
    test_banner_html = (
        '<div style="background: #e74c3c; color: white; padding: 0.5rem; '
        'border-radius: 8px; margin-bottom: 1rem; font-weight: bold; '
        'font-size: 0.9rem; display: inline-block;">🧪 TEST MODE</div>'
    ) if IS_TEST_MODE else ""

    html = HTML_TEMPLATE.substitute(
        total_notes=str(total_notes),
        last_update=last_update,
        test_banner=test_banner_html,
        transcript_cards=build_transcript_cards(transcripts),
    )
    
    return HTMLResponse(content=html)


@app.get("/api/data")
async def api_data():
    """Return raw JSON data."""
    transcripts = load_data()
    return {"transcripts": transcripts[-50:]}


if __name__ == "__main__":
    port = int(os.getenv("DOCTOR_DASHBOARD_PORT", "9001"))
    mode = "TEST MODE" if IS_TEST_MODE else "Production"
    print(f"Starting The Doctor Dashboard ({mode})...")
    print(f"   Open http://localhost:{port} in your browser")
    uvicorn.run(app, host="0.0.0.0", port=port)
