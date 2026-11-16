"""유로존: 유럽중앙은행(ECB)이 추정한 AAA 국채 수익률 곡선. 입찰 자료는 없다."""
from __future__ import annotations

import csv
import io
from datetime import date

import common
from common import iso_day, to_float

CODE = "ez"
NAME = "유로존"

TENORS = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
URL = (
    "https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM."
    + "+".join("SR_" + tenor for tenor in TENORS)
    + "?format=csvdata&lastNObservations={count}"
)
FULL_COUNT = 290     # 처음 받을 때: 만기별 최근 290영업일
RECENT_COUNT = 15    # 이력이 있을 때: 최근 15영업일만 받아 합친다


def parse_csv(text: str, since: str) -> list[list]:
    by_tenor: dict[str, dict[str, float]] = {tenor: {} for tenor in TENORS}
    for rec in csv.DictReader(io.StringIO(text)):
        tenor = (rec.get("DATA_TYPE_FM") or "").removeprefix("SR_")
        day = iso_day(rec.get("TIME_PERIOD"))
        value = to_float(rec.get("OBS_VALUE"))
        if tenor in by_tenor and day and value is not None:
            by_tenor[tenor][day] = round(value, 3)
    return common.curve_rows(TENORS, by_tenor, since)


def collect(today: date, previous: dict | None) -> dict:
    since = common.days_ago(today, common.KEEP_DAYS)
    old = (previous or {}).get("curve", {}).get("rows") or []
    fresh = len(old) > 200 and old[-1][0] >= common.days_ago(today, 14)
    url = URL.format(count=RECENT_COUNT if fresh else FULL_COUNT)
    text = common.fetch(url).decode("utf-8-sig", errors="replace")
    rows = common.merge_rows(old if fresh else [], parse_csv(text, since), since)
    return {
        "curve": {
            "title": "유로존 AAA 국채 수익률 곡선 (spot)",
            "note": "ECB가 AAA 등급 국채로 추정한 제로쿠폰 금리입니다. 개별 국채의 호가가 아닙니다.",
            "tenors": TENORS,
            "rows": rows,
        } if rows else None,
        "auctions": None,
        "auctions_note": "유로존은 ECB 추정 곡선만 싣습니다. 국가별 입찰은 각 나라 탭을 보십시오.",
        "sources": "유럽중앙은행(ECB)",
        "errors": [],
    }
