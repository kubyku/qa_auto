from __future__ import annotations

import json
import os
import re
from typing import List, Dict, Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from main import TestCase  # main.py의 TestCase dataclass 재사용


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_RANGE = "testcase!A1:E100"  # 기본값을 당신 프로젝트 기준으로 맞춰둠 (원하면 Sheet1로 바꿔도 됨)
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _normalize_sheet_id(spreadsheet_id: str) -> str:
    """
    spreadsheet_id에 ID가 아니라 URL이 들어와도 ID만 추출해줌.
    예: https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0
    """
    s = (spreadsheet_id or "").strip()
    if not s:
        return s

    # URL 패턴에서 /d/<ID>/ 추출
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", s)
    if m:
        return m.group(1)

    return s


def _loads_credentials_json(raw: str) -> Dict[str, Any]:
    """
    GOOGLE_CREDENTIALS_JSON 값이
    - 정상 JSON 문자열
    - 혹은 줄바꿈/escape가 꼬인 문자열
    이더라도 최대한 안전하게 파싱.
    """
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON 환경변수가 비어 있습니다.")

    # 가장 흔한 케이스: 그냥 json.loads로 됨
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 줄바꿈이 포함되거나, 이스케이프가 꼬인 경우를 한 번 더 시도
    # 1) JSON 전체가 따옴표로 감싸진 형태(예: '{"a":"b"}' 를 또 감싼 경우)
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        try:
            return json.loads(raw[1:-1])
        except Exception:
            pass

    # 2) \n이 실제 개행으로 들어간 경우 → 다시 escape 처리 시도
    # (완벽하진 않지만 초보자 입력 실수를 많이 구해줌)
    try:
        fixed = raw.replace("\n", "\\n")
        return json.loads(fixed)
    except Exception as e:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS_JSON 값을 JSON으로 파싱할 수 없습니다. "
            "한 줄(JSON) 형태인지 확인하세요."
        ) from e


def _build_credentials() -> Credentials:
    """
    우선순위
    1) GOOGLE_CREDENTIALS_JSON (권장: 로컬/CI 공통)
    2) GOOGLE_APPLICATION_CREDENTIALS 파일 경로 (대안)
    """
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if raw:
        info = _loads_credentials_json(raw)
        info["token_uri"] = TOKEN_URI  # 핵심: 무조건 정상 엔드포인트 고정
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"credentials 파일이 없습니다: {cred_path}\n"
            f"- (권장) GOOGLE_CREDENTIALS_JSON 환경변수를 설정하거나\n"
            f"- (대안) GOOGLE_APPLICATION_CREDENTIALS에 올바른 경로를 지정하세요."
        )

    with open(cred_path, "r", encoding="utf-8") as f:
        info = json.load(f)
    info["token_uri"] = TOKEN_URI
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def load_cases_from_sheets(
    spreadsheet_id: str,
    range_name: str = DEFAULT_RANGE,
) -> List[TestCase]:
    spreadsheet_id = _normalize_sheet_id(spreadsheet_id)
    if not spreadsheet_id:
        return []

    creds = _build_credentials()

    # cache_discovery=False: github actions 같은 환경에서 불필요한 캐시/경고 줄임
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )

    values = result.get("values", [])
    if not values:
        return []

    headers = [h.strip() for h in values[0]]
    cases: List[TestCase] = []

    for row in values[1:]:
        # row 길이가 header보다 짧아도 안전하게 zip
        data = dict(zip(headers, row))

        # 초보자 방어: 컬럼명이 대소문자/공백 차이 날 수 있음
        # 필요한 키를 정규화해서 가져오기
        def _get(key: str) -> str:
            for k, v in data.items():
                if k.strip().lower() == key.strip().lower():
                    return str(v).strip()
            return ""

        tc_id = _get("id")
        if not tc_id:
            continue

        cases.append(
            TestCase(
                id=tc_id,
                engine=_get("engine"),
                name=_get("name"),
                url=_get("url"),
                assert_title_contains=_get("assert_title_contains"),
            )
        )

    return cases
