"""미국: 재무부 수익률 곡선과 국채 입찰.

- 수익률 곡선: home.treasury.gov 일별 XML 피드 (월 단위 조회)
- 입찰: TreasuryDirect, Fiscal Data 두 곳을 받아 결과가 더 최근까지 들어 있는 쪽을 쓴다
"""
from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import urlencode

import common
from common import auction_row, iso_day, to_float

CODE = "us"
NAME = "미국"

CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml"
)
TD_AUCTIONED_URL = "https://www.treasurydirect.gov/TA_WS/securities/auctioned"
TD_UPCOMING_URL = "https://www.treasurydirect.gov/TA_WS/securities/upcoming"
FISCAL_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
    "v1/accounting/od/auctions_query"
)

# (화면 표기, XML 항목 이름)
TENORS = [
    ("1M", "BC_1MONTH"), ("1.5M", "BC_1_5MONTH"), ("2M", "BC_2MONTH"),
    ("3M", "BC_3MONTH"), ("4M", "BC_4MONTH"), ("6M", "BC_6MONTH"),
    ("1Y", "BC_1YEAR"), ("2Y", "BC_2YEAR"), ("3Y", "BC_3YEAR"),
    ("5Y", "BC_5YEAR"), ("7Y", "BC_7YEAR"), ("10Y", "BC_10YEAR"),
    ("20Y", "BC_20YEAR"), ("30Y", "BC_30YEAR"),
]
CURVE_MONTHS = 13

# TreasuryDirect 항목 이름은 2026-11-16 실제 응답으로 확인했다.
TD_KEYS = {
    "type": "securityType", "term": "securityTerm",
    "auction": "competitiveAuctionCloseDate", "issue": "issueDate", "maturity": "maturityDate",
    "offering": "offeringAmount", "high_yield": "highYield",
    "high_discount": "highRate", "high_margin": "highDiscountMargin",
    "coupon": "interestRate", "btc": "bidToCoverRatio", "reopening": "reopening",
    "tips": "inflationProtected", "frn": "floatingRate", "cmb": "cashManagementBill",
}
FISCAL_KEYS = {
    "type": "security_type", "term": "security_term",
    "auction": "auction_date", "issue": "issue_date", "maturity": "maturity_date",
    "offering": "offering_amt", "high_yield": "high_yield",
    "high_discount": "high_discnt_rate", "high_margin": "high_discnt_margin",
    "coupon": "int_rate", "btc": "bid_to_cover_ratio", "reopening": "reopening",
    "tips": "inflation_index_security", "frn": "floating_rate",
    "cmb": "cash_management_bill_cmb",
}


# ---------- 수익률 곡선 ----------

def months_back(today: date, count: int) -> list[str]:
    """today가 속한 달부터 거슬러 count개월. 오래된 달이 앞."""
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        out.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out[::-1]


def parse_curve(xml_bytes: bytes) -> list[list]:
    """XML 피드 → [[날짜, 만기별 금리...], ...]"""
    rows = []
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if common.local_name(node.tag) != "properties":
            continue
        props = {common.local_name(child.tag): (child.text or "").strip() for child in node}
        day = props.get("NEW_DATE", "")[:10]
        if len(day) != 10:
            continue
        values = [to_float(props.get(key)) for _, key in TENORS]
        if all(v is None for v in values):
            continue
        rows.append([day] + values)
    return rows


def collect_curve(today: date, previous: dict | None, errors: list[str]) -> list[list]:
    old = (previous or {}).get("curve", {}).get("rows") or []
    since = common.days_ago(today, common.KEEP_DAYS)
    # 이미 받아 둔 이력이 있으면 최근 두 달만 다시 받는다.
    months = months_back(today, 2 if len(old) > 200 else CURVE_MONTHS)
    new: list[list] = []
    for ym in months:
        url = f"{CURVE_URL}?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}"
        try:
            new += parse_curve(common.fetch(url))
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"수익률 곡선 {ym}: {exc}")
        time.sleep(0.3)
    return common.merge_rows(old, new, since) if new else []


# ---------- 입찰 ----------

def _yes(value) -> bool:
    return str(value or "").strip().lower() in ("yes", "y", "true")


