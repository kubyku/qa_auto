from __future__ import annotations

import json
import os
from typing import List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from main import TestCase  # main.py의 TestCase dataclass 재사용


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_RANGE = "Sheet1!A1:E100"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _build_credentials() -> Credentials:
    # 1) CI에서 가장 안전: Secrets를 그대로 env로 주입한 JSON 사용
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if raw:
        info = json.loads(raw)
        info["token_uri"] = TOKEN_URI  # 핵심: 무조건 정상 엔드포인트로 고정
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    # 2) 로컬/대안: 파일에서 읽되 token_uri 강제 고정
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    with open(cred_path, "r", encoding="utf-8") as f:
        info = json.load(f)
    info["token_uri"] = TOKEN_URI
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def load_cases_from_sheets(
    spreadsheet_id: str,
    range_name: str = DEFAULT_RANGE,
) -> List[TestCase]:
    creds = _build_credentials()
    service = build("sheets", "v4", credentials=creds)

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )

    values = result.get("values", [])
    if not values:
        return []

    headers = values[0]
    cases: List[TestCase] = []

    for row in values[1:]:
        data = dict(zip(headers, row))
        cases.append(
            TestCase(
                id=str(data.get("id", "")).strip(),
                engine=str(data.get("engine", "")).strip(),
                name=str(data.get("name", "")).strip(),
                url=str(data.get("url", "")).strip(),
                assert_title_contains=str(data.get("assert_title_contains", "")).strip(),
            )
        )

    return [c for c in cases if c.id]
