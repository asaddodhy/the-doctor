"""
The Doctor — Dashboard
Simple web dashboard to view raw transcripts and extracted health data.
"""

import json
from pathlib import Path
from string import Template

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

# ── Config ──────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"
TRANSCRIPT_FILE = DATA_DIR / "transcripts.json"
HEALTH_DATA_FILE = DATA_DIR / "health_data.json"

app = FastAPI(title="The Doctor — Dashboard")


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
        .tab-bar { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
        .tab { padding: 0.6rem 1.5rem; border: none; border-radius: 8px;
               cursor: pointer; font-size: 0.9rem; background: #ddd; }
        .tab.active { background: #0f3460; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        table { width: 100%; border-collapse: collapse; background: white;
                border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        th, td { padding: 0.8rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.85rem; }
        th { background: #f8f9fa; font-weight: 600; position: sticky; top: 0; }
        tr:hover { background: #f8f9fa; }
        .transcript-card { background: white; border-radius: 12px; padding: 1rem; margin-bottom: 1rem;
                           box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .transcript-header { display: flex; gap: 1rem; align-items: center; margin-bottom: 0.5rem;
                             font-size: 0.85rem; color: #666; }
        .transcript-card pre { background: #f8f9fa; padding: 0.8rem; border-radius: 8px;
                               font-size: 0.8rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
        .badge { background: #0f3460; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; }
        .time { color: #999; font-size: 0.8rem; }
        .empty { text-align: center; padding: 3rem; color: #999; }
        @media (max-width: 768px) { .stats { flex-direction: column; } table { font-size: 0.75rem; }
            th, td { padding: 0.5rem; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>The Doctor -- Dashboard</h1>
        <p>Health tracking for audio notes -- transcripts and extracted data</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="number">$total_notes</div>
            <div class="label">Total Audio Notes</div>
        </div>
        <div class="stat-card">
            <div class="number">$total_entries</div>
            <div class="label">Health Entries</div>
        </div>
        <div class="stat-card">
            <div class="number" style="font-size:1rem">$last_update</div>
            <div class="label">Last Update</div>
        </div>
    </div>

    <div class="container">
        <div class="tab-bar">
            <button class="tab active" data-tab="health" onclick="switchTab('health')">Health Data</button>
            <button class="tab" data-tab="transcripts" onclick="switchTab('transcripts')">Raw Transcripts</button>
        </div>

        <div id="health" class="tab-content active">
            $health_table
        </div>

        <div id="transcripts" class="tab-content">
            $transcript_cards
        </div>
    </div>

    <script>
        function switchTab(name) {
            document.querySelectorAll('.tab-content').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.getElementById(name).classList.add('active');
            document.querySelector('.tab[data-tab="' + name + '"]').classList.add('active');
        }
    </script>
</body>
</html>
""")


# ── Data Loading ─────────────────────────────────────────────────────

def load_data():
    """Load transcripts and health data."""
    transcripts = []
    health_data = []
    
    if TRANSCRIPT_FILE.exists():
        with open(TRANSCRIPT_FILE, "r") as f:
            try:
                transcripts = json.load(f)
            except json.JSONDecodeError:
                transcripts = []
    
    if HEALTH_DATA_FILE.exists():
        with open(HEALTH_DATA_FILE, "r") as f:
            try:
                data = json.load(f)
                health_data = data if isinstance(data, list) else [data]
            except json.JSONDecodeError:
                health_data = []
    
    return transcripts, health_data


def build_health_table(health_data):
    """Build HTML table rows from health data."""
    if not health_data:
        return '<div class="empty">No health data yet. Send an audio note to get started.</div>'
    
    rows = ""
    for entry in reversed(health_data[-50:]):
        rows += "<tr>"
        rows += "<td>" + str(entry.get('id', '-')) + "</td>"
        rows += "<td>" + str(entry.get('recording_time', '-')) + "</td>"
        rows += "<td>" + str(entry.get('blood_sugar', '-')) + "</td>"
        rows += "<td>" + str(entry.get('meals', '-')) + "</td>"
        rows += "<td>" + str(entry.get('activity', '-')) + "</td>"
        rows += "<td>" + str(entry.get('medications', '-')) + "</td>"
        rows += "<td>" + str(entry.get('symptoms', '-')) + "</td>"
        rows += "<td>" + str(entry.get('mood', '-')) + "</td>"
        rows += "<td>" + str(entry.get('summary', ''))[:80] + "</td>"
        rows += "</tr>"
    
    return (
        '<div style="overflow-x:auto">'
        '<table><thead><tr>'
        '<th>#</th><th>Recording Time</th><th>Blood Sugar</th><th>Meals</th><th>Activity</th>'
        '<th>Medications</th><th>Symptoms</th><th>Mood</th><th>Summary</th>'
        '</tr></thead><tbody>' + rows + '</tbody></table>'
        '</div>'
    )


def build_transcript_cards(transcripts):
    """Build HTML transcript cards."""
    if not transcripts:
        return '<div class="empty">No transcripts yet. Send an audio note to get started.</div>'
    
    cards = ""
    for t in reversed(transcripts[-20:]):
        raw = str(t.get("raw_response", ""))[:300]
        tid = str(t.get('id', '-'))
        rtime = str(t.get('recording_time', '-'))
        ptime = str(t.get('processed_at', ''))[:19]
        
        cards += '<div class="transcript-card">'
        cards += '<div class="transcript-header">'
        cards += '<span class="badge">#' + tid + '</span>'
        cards += '<span>' + rtime + '</span>'
        cards += '<span class="time">' + ptime + '</span>'
        cards += '</div>'
        cards += '<pre>' + raw + ('...' if len(str(t.get('raw_response', ''))) > 300 else '') + '</pre>'
        cards += '</div>'
    
    return '<div class="transcripts-list">' + cards + '</div>'


# ── Routes ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page."""
    transcripts, health_data = load_data()
    
    total_notes = len(transcripts)
    total_entries = len(health_data)
    last_update = str(transcripts[-1].get('processed_at', '')[:10]) if transcripts else "No data yet"
    
    html = HTML_TEMPLATE.substitute(
        total_notes=str(total_notes),
        total_entries=str(total_entries),
        last_update=last_update,
        health_table=build_health_table(health_data),
        transcript_cards=build_transcript_cards(transcripts),
    )
    
    return HTMLResponse(content=html)


@app.get("/api/data")
async def api_data():
    """Return raw JSON data."""
    transcripts, health_data = load_data()
    return {"transcripts": transcripts[-20:], "health_data": health_data[-50:]}


if __name__ == "__main__":
    print("Starting The Doctor Dashboard...")
    print("   Open http://localhost:9001 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=9001)
