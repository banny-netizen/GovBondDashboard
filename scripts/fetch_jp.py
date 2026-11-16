"""일본: 재무성의 국채 금리(CSV)와 입찰 결과(월별 일정 페이지 + 건별 결과 페이지)."""
from __future__ import annotations

import re
import time
from datetime import date
from urllib.parse import urljoin

import common
from common import auction_row, to_float

CODE = "jp"
NAME = "일본"

CURRENT_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
HISTORY_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"
CALENDAR_URL = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/{yymm}e.htm"

TENORS = ["1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "15Y", "20Y", "25Y", "30Y", "40Y"]
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
SKIP_ISSUES = ("treasury discount bills", "liquidity enhancement")
MAX_RESULT_PAGES = 40   # 한 번 실행에서 새로 여는 결과 페이지 수 상한


# ---------- 금리 ----------

def parse_yield_csv(text: str, since: str) -> list[list]:
    """'2026/11/13,1.663,…' 줄만 읽는다. '-' 는 값 없음."""
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        match = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", parts[0]) if parts else None
        if not match:
            continue
        day = f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}"
        if day < since:
            continue
        values = [to_float(p) for p in parts[1:1 + len(TENORS)]]
        values += [None] * (len(TENORS) - len(values))
        if any(v is not None for v in values):
            rows.append([day] + values)
    return rows


def collect_curve(today: date, previous: dict | None) -> list[list]:
    since = common.days_ago(today, common.KEEP_DAYS)
    old = (previous or {}).get("curve", {}).get("rows") or []
    new = parse_yield_csv(common.decode_text(common.fetch(CURRENT_URL)), since)
    # 이력이 비었거나 한 달 넘게 끊겼을 때만 전체 이력 파일(약 1MB)을 받는다.
    if not old or old[-1][0] < common.days_ago(today, 40):
        time.sleep(0.4)
        new = parse_yield_csv(common.decode_text(common.fetch(HISTORY_URL)), since) + new
    return common.merge_rows(old, new, since)


# ---------- 입찰 ----------

def classify(text: str) -> tuple[str, str | None]:
    """종목 설명 → (종류, 만기). '10-year(384)' → ('JGB', '10-Year')."""
    lowered = text.lower()
    if "inflation" in lowered:
        kind = "JGBi"
    elif "climate" in lowered:
        kind = "GX"
    elif "floating" in lowered:
        kind = "JGB FRN"
    else:
        kind = "JGB"
    match = re.search(r"(\d+)\s*-\s*year", lowered)
    return kind, f"{match[1]}-Year" if match else None


def _calendar_date(text: str) -> str | None:
    """'Nov. 2, 2026' → '2026-11-02'."""
    match = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})", text)
    if not match or match[1].lower() not in MONTHS:
        return None
    return f"{int(match[3]):04d}-{MONTHS.index(match[1].lower()) + 1:02d}-{int(match[2]):02d}"


def _us_date(text: str) -> str | None:
    """'11/5/2026' → '2026-11-05'."""
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", text or "")
    return f"{int(match[3]):04d}-{int(match[1]):02d}-{int(match[2]):02d}" if match else None


def parse_calendar(html: str, page_url: str) -> list[dict]:
    """월별 일정 표 → [{date, issue, result_url}]. 단기국채와 유동성공급입찰은 뺀다."""
    out = []
    for table in common.html_tables(html):
        if not table or "auction date" not in table[0][0][0].lower():
            continue
        header = [text.lower() for text, _ in table[0]]
        if not any("auction result" in h for h in header):
            continue
        result_col = next(i for i, h in enumerate(header) if "auction result" in h)
        for row in table[1:]:
            if len(row) <= result_col:
                continue
            day = _calendar_date(row[0][0])
            issue = row[1][0]
            if not day or any(word in issue.lower() for word in SKIP_ISSUES):
                continue
            href = row[result_col][1]
            out.append({"date": day, "issue": issue,
                        "result_url": urljoin(page_url, href) if href else None})
        break
    return out


def _norm(header: str) -> str:
    return re.sub(r"\s+", "", header).lower()


