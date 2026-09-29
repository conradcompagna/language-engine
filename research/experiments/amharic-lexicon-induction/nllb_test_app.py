"""
Ancient Greek Morfessor test app.

Loads a locally trained Morfessor model produced by
``experiment/train_morfessor_from_sqlite.py`` and exposes a small Flask UI for
trying Ancient Greek surface forms against the trained segmenter.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request
import morfessor

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "morfessor_grc"
MODEL_PATH = MODEL_DIR / "grc_model.reduced.bin"
MANIFEST_PATH = MODEL_DIR / "grc_manifest.json"

TOKEN_RE = re.compile(r"\S+", re.UNICODE)
MODEL_LOCK = threading.Lock()
IO = morfessor.MorfessorIO()
MODEL = None

app = Flask(__name__)


def normalize_token(token: str) -> str:
    token = unicodedata.normalize("NFC", (token or "").strip())
    token = token.strip("·.,;:!?()[]{}<>\"'")
    return unicodedata.normalize("NFC", token)


def split_input_text(text: str) -> list[str]:
    tokens = []
    for raw in TOKEN_RE.findall(text or ""):
        token = normalize_token(raw)
        if token:
            tokens.append(token)
    return tokens


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def ensure_model_loaded():
    global MODEL
    if MODEL is not None:
        return MODEL

    with MODEL_LOCK:
        if MODEL is not None:
            return MODEL
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "Missing trained Morfessor model. Run "
                "`python experiment/train_morfessor_from_sqlite.py` first."
            )
        MODEL = IO.read_binary_model_file(str(MODEL_PATH))
        return MODEL


def segment_token(token: str) -> dict:
    model = ensure_model_loaded()
    segments, score = model.viterbi_segment(token)
    parts = [str(part) for part in segments]
    return {
        "token": token,
        "segments": parts,
        "segmented": " + ".join(parts),
        "score": score,
    }


def analyze_text(text: str) -> dict:
    tokens = split_input_text(text)
    rows = []
    for token in tokens:
        try:
            rows.append(segment_token(token))
        except Exception as exc:
            rows.append(
                {
                    "token": token,
                    "segments": [],
                    "segmented": token,
                    "score": None,
                    "error": str(exc),
                }
            )
    return {
        "model_path": str(MODEL_PATH),
        "manifest": load_manifest(),
        "token_count": len(tokens),
        "tokens": tokens,
        "rows": rows,
    }


HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Ancient Greek Morfessor Probe</title>
<style>
* { box-sizing: border-box; }
body {
  font-family: Georgia, "Times New Roman", serif;
  max-width: 1120px;
  margin: 28px auto;
  padding: 0 20px 40px;
  background:
    radial-gradient(circle at top left, rgba(177, 143, 83, 0.28), transparent 35%),
    radial-gradient(circle at top right, rgba(74, 107, 94, 0.20), transparent 28%),
    linear-gradient(180deg, #f5efe3 0%, #eadcc1 100%);
  color: #231c15;
}
h1 {
  margin: 0 0 8px;
  font-size: 34px;
  letter-spacing: 0.01em;
}
p.lead {
  margin: 0 0 18px;
  max-width: 900px;
  color: #5f4f40;
  line-height: 1.55;
}
.panel {
  background: rgba(255, 251, 244, 0.92);
  border: 1px solid #d9cab3;
  border-radius: 16px;
  padding: 18px;
  margin-top: 14px;
  box-shadow: 0 14px 34px rgba(60, 45, 26, 0.10);
}
label {
  display: block;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
  color: #594a3d;
  text-transform: uppercase;
}
textarea {
  width: 100%;
  border: 1px solid #cdbb9d;
  border-radius: 11px;
  padding: 11px 12px;
  font-size: 18px;
  background: rgba(255,255,255,0.92);
  color: #231c15;
  resize: vertical;
  min-height: 180px;
  line-height: 1.6;
  font-family: "Palatino Linotype", "Iowan Old Style", Georgia, serif;
}
.hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6c5a49;
  line-height: 1.45;
}
.actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
}
#run-btn {
  padding: 12px 24px;
  font-size: 15px;
  font-weight: 700;
  background: #7b4b2a;
  color: white;
  border: none;
  border-radius: 999px;
  cursor: pointer;
}
#run-btn:hover { background: #663d22; }
#run-btn:disabled { background: #b39a86; cursor: default; }
#status {
  min-height: 20px;
  font-size: 13px;
  color: #5f4f40;
}
.meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.chip {
  font-size: 12px;
  background: #f3e4c6;
  color: #6b4722;
  border: 1px solid #dbbf93;
  border-radius: 999px;
  padding: 5px 10px;
}
.section-title {
  margin: 0 0 10px;
  font-size: 16px;
}
.result-block {
  margin-top: 14px;
}
table {
  width: 100%;
  border-collapse: collapse;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid #dfd1ba;
  background: #fffdf8;
}
th, td {
  padding: 10px 12px;
  border-bottom: 1px solid #eadfce;
  vertical-align: top;
  text-align: left;
}
th {
  background: #f7ecd9;
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
tr:last-child td { border-bottom: none; }
pre {
  margin: 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #dfd1ba;
  background: #fffdf8;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  line-height: 1.55;
}
.error-text {
  color: #922;
  font-size: 12px;
}
</style>
</head>
<body>
<h1>Ancient Greek Morfessor Probe</h1>
<p class="lead">This test app uses a Morfessor model trained locally from the Ancient Greek SQLite dictionary in this repo. It is a rough unsupervised splitter, so use it to inspect tendencies, not as a gold morphology analyzer.</p>

<div class="panel">
  <label for="text-input">Ancient Greek Text</label>
  <textarea id="text-input">σκύλος κυνός δώδεκα ἀνθρωπολογία λόγος</textarea>
  <div class="hint">Whitespace tokenization only. Punctuation is lightly stripped before segmentation.</div>

  <div class="actions">
    <button id="run-btn" onclick="run()">Run Segmentation</button>
    <div id="status"></div>
  </div>
</div>

<div class="panel" id="result-panel" style="display:none">
  <div class="meta">
    <span class="chip" id="model-chip">Model: pending</span>
    <span class="chip" id="token-chip">Tokens: pending</span>
    <span class="chip" id="stats-chip">Training: pending</span>
  </div>

  <div class="result-block">
    <h2 class="section-title">Per-Token Segmentation</h2>
    <div id="segments-table-wrap"></div>
  </div>

  <div class="result-block">
    <h2 class="section-title">Manifest / Training Metadata</h2>
    <pre id="manifest-output"></pre>
  </div>

  <div class="result-block">
    <h2 class="section-title">Raw JSON</h2>
    <pre id="raw-json-output"></pre>
  </div>
</div>

<script>
function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderSegmentsTable(rows) {
  if (!rows.length) {
    return '<div class="hint">No tokens returned.</div>';
  }
  const body = rows.map((row) => {
    const error = row.error ? '<div class="error-text">' + escapeHtml(row.error) + '</div>' : '';
    const score = row.score === null || row.score === undefined ? '' : escapeHtml(String(row.score));
    return (
      '<tr>' +
        '<td>' + escapeHtml(row.token) + '</td>' +
        '<td>' + escapeHtml(row.segmented || row.token) + error + '</td>' +
        '<td>' + escapeHtml((row.segments || []).join(' | ')) + '</td>' +
        '<td>' + score + '</td>' +
      '</tr>'
    );
  }).join('');

  return (
    '<table>' +
      '<thead><tr><th>Token</th><th>Segmented</th><th>Segments</th><th>Score</th></tr></thead>' +
      '<tbody>' + body + '</tbody>' +
    '</table>'
  );
}

async function run() {
  const text = document.getElementById('text-input').value.trim();
  if (!text) {
    document.getElementById('status').textContent = 'Enter some text first.';
    return;
  }

  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  document.getElementById('status').textContent = 'Loading local model and segmenting...';
  document.getElementById('result-panel').style.display = 'none';

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text })
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || ('HTTP ' + response.status));
    }

    const stats = (data.manifest && data.manifest.stats) || {};
    document.getElementById('model-chip').textContent = 'Model: ' + data.model_path;
    document.getElementById('token-chip').textContent = 'Tokens: ' + data.token_count;
    document.getElementById('stats-chip').textContent =
      'Wordlist types: ' + (stats.unique_tokens || 'n/a');

    document.getElementById('segments-table-wrap').innerHTML =
      renderSegmentsTable(data.rows || []);
    document.getElementById('manifest-output').textContent =
      JSON.stringify(data.manifest || {}, null, 2);
    document.getElementById('raw-json-output').textContent =
      JSON.stringify(data, null, 2);

    document.getElementById('result-panel').style.display = 'block';
    document.getElementById('status').textContent = '';
  } catch (err) {
    document.getElementById('status').textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/analyze", methods=["POST"])
def analyze_endpoint():
    try:
        payload = request.get_json(silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Missing `text`."}), 400
        return jsonify(analyze_text(text))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    print(f"Morfessor model path: {MODEL_PATH}")
    app.run(debug=False, port=5050, threaded=True)
