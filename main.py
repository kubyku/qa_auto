from __future__ import annotations

import csv
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = ROOT / "history"
HISTORY_FILE = HISTORY_DIR / "test_history.json"


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cases_from_csv(csv_path: Path) -> List[TestCase]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    cases: List[TestCase] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"id", "engine", "name", "url", "assert_title_contains"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"CSV headers must include {sorted(required)}. "
                f"Got: {reader.fieldnames}"
            )

        for row in reader:
            cases.append(
                TestCase(
                    id=row["id"].strip(),
                    engine=row["engine"].strip(),
                    name=row["name"].strip(),
                    url=row["url"].strip(),
                    assert_title_contains=row["assert_title_contains"].strip(),
                )
            )
    return cases


def ensure_history_file() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def append_history(results: List[TestResult]) -> None:
    ensure_history_file()
    try:
        existing = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except Exception:
        existing = []

    existing.extend([asdict(r) for r in results])
    HISTORY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
                    f"Title assertion failed. "
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


def main() -> None:
    from loaders.sheets_loader import load_cases_from_sheets

    SHEET_ID = "1eyWcXsz8pKGDV_LSjqJA720_rIfe1a_TobsRAqolSA4"  # 반드시 입력
    RANGE = "testcase!A1:E100"            # 시트 이름이 다르면 Sheet1을 바꾸세요

    cases = load_cases_from_sheets(SHEET_ID, RANGE)

    print(f"[INPUT] sheets: {SHEET_ID} / {RANGE}")
    print(f"[INPUT] loaded cases: {len(cases)}")
    print("[INPUT] case ids:", [c.id + ":" + c.engine for c in cases])


    results = run_all(cases)
    append_history(results)

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
