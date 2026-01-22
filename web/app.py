from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

import json
from pathlib import Path
from flask import Flask, redirect, render_template_string, url_for

# 프로젝트 루트 경로 잡기
ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = ROOT / "history" / "test_history.json"

# main.py의 main()을 호출해서 실행시키는 방식(가장 단순)
import main as runner_main  # main.py

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>QA Auto Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; }
      button { padding: 10px 14px; cursor: pointer; }
      table { border-collapse: collapse; width: 100%; margin-top: 16px; }
      th, td { border: 1px solid #ddd; padding: 8px; font-size: 14px; }
      th { background: #f5f5f5; text-align: left; }
      .pass { color: #0a0; }
      .fail { color: #a00; }
      .error { color: #a60; }
    </style>
  </head>
  <body>
    <h1>QA Auto Dashboard</h1>

    <form action="{{ url_for('run') }}" method="post">
      <button type="submit">Run tests</button>
    </form>

    <h2>Recent history</h2>
    <table>
      <thead>
        <tr>
          <th>started_at</th>
          <th>id</th>
          <th>engine</th>
          <th>name</th>
          <th>status</th>
          <th>duration_ms</th>
          <th>error</th>
        </tr>
      </thead>
      <tbody>
        {% for r in rows %}
        <tr>
          <td>{{ r.get('started_at','') }}</td>
          <td>{{ r.get('id','') }}</td>
          <td>{{ r.get('engine','') }}</td>
          <td>{{ r.get('name','') }}</td>
          <td class="{{ r.get('status','') }}">{{ r.get('status','') }}</td>
          <td>{{ r.get('duration_ms','') }}</td>
          <td>{{ r.get('error','') }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </body>
</html>
"""

def read_history(limit: int = 50):
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return list(reversed(data))[:limit]
    except Exception:
        return []

@app.get("/")
def index():
    rows = read_history(limit=50)
    return render_template_string(HTML, rows=rows)

@app.post("/run")
def run():
    runner_main.main()  # main.py 실행
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
