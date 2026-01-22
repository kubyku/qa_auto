from flask import Flask, render_template, redirect, url_for, flash
import json, os, subprocess, sys
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = "qa-auto-local"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HISTORY_PATH = os.path.join(BASE_DIR, "history", "test_history.json")
MAIN_PATH = os.path.join(BASE_DIR, "main.py")

def _read_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def get_runs():
    data = _read_json(HISTORY_PATH, [])
    return data if isinstance(data, list) else []

def get_latest_run():
    runs = get_runs()
    return runs[-1] if runs else None

def get_cases_from_sheets():
    # main.py와 동일한 env 사용
    sheet_id = os.getenv("SHEET_ID", "").strip()
    sheet_range = os.getenv("SHEET_RANGE", "testcase!A1:E100").strip()
    if not sheet_id:
        return []

    from loaders.sheets_loader import load_cases_from_sheets
    cases = load_cases_from_sheets(sheet_id, sheet_range)
    # dataclass -> dict
    return [c.__dict__ for c in cases]

def calc_cards(latest_run, cases):
    total = len(cases)
    p = f = e = 0
    if latest_run and isinstance(latest_run, dict):
        s = latest_run.get("summary", {}) or {}
        p = int(s.get("pass", 0) or 0)
        f = int(s.get("fail", 0) or 0)
        e = int(s.get("error", 0) or 0)
    denom = (p + f + e)
    rate = int(round((p / denom) * 100)) if denom else 0
    # 신규(new)는 일단 “전체”로 두고, 다음 단계에서 규칙 정의(최근 7일 생성 등)
    new_cnt = total
    return {"total": total, "pass": p, "fail": f, "new": new_cnt, "rate": rate}

@app.route("/")
def dashboard():
    cases = get_cases_from_sheets()
    runs = get_runs()
    latest = runs[-1] if runs else None
    cards = calc_cards(latest, cases)

    actions_url = os.getenv("GITHUB_ACTIONS_URL", "").strip()
    return render_template(
        "dashboard2.html",
        cards=cards,
        cases=cases,
        runs=runs[::-1],   # 최신 먼저
        latest_run=latest,
        actions_url=actions_url,
    )

@app.route("/run", methods=["POST"])
def run_tests():
    env = os.environ.copy()

    proc = subprocess.run(
        [sys.executable, "-u", MAIN_PATH],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()

    if proc.returncode != 0:
        flash((output[-2000:] if output else "Test run failed."), "error")
    else:
        flash("Test run completed.", "success")

    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