def normalize(rec: dict, keys: dict) -> dict | None:
    """출처마다 다른 항목 이름을 한 가지 모양으로 맞춘다."""
    kind = str(rec.get(keys["type"]) or "").strip()
    term = str(rec.get(keys["term"]) or "").strip()
    auction = iso_day(rec.get(keys["auction"]))
    if not (kind and term and auction):
        return None
    if _yes(rec.get(keys["tips"])):
        kind = "TIPS"
    elif _yes(rec.get(keys["frn"])):
        kind = "FRN"
    elif _yes(rec.get(keys["cmb"])):
        kind = "CMB"

    high_yield = to_float(rec.get(keys["high_yield"]))
    high_discount = to_float(rec.get(keys["high_discount"]))
    high_margin = to_float(rec.get(keys["high_margin"]))
    if kind == "FRN" and high_margin is not None:
        rate, rate_kind = high_margin, "margin"
    elif high_yield is not None:
        rate, rate_kind = high_yield, "yield"
    elif high_discount is not None:
        rate, rate_kind = high_discount, "discount"
    else:
        rate, rate_kind = None, None

    return auction_row(
        auction_date=auction,
        issue_date=iso_day(rec.get(keys["issue"])),
        maturity=iso_day(rec.get(keys["maturity"])),
        type=kind,
        bill=kind in ("Bill", "CMB"),
        term=term,
        offering_amt=to_float(rec.get(keys["offering"])),
        high_rate=rate,
        rate_kind=rate_kind,
        coupon=to_float(rec.get(keys["coupon"])),
        bid_to_cover=to_float(rec.get(keys["btc"])),
        tag="리오픈" if _yes(rec.get(keys["reopening"])) else "신규",
    )


def fetch_treasurydirect(errors: list[str]) -> list[dict]:
    data = json.loads(common.fetch(f"{TD_AUCTIONED_URL}?format=json&days={common.AUCTION_DAYS}"))
    if not isinstance(data, list):
        raise ValueError("예상과 다른 응답 형식")
    rows = [r for r in (normalize(x, TD_KEYS) for x in data) if r]
    if data and not rows:
        first = data[0] if isinstance(data[0], dict) else {}
        raise ValueError(f"{len(data)}건을 받았지만 읽지 못함. 항목 이름: {', '.join(sorted(first)[:40])}")
    if not data:
        raise ValueError("빈 목록을 받음")
    try:
        upcoming = json.loads(common.fetch(f"{TD_UPCOMING_URL}?format=json"))
        rows += [r for r in (normalize(x, TD_KEYS) for x in upcoming) if r]
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"TreasuryDirect 입찰 예정: {exc}")
    return rows


def fetch_fiscaldata(today: date) -> list[dict]:
    since = common.days_ago(today, common.AUCTION_DAYS)
    query = urlencode(
        {"filter": f"auction_date:gte:{since}", "sort": "-auction_date", "page[size]": "500"},
        safe=":,[]",
    )
    data = json.loads(common.fetch(f"{FISCAL_URL}?{query}"))
    return [r for r in (normalize(x, FISCAL_KEYS) for x in data.get("data", [])) if r]


def collect_auctions(today: date, errors: list[str]) -> dict | None:
    """TreasuryDirect를 먼저 쓰고, 실패하면 Fiscal Data(약 한 달 늦음)로 넘어간다."""
    name, rows = "TreasuryDirect", []
    try:
        rows = fetch_treasurydirect(errors)
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"TreasuryDirect 입찰: {exc}")
    if not rows:
        name = "Fiscal Data"
        try:
            rows = fetch_fiscaldata(today)
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"Fiscal Data 입찰: {exc}")
    if not rows:
        return None
    results, pending = common.split_auctions(rows, today)
    return {
        "source": name, "rate_label": "최고 낙찰금리",
        "amount_label": "억 달러", "amount_div": 1e8, "amount_digits": 0,
        "latest_result": common.latest_result(rows),
        "results": results, "pending": pending,
    }


def collect(today: date, previous: dict | None) -> dict:
    errors: list[str] = []
    rows = collect_curve(today, previous, errors)
    return {
        "curve": {
            "title": "미 재무부 Par Yield Curve",
            "tenors": [label for label, _ in TENORS],
            "rows": rows,
        } if rows else None,
        "auctions": collect_auctions(today, errors),
        "sources": "미 재무부, TreasuryDirect",
        "errors": errors,
    }
