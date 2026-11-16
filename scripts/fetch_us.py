"""미국채 일별 수집: 수익률 곡선과 입찰 결과·예정.

출처는 모두 미 재무부 공개 데이터다.
- 수익률 곡선: home.treasury.gov 일별 XML 피드 (월 단위 조회)
- 입찰: TreasuryDirect, Fiscal Data 두 곳을 받아 더 최근 것을 쓴다
"""
from __future__ import annotations

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import common
from common import ROOT, to_float, write_json

OUT = ROOT / "docs" / "data" / "us.json"

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

CURVE_MONTHS = 13      # 곡선 이력: 최근 13개월
AUCTION_DAYS = 90      # 입찰 이력: 최근 90일
PENDING_DAYS = 45      # 결과가 비어 있는 입찰은 이 기간 안의 것만 보여 준다

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


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_curve(xml_bytes: bytes) -> list[list]:
    """XML 피드 → [[날짜, 만기별 금리...], ...]"""
    rows = []
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if _local(node.tag) != "properties":
            continue
        props = {_local(child.tag): (child.text or "").strip() for child in node}
        day = props.get("NEW_DATE", "")[:10]
        if len(day) != 10:
            continue
        values = [to_float(props.get(key)) for _, key in TENORS]
        if all(v is None for v in values):
            continue
        rows.append([day] + values)
    return rows


def collect_curve(today: date, errors: list[str]) -> list[list]:
    by_day: dict[str, list] = {}
    for ym in months_back(today, CURVE_MONTHS):
        url = f"{CURVE_URL}?data=daily_treasury_yield_curve&field_tdr_date_value_month={ym}"
        try:
            for row in parse_curve(common.fetch(url)):
                by_day[row[0]] = row
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"수익률 곡선 {ym}: {exc}")
        time.sleep(0.3)
    return [by_day[day] for day in sorted(by_day)]


# ---------- 입찰 ----------

def _yes(value) -> bool:
    return str(value or "").strip().lower() in ("yes", "y", "true")


def _day(value) -> str | None:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def normalize(rec: dict, keys: dict) -> dict | None:
    """출처마다 다른 항목 이름을 한 가지 모양으로 맞춘다."""
    kind = str(rec.get(keys["type"]) or "").strip()
    term = str(rec.get(keys["term"]) or "").strip()
    auction = _day(rec.get(keys["auction"]))
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

    return {
        "auction_date": auction,
        "issue_date": _day(rec.get(keys["issue"])),
        "maturity_date": _day(rec.get(keys["maturity"])),
        "type": kind,
        "term": term,
        "offering_amt": to_float(rec.get(keys["offering"])),
        "high_rate": rate,
        "rate_kind": rate_kind,
        "coupon": to_float(rec.get(keys["coupon"])),
        "bid_to_cover": to_float(rec.get(keys["btc"])),
        "reopening": _yes(rec.get(keys["reopening"])),
    }


def has_result(row: dict) -> bool:
    return row["high_rate"] is not None or row["bid_to_cover"] is not None


def latest_result(rows: list[dict]) -> str:
    return max((r["auction_date"] for r in rows if has_result(r)), default="")


def split_rows(rows: list[dict], today: date) -> tuple[list[dict], list[dict]]:
    """결과가 나온 입찰과, 아직 결과가 없는 입찰(예정·대기)로 나눈다."""
    seen = set()
    unique = []
    for row in rows:
        key = (row["auction_date"], row["type"], row["term"], row["maturity_date"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    cutoff = (today - timedelta(days=PENDING_DAYS)).isoformat()
    results = sorted((r for r in unique if has_result(r)),
                     key=lambda r: r["auction_date"], reverse=True)
    pending = sorted((r for r in unique if not has_result(r) and r["auction_date"] >= cutoff),
                     key=lambda r: r["auction_date"])
    return results, pending


def fetch_treasurydirect(today: date, errors: list[str]) -> list[dict]:
    data = json.loads(common.fetch(f"{TD_AUCTIONED_URL}?format=json&days={AUCTION_DAYS}"))
    if not isinstance(data, list):
        raise ValueError("예상과 다른 응답 형식")
    rows = [r for r in (normalize(x, TD_KEYS) for x in data) if r]
    if data and not rows:
        # 받긴 했는데 하나도 못 읽었으면 항목 이름이 예상과 다른 것이다. 이름을 남겨 둔다.
        first = data[0] if isinstance(data[0], dict) else {}
        raise ValueError(f"{len(data)}건을 받았지만 읽지 못함. 항목 이름: {', '.join(sorted(first)[:60])}")
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


def fetch_fiscaldata(today: date, errors: list[str]) -> list[dict]:
    since = (today - timedelta(days=AUCTION_DAYS)).isoformat()
    query = urlencode(
        {"filter": f"auction_date:gte:{since}", "sort": "-auction_date", "page[size]": "500"},
        safe=":,[]",
    )
    data = json.loads(common.fetch(f"{FISCAL_URL}?{query}"))
    return [r for r in (normalize(x, FISCAL_KEYS) for x in data.get("data", [])) if r]


def collect_auctions(today: date, errors: list[str]) -> dict | None:
    """두 출처를 받아, 결과가 더 최근까지 들어 있는 쪽을 쓴다."""
    best = None
    for name, loader in (("TreasuryDirect", fetch_treasurydirect),
                         ("Fiscal Data", fetch_fiscaldata)):
        try:
            rows = loader(today, errors)
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"{name} 입찰: {exc}")
            continue
        if not rows:
            errors.append(f"{name} 입찰: 받은 자료가 없음")
            continue
        newest = latest_result(rows)
        if best is None or newest > best[1]:
            best = (name, newest, rows)
    if best is None:
        return None
    results, pending = split_rows(best[2], today)
    return {"source": best[0], "latest_result": best[1],
            "results": results, "pending": pending}


# ---------- 실행 ----------

def main() -> int:
    now = datetime.now(timezone.utc)
    today = now.date()
    errors: list[str] = []

    curve_rows = collect_curve(today, errors)
    if not curve_rows:
        print("수익률 곡선을 하나도 받지 못해 기존 파일을 그대로 둔다.")
        for line in errors:
            print(" -", line)
        return 1

    auctions = collect_auctions(today, errors)
    if auctions is None and OUT.exists():
        # 입찰 출처가 모두 실패하면 직전 수집분을 유지한다.
        try:
            auctions = json.loads(OUT.read_text(encoding="utf-8")).get("auctions")
            errors.append("입찰: 이번 수집 실패, 직전 수집분 유지")
        except Exception:
            auctions = None

    write_json(OUT, {
        "schema": 1,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "curve": {
            "tenors": [label for label, _ in TENORS],
            "rows": curve_rows,
        },
        "auctions": auctions,
        "errors": errors,
    })

    print(f"수익률 곡선: {len(curve_rows)}일, 최근 {curve_rows[-1][0]}")
    if auctions:
        print(f"입찰: 출처 {auctions['source']}, 결과 {len(auctions['results'])}건"
              f"(최근 {auctions['latest_result'] or '없음'}), 예정·대기 {len(auctions['pending'])}건")
    else:
        print("입찰: 자료 없음")
    for line in errors:
        print("경고:", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
