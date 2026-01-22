from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "history"
HISTORY_FILE = HISTORY_DIR / "test_history.json"


# -----------------------------
# Models
# -----------------------------
@dataclass(frozen=True)
class TestCase:
    id: str
    engine: str
    name: str
    url: str
    assert_title_contains: str


@dataclass
class TestResult:
    id: str
    engine: str
    name: str
    url: str
    status: str  # "pass" | "fail" | "error"
    started_at: str
    finished_at: str
    duration_ms: int
    title: Optional[str] = None
    error: Optional[str] = None


# -----------------------------
# Utils
# -----------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_history_file() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def append_run_history(results: List[TestResult]) -> None:
    """
    History format (runs):
    [
      {
        "executed_at": "...",
        "summary": {"pass": 1, "fail": 0, "error": 0},
        "results": [ {TestResult...}, ... ]
      },
      ...
    ]
    """
    ensure_history_file()

    # load existing
    try:
        existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        existing = []

    # if old format (list of TestResult dicts), reset to empty
    if isinstance(existing, list) and existing:
        first = existing[0]
        if (
            isinstance(first, dict)
            and ("id" in first and "status" in first)
            and ("results" not in first)
        ):
            existing = []

    if not isinstance(existing, list):
        existing = []

    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    errored = sum(1 for r in results if r.status == "error")

    run_record = {
        "executed_at": utc_now_iso(),
        "summary": {"pass": passed, "fail": failed, "error": errored},
        "results": [asdict(r) for r in results],
    }

    existing.append(run_record)

    HISTORY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# -----------------------------
# Engines
# -----------------------------
def run_case_playwright(case: TestCase) -> TestResult:
    started = utc_now_iso()
    t0 = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(case.url, wait_until="domcontentloaded", timeout=30_000)

            title = page.title()
            if case.assert_title_contains not in title:
                status = "fail"
                err = (
                    "Title assertion failed. "
                    f"Expected to contain: '{case.assert_title_contains}', "
                    f"Actual: '{title}'"
                )
            else:
                status = "pass"
                err = None

            browser.close()

        finished = utc_now_iso()
        duration_ms = int((time.time() - t0) * 1000)
        return TestResult(
            id=case.id,
            engine=case.engine,
            name=case.name,
            url=case.url,
            status=status,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            title=title,
            error=err,
        )
    except Exception as e:
        finished = utc_now_iso()
        duration_ms = int((time.time() - t0) * 1000)
        return TestResult(
            id=case.id,
            engine=case.engine,
            name=case.name,
            url=case.url,
            status="error",
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            title=None,
            error=str(e),
        )


# -----------------------------
# Runner
# -----------------------------
def run_all(cases: List[TestCase]) -> List[TestResult]:
    results: List[TestResult] = []
    for case in cases:
        if case.engine != "playwright":
            results.append(
                TestResult(
                    id=case.id,
                    engine=case.engine,
                    name=case.name,
                    url=case.url,
                    status="error",
                    started_at=utc_now_iso(),
                    finished_at=utc_now_iso(),
                    duration_ms=0,
                    error=f"Unsupported engine: {case.engine}",
                )
            )
            continue

        print(f"Running {case.id} - {case.name}")
        r = run_case_playwright(case)
        results.append(r)
        print(f" -> {r.status.upper()}" + (f" ({r.error})" if r.error else ""))

    return results


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    # sheets loader
    from loaders.sheets_loader import load_cases_from_sheets

    # Prefer env (works for local + CI + dashboard)
    sheet_id = os.getenv("SHEET_ID", "").strip()
    sheet_range = os.getenv("SHEET_RANGE", "testcase!A1:E100").strip()

    # Fallback: allow hardcode if env not set (초보 방어)
    if not sheet_id:
        sheet_id = "1eyWcXsz8pKGDV_LSjqJA720_rIfe1a_TobsRAqolSA4"

    cases = load_cases_from_sheets(sheet_id, sheet_range)

    print(f"[INPUT] sheets: {sheet_id} / {sheet_range}")
    print(f"[INPUT] loaded cases: {len(cases)}")
    print("[INPUT] case ids:", [c.id + ":" + c.engine for c in cases])

    results = run_all(cases)
    append_run_history(results)

    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    errored = sum(1 for r in results if r.status == "error")

    print("\nSummary")
    print(f"  pass: {passed}")
    print(f"  fail: {failed}")
    print(f"  error: {errored}")
    print(f"\nHistory saved to: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
