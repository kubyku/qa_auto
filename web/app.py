from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for

# ---------------------------------
# Env (.env) load
# ---------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---------------------------------
# Flask app
# ---------------------------------
app = Flask(__name__)
app.secret_key = "qa-auto-local"

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
    sheet_id = os.getenv("SHEET_ID", "").strip()
    sheet_range = os.getenv("SHEET_RANGE", "testcase!A1:E100").strip()
    if not sheet_id:
        return []

    from loaders.sheets_loader import load_cases_from_sheets

    cases = load_cases_from_sheets(sheet_id, sheet_range)
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

    # 신규(new)는 일단 전체로(추후 규칙 정의 가능)
    new_cnt = total
    return {"total": total, "pass": p, "fail": f, "new": new_cnt, "rate": rate}


# ---------------------------
# GitHub Artifact Sync
# ---------------------------
def fetch_latest_test_history_from_github():
    """
    GitHub Actions artifact(name=test-history) 중 최신 것을 내려받아
    history/test_history.json 을 파싱해서 반환.
    실패하면 (None, "에러메시지") 반환.
    """
    owner = os.getenv("GITHUB_OWNER", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not owner or not repo or not token:
        return None, "GITHUB_OWNER / GITHUB_REPO / GITHUB_TOKEN 환경변수가 필요합니다."

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts?per_page=50"
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        return None, f"Artifacts 목록 조회 실패: {r.status_code} {r.text[:500]}"

    artifacts = r.json().get("artifacts", [])
    candidates = [
        a for a in artifacts
        if a.get("name") == "test-history" and not a.get("expired", False)
    ]
    if not candidates:
        return None, "test-history artifact를 찾지 못했습니다. (Actions 실행 후 artifact 업로드 확인 필요)"

    candidates.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    latest = candidates[0]
    archive_url = latest.get("archive_download_url")
    if not archive_url:
        return None, "archive_download_url이 없습니다."

    z = requests.get(archive_url, headers=headers, timeout=60)
    if z.status_code != 200:
        return None, f"Artifact zip 다운로드 실패: {z.status_code} {z.text[:500]}"

    with zipfile.ZipFile(io.BytesIO(z.content)) as zipf:
        names = zipf.namelist()

        target = None
        for cand in ["history/test_history.json", "test_history.json"]:
            if cand in names:
                target = cand
                break

        if not target:
            for n in names:
                if n.endswith("test_history.json"):
                    target = n
                    break

        if not target:
            return None, f"zip 안에서 test_history.json을 찾지 못했습니다. zip entries: {names[:20]}"

        raw = zipf.read(target).decode("utf-8")
        try:
            data = json.loads(raw)
        except Exception as e:
            return None, f"history JSON 파싱 실패: {e}"

        if not isinstance(data, list):
            return None, "history JSON이 list 형식이 아닙니다."

        return data, None


def save_github_history_to_local(history_data):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)


@app.route("/sync_github", methods=["POST"])
def sync_github():
    data, err = fetch_latest_test_history_from_github()
    if err:
        flash(err, "error")
        return redirect(url_for("dashboard"))

    save_github_history_to_local(data)
    flash("GitHub Actions 결과를 로컬 history로 동기화했습니다.", "success")
    return redirect(url_for("dashboard"))


# ---------------------------
# Routes
# ---------------------------
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
        runs=runs[::-1],
        latest_run=latest,
        actions_url=actions_url,
    )

@app.route("/__routes")
def __routes():
    # 현재 서버에 등록된 라우트들을 텍스트로 보여줌
    lines = []
    for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
        methods = ",".join(sorted(m for m in r.methods if m not in {"HEAD", "OPTIONS"}))
        lines.append(f"{methods:10s} {r.rule:30s} -> {r.endpoint}")
    return "<pre>" + "\n".join(lines) + "</pre>"

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


# (선택) 환경변수 확인용 디버그 라우트
@app.route("/debug-env")
def debug_env():
    token = os.getenv("GITHUB_TOKEN", "")
    return {
        "BASE_DIR": BASE_DIR,
        "cwd": os.getcwd(),
        "GITHUB_OWNER": os.getenv("GITHUB_OWNER"),
        "GITHUB_REPO": os.getenv("GITHUB_REPO"),
        "GITHUB_TOKEN_prefix": (token[:10] if token else None),
        "SHEET_ID_set": bool(os.getenv("SHEET_ID")),
        "SHEET_RANGE": os.getenv("SHEET_RANGE"),
    }


if __name__ == "__main__":
    app.run(debug=True)