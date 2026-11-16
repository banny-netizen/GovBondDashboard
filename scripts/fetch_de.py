"""독일: 분데스방크의 연방채 지표물 금리와 재무대리인(Finanzagentur)의 입찰 결과."""
from __future__ import annotations

import time
from datetime import date

import common
from common import auction_row, excel_date, to_float

CODE = "de"
NAME = "독일"

YIELD_URL = "https://api.statistiken.bundesbank.de/rest/download/BBSSY/{key}?format=csv&lang=en"
SERIES = [
    ("2Y", "D.REN.EUR.A610.000000WT0202.A"),
    ("5Y", "D.REN.EUR.A620.000000WT0505.A"),
    ("10Y", "D.REN.EUR.A630.000000WT1010.A"),
    ("30Y", "D.REN.EUR.A640.000000WT3030.A"),
]
AUCTIONS_URL = (
    "https://www.deutsche-finanzagentur.de/fileadmin/user_upload/"
    "Institutionelle-investoren/auktionen/emissionsergebnisse_aktuell_en.xlsx"
)

# 엑셀 열 위치 (2026-11-16 실제 파일로 확인)
COL_DATE, COL_BOND, COL_COUPON, COL_MATURITY, COL_SEGMENT = 1, 3, 4, 5, 6
COL_VOLUME, COL_NEW_OR_REOPEN, COL_AVG_YIELD, COL_COVER = 7, 8, 16, 18


def parse_bundesbank_csv(text: str, since: str) -> dict[str, float]:
    """분데스방크 CSV → {날짜: 금리}. 머리말 줄과 값 없는 날('.')은 건너뛴다."""
    out = {}
    for line in text.splitlines():
        parts = line.split(",")
        day = common.iso_day(parts[0].strip().strip('"'))
        if not day or day < since or len(parts) < 2:
            continue
        value = to_float(parts[1])
        if value is not None:
            out[day] = value
    return out


def _term(segment: str) -> str | None:
    """'10 Y' → '10-Year', '12 M' → '12-Month'."""
    parts = segment.split()
    if len(parts) == 2 and parts[0].replace(".", "").isdigit():
        unit = {"Y": "Year", "M": "Month"}.get(parts[1].upper())
        if unit:
            return f"{parts[0]}-{unit}"
    return None


def parse_auctions(sheets: list[list[list[str]]], since: str) -> list[dict]:
    rows = []
    for sheet in sheets:
        for cells in sheet:
            if len(cells) <= COL_COVER or not cells[0].strip().isdigit():
                continue  # 머리말, 합계, 각주
            auction = excel_date(cells[COL_DATE])
            if not auction or auction < since:
                continue
            bond = cells[COL_BOND].strip()
            volume = to_float(cells[COL_VOLUME])
            coupon = to_float(cells[COL_COUPON])
            flag = cells[COL_NEW_OR_REOPEN].strip().upper()
            rows.append(auction_row(
                auction_date=auction,
                maturity=excel_date(cells[COL_MATURITY]),
                type=bond,
                bill=bond.lower() == "bubill",
                term=_term(cells[COL_SEGMENT]),
                offering_amt=volume * 1e6 if volume is not None else None,
                high_rate=to_float(cells[COL_AVG_YIELD]),
                rate_kind="yield" if to_float(cells[COL_AVG_YIELD]) is not None else None,
                coupon=round(coupon * 100, 4) if coupon is not None else None,
                bid_to_cover=to_float(cells[COL_COVER]),
                tag={"N": "신규", "R": "리오픈"}.get(flag, ""),
            ))
    return rows


def collect(today: date, previous: dict | None) -> dict:
    errors: list[str] = []
    since = common.days_ago(today, common.KEEP_DAYS)

    by_tenor: dict[str, dict[str, float]] = {}
    for label, key in SERIES:
        try:
            text = common.fetch(YIELD_URL.format(key=key)).decode("utf-8-sig", errors="replace")
            by_tenor[label] = parse_bundesbank_csv(text, since)
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"금리 {label}: {exc}")
        time.sleep(0.3)
    rows = common.curve_rows([label for label, _ in SERIES], by_tenor, since)

    auctions = None
    try:
        parsed = parse_auctions(common.xlsx_sheets(common.fetch(AUCTIONS_URL)),
                                common.days_ago(today, common.AUCTION_DAYS))
        results, pending = common.split_auctions(parsed, today)
        auctions = {
            "source": "독일 재무대리인", "rate_label": "평균 낙찰금리",
            "amount_label": "억 유로", "amount_div": 1e8, "amount_digits": 0,
            "latest_result": common.latest_result(parsed),
            "results": results, "pending": pending,
            "note": "올해 치른 입찰 결과만 있는 파일이라 예정 입찰은 없습니다. 발행액은 정부 보유분을 포함합니다.",
        }
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"입찰: {exc}")

    return {
        "curve": {
            "title": "독일 연방채 지표물 금리",
            "tenors": [label for label, _ in SERIES],
            "rows": rows,
        } if rows else None,
        "auctions": auctions,
        "sources": "분데스방크, 독일 재무대리인(Finanzagentur)",
        "errors": errors,
    }
