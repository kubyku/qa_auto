from __future__ import annotations

from typing import List
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from main import TestCase  # 이미 만든 dataclass 재사용


def load_cases_from_sheets(
    spreadsheet_id: str,
    range_name: str = "Sheet1!A1:E100"
) -> List[TestCase]:
    creds = Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )

    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()

    values = result.get("values", [])
    if not values:
        return []

    headers = values[0]
    cases: List[TestCase] = []

    for row in values[1:]:
        data = dict(zip(headers, row))
        cases.append(
            TestCase(
                id=data["id"],
                engine=data["engine"],
                name=data["name"],
                url=data.get("url", ""),
                assert_title_contains=data.get("assert_title_contains", ""),
            )
        )

    return cases