def parse_result(html: str) -> dict | None:
    """건별 결과 페이지의 표 → 입찰 행."""
    for table in common.html_tables(html):
        if len(table) < 2:
            continue
        cells = {_norm(h): v for (h, _), (v, _) in zip(table[0], table[1])}
        if "auctiondate" not in cells or "amountsofbidsaccepted(billionyen)" not in cells:
            continue
        auction = _us_date(cells["auctiondate"])
        if not auction:
            continue
        kind, term = classify(cells.get("security", ""))
        accepted = to_float(cells.get("amountsofbidsaccepted(billionyen)"))
        bids = to_float(cells.get("amountsofcompetitivebids(billionyen)"))
        rate = None
        for key in ("yieldatthelowestacceptedprice", "highestacceptedyield"):
            rate = to_float(cells.get(key))
            if rate is not None:
                break
        return auction_row(
            auction_date=auction,
            issue_date=_us_date(cells.get("issuedate", "")),
            maturity=_us_date(cells.get("maturitydate", "")),
            type=kind,
            term=term,
            offering_amt=accepted * 1e9 if accepted is not None else None,
            high_rate=rate,
            rate_kind="yield" if rate is not None else None,
            coupon=to_float(cells.get("nominalcoupon")),
            bid_to_cover=round(bids / accepted, 2) if bids and accepted else None,
        )
    return None


def _months_around(today: date) -> list[tuple[str, str]]:
    """(YYMM, YYYY-MM) 목록: 석 달 전부터 다음 달까지."""
    out = []
    for offset in range(-3, 2):
        index = today.year * 12 + today.month - 1 + offset
        year, month = divmod(index, 12)
        out.append((f"{year % 100:02d}{month + 1:02d}", f"{year:04d}-{month + 1:02d}"))
    return out


def collect_auctions(today: date, previous: dict | None, errors: list[str]) -> dict | None:
    since = common.days_ago(today, common.AUCTION_DAYS)
    cached = [r for r in ((previous or {}).get("auctions") or {}).get("results", [])
              if r.get("auction_date", "") >= since]
    known = {(r["auction_date"], r["type"], r["term"]) for r in cached}
    months = _months_around(today)
    this_month, last_month = months[3][1], months[2][1]

    entries: list[dict] = []
    got_calendar = False
    for yymm, month in months:
        # 두 달 넘게 지난 일정은 결과를 이미 받아 둔 경우 다시 열지 않는다.
        if month < last_month and any(r["auction_date"].startswith(month) for r in cached):
            continue
        url = CALENDAR_URL.format(yymm=yymm)
        try:
            entries += parse_calendar(common.decode_text(common.fetch(url, retries=2)), url)
            got_calendar = True
        except common.PolicyError:
            raise
        except Exception as exc:
            if month <= this_month:
                errors.append(f"입찰 일정 {month}: {exc}")
        time.sleep(0.4)
    if not got_calendar and not cached:
        return None

    rows = list(cached)
    opened = 0
    for entry in entries:
        kind, term = classify(entry["issue"])
        key = (entry["date"], kind, term)
        if entry["date"] < since or key in known:
            continue
        if entry["result_url"] and opened < MAX_RESULT_PAGES:
            opened += 1
            try:
                row = parse_result(common.decode_text(common.fetch(entry["result_url"], retries=2)))
            except common.PolicyError:
                raise
            except Exception as exc:
                row = None
                errors.append(f"입찰 결과 {entry['date']}: {exc}")
            time.sleep(0.4)
            if row:
                rows.append(row)
                known.add((row["auction_date"], row["type"], row["term"]))
                continue
        # 결과가 아직 없으면 예정으로 싣는다.
        rows.append(auction_row(auction_date=entry["date"], type=kind, term=term))

    results, pending = common.split_auctions(rows, today, pending_days=3)
    return {
        "source": "일본 재무성", "rate_label": "최고 낙찰금리",
        "amount_label": "조 엔", "amount_div": 1e12, "amount_digits": 2,
        "latest_result": common.latest_result(rows),
        "results": results, "pending": pending,
        "note": "이표채만 싣습니다(단기국채·유동성공급입찰 제외). 발행액은 경쟁입찰 낙찰액, 응찰률은 응찰액÷낙찰액입니다.",
    }


def collect(today: date, previous: dict | None) -> dict:
    errors: list[str] = []
    rows = collect_curve(today, previous)
    auctions = None
    try:
        auctions = collect_auctions(today, previous, errors)
    except common.PolicyError:
        raise
    except Exception as exc:
        errors.append(f"입찰: {exc}")
    return {
        "curve": {
            "title": "일본 국채 금리 (재무성 고시)",
            "tenors": TENORS,
            "rows": rows,
        } if rows else None,
        "auctions": auctions,
        "sources": "일본 재무성(MOF)",
        "errors": errors,
    }
