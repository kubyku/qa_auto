from __future__ import annotations

from typing import List
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from main import TestCase  # main.py의 TestCase dataclass 재사용


def load_cases_from_sheets(
    spreadsheet_id: str,
    range_name: str = "Sheet1!A1:E100",
) -> List[TestCase]:
    creds = Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )

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

    # 빈 id 같은 잘못된 행 제거(초보 방어)
    cases = [c for c in cases if c.id]
    return cases
