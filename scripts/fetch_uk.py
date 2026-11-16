"""영국: 영란은행의 길트 명목 금리와 국채관리청(DMO)의 발행 내역."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import common
from common import auction_row, iso_day, to_float

CODE = "uk"
NAME = "영국"

YIELD_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
    "?csv.x=yes&Datefrom={start}&Dateto=now&SeriesCodes=IUDSNPY,IUDMNPY,IUDLNPY"
    "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
)
SERIES = [("5Y", "IUDSNPY"), ("10Y", "IUDMNPY"), ("20Y", "IUDLNPY")]
ISSUANCE_URL = "https://www.dmo.gov.uk/data/XmlDataReport?reportCode=D2.1E"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}
KEPT_TYPES = {"Outright": "입찰", "Syndication": "신디케이션"}


def _boe_date(text: str) -> str | None:
    """'02 Nov 2026' → '2026-11-02'."""
    parts = text.strip().split()
    if len(parts) == 3 and parts[1][:3].title() in MONTHS and parts[0].isdigit() and parts[2].isdigit():
        return f"{int(parts[2]):04d}-{MONTHS.index(parts[1][:3].title()) + 1:02d}-{int(parts[0]):02d}"
    return None


def parse_boe_csv(text: str, since: str) -> list[list]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].upper().startswith("DATE"):
        raise ValueError("예상과 다른 응답 형식")
    codes = [code.strip() for code in lines[0].split(",")[1:]]
    by_tenor: dict[str, dict[str, float]] = {label: {} for label, _ in SERIES}
    for line in lines[1:]:
        parts = line.split(",")
        day = _boe_date(parts[0])
        if not day:
            continue
        for label, code in SERIES:
            if code in codes and codes.index(code) + 1 < len(parts):
                value = to_float(parts[codes.index(code) + 1])
                if value is not None:
                    by_tenor[label][day] = round(value, 3)
    return common.curve_rows([label for label, _ in SERIES], by_tenor, since)


def parse_coupon(name: str) -> float | None:
    """'4 5/8% Treasury Gilt 2032' → 4.625, '0½% …' → 0.5."""
    head = name.split("%", 1)[0].strip()
    if not head or "%" not in name:
        return None
    total = 0.0
    for ch, value in FRACTIONS.items():
        if ch in head:
            total += value
            head = head.replace(ch, " ")
    for part in head.split():
        if "/" in part:
            top, _, bottom = part.partition("/")
            if top.isdigit() and bottom.isdigit() and int(bottom):
                total += int(top) / int(bottom)
            else:
                return None
        else:
            number = to_float(part)
            if number is None:
                return None
            total += number
    return round(total, 4)


def parse_issuance(xml_text: str, since: str) -> list[dict]:
    root = ET.fromstring(xml_text.strip())
    rows = []
    for node in root:
        rec = node.attrib
        day = iso_day(rec.get("ACTUAL_DATE"))
        tag = KEPT_TYPES.get(rec.get("ISSUANCE_TYPE", ""))
        amount = to_float(rec.get("NOMINAL_ISSUED"))
        if not day or day < since or tag is None or amount is None or amount <= 0:
            continue
        name = rec.get("INSTRUMENT_NAME", "")
        year = re.search(r"(20\d{2}|19\d{2})\b", name.split("%", 1)[-1])
        if "Index-linked" in name:
            kind = "IL Gilt"
        elif "Green" in name:
            kind = "Green Gilt"
        else:
            kind = "Gilt"
        rate = to_float(rec.get("ISSUE_YIELD"))
        rows.append(auction_row(
            auction_date=day,
            maturity=year.group(1) if year else None,
            type=kind,
            offering_amt=amount * 1e6,
            high_rate=round(rate, 3) if rate is not None else None,
            rate_kind="yield" if rate is not None else None,
            coupon=parse_coupon(name),
            tag=tag,
        ))
    return rows


def collect(today: date, previous: dict | None) -> dict:
    errors: list[str] = []
    since = common.days_ago(today, common.KEEP_DAYS)

    start = datetime.strptime(since, "%Y-%m-%d")
    start_text = f"{start.day:02d}/{MONTHS[start.month - 1]}/{start.year}"
    text = common.fetch(YIELD_URL.format(start=start_text)).decode("utf-8-sig", errors="replace")
    rows = parse_boe_csv(text, since)

    auctions = (previous or {}).get("auctions")
    try:
        body = common.fetch(ISSUANCE_URL, retries=1).decode("utf-8-sig", errors="replace")
        parsed = parse_issuance(body, common.days_ago(today, common.AUCTION_DAYS))
        results, _ = common.split_auctions(parsed, today)
        auctions = {
            "source": "영국 국채관리청(DMO)", "rate_label": "발행 금리",
            "amount_label": "억 파운드", "amount_div": 1e8, "amount_digits": 0,
            "latest_result": common.latest_result(parsed),
            "results": results, "pending": [],
            "note": "발행 내역만 제공돼 응찰률과 예정 입찰은 없습니다. 물가연동채 금리는 실질금리입니다.",
        }
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"발행 내역: {exc}" + (" (직전 수집분 유지)" if auctions else ""))

    return {
        "curve": {
            "title": "영국 길트 명목 금리 (par yield)",
            "note": "영란은행이 추정한 5·10·20년 명목 par yield입니다.",
            "tenors": [label for label, _ in SERIES],
            "rows": rows,
        } if rows else None,
        "auctions": auctions,
        "sources": "영란은행(Bank of England), 영국 국채관리청(DMO)",
        "errors": errors,
    }
