"""캐나다: 캐나다 중앙은행(Valet API)의 벤치마크 국채 금리와 국채 입찰 결과."""
from __future__ import annotations

import json
from datetime import date

import common
from common import auction_row, iso_day, to_float

CODE = "ca"
NAME = "캐나다"

YIELDS_URL = "https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=400"
AUCTIONS_URL = "https://www.bankofcanada.ca/valet/observations/group/AUC_BOND_RESULTS/json"

# 장기물(LONG)은 30년 지표물이라 30Y 로 적는다.
TENORS = [
    ("2Y", "BD.CDN.2YR.DQ.YLD"), ("3Y", "BD.CDN.3YR.DQ.YLD"), ("5Y", "BD.CDN.5YR.DQ.YLD"),
    ("7Y", "BD.CDN.7YR.DQ.YLD"), ("10Y", "BD.CDN.10YR.DQ.YLD"), ("30Y", "BD.CDN.LONG.DQ.YLD"),
]


def _v(obs: dict, key: str):
    item = obs.get(key)
    return item.get("v") if isinstance(item, dict) else None


def parse_yields(data: dict, since: str) -> list[list]:
    by_tenor: dict[str, dict[str, float]] = {label: {} for label, _ in TENORS}
    for obs in data.get("observations", []):
        day = iso_day(obs.get("d"))
        if not day:
            continue
        for label, key in TENORS:
            value = to_float(_v(obs, key))
            if value is not None:
                by_tenor[label][day] = value
    return common.curve_rows([label for label, _ in TENORS], by_tenor, since)


def parse_auctions(data: dict, since: str) -> list[dict]:
    rows = []
    for obs in data.get("observations", []):
        auction = iso_day(_v(obs, "AUC_BOND_AUCTION_DATE"))
        maturity = iso_day(_v(obs, "AUC_BOND_MATURITY_DATE"))
        if not auction or not maturity or auction < since:
            continue  # 날짜만 든 머리 행과 오래된 건은 건너뛴다
        amount = to_float(_v(obs, "AUC_BOND_AMOUNT"))
        outstanding = to_float(_v(obs, "AUC_BOND_OUTSTANDING_AFTER"))
        years = to_float(_v(obs, "AUC_BOND_TERM_YEARS"))
        tag = ""
        if amount is not None and outstanding is not None:
            tag = "리오픈" if outstanding > amount + 0.5 else "신규"
        rows.append(auction_row(
            auction_date=auction,
            issue_date=iso_day(_v(obs, "AUC_BOND_ISSUE_DATE")),
            maturity=maturity,
            type="Bond",
            term=f"{years:g}-Year" if years is not None else None,
            offering_amt=amount * 1e6 if amount is not None else None,
            high_rate=to_float(_v(obs, "AUC_BOND_HIGH_YIELD")),
            rate_kind="yield" if _v(obs, "AUC_BOND_HIGH_YIELD") else None,
            coupon=to_float(_v(obs, "AUC_BOND_COUPON_RATE")),
            bid_to_cover=to_float(_v(obs, "AUC_BOND_COVERAGE")),
            tag=tag,
        ))
    return rows


def collect(today: date, previous: dict | None) -> dict:
    errors: list[str] = []
    since = common.days_ago(today, common.KEEP_DAYS)

    rows = parse_yields(json.loads(common.fetch(YIELDS_URL)), since)

    auctions = None
    try:
        parsed = parse_auctions(json.loads(common.fetch(AUCTIONS_URL)),
                                common.days_ago(today, common.AUCTION_DAYS))
        results, pending = common.split_auctions(parsed, today)
        auctions = {
            "source": "캐나다 중앙은행", "rate_label": "최고 낙찰금리",
            "amount_label": "억 캐나다달러", "amount_div": 1e8, "amount_digits": 0,
            "latest_result": common.latest_result(parsed),
            "results": results, "pending": pending,
            "note": "명목 국채만 싣습니다. 단기국채(T-bill)와 물가연동채는 빠져 있습니다.",
        }
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"입찰: {exc}")

    return {
        "curve": {
            "title": "캐나다 벤치마크 국채 금리",
            "note": "30년은 장기 지표물 금리입니다.",
            "tenors": [label for label, _ in TENORS],
            "rows": rows,
        } if rows else None,
        "auctions": auctions,
        "sources": "캐나다 중앙은행(Bank of Canada)",
        "errors": errors,
    }
