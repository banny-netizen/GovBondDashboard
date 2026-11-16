"""일별 수집. 나라별로 따로 받아 docs/data/<코드>.json 에 쓴다.

한 나라가 실패해도 다른 나라는 그대로 진행하고, 실패한 나라는 직전 수집분을 남겨 둔다.
허용 목록 밖 주소를 직접 부르려 한 경우(PolicyError)에만 전체를 멈춘다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import common
import fetch_ca
import fetch_de
import fetch_ez
import fetch_jp
import fetch_uk
import fetch_us

SOURCES = [fetch_us, fetch_ca, fetch_de, fetch_uk, fetch_jp, fetch_ez]


def run_one(module, now: datetime) -> tuple[bool, str]:
    """한 나라를 수집해 파일에 쓴다. (성공 여부, 한 줄 요약)을 돌려준다."""
    path = common.DATA_DIR / f"{module.CODE}.json"
    previous = common.read_json(path)
    errors: list[str] = []
    try:
        got = module.collect(now.date(), previous)
        errors += got.get("errors", [])
    except common.PolicyError:
        raise
    except Exception as exc:
        got = {}
        errors.append(f"수집 실패: {exc}")

    curve = got.get("curve")
    fresh = curve is not None
    if curve is None:
        curve = (previous or {}).get("curve")
        if curve:
            errors.append("금리: 이번 수집 실패, 직전 수집분 유지")
    if not curve or not curve.get("rows"):
        return False, f"{module.NAME}: 받은 금리 자료가 없어 파일을 쓰지 않음 ({'; '.join(errors)})"

    # 입찰을 못 받았으면 직전 수집분을 남겨 둔다.
    auctions = got.get("auctions") or (previous or {}).get("auctions")

    common.write_json(path, {
        "schema": 2,
        "code": module.CODE,
        "name": module.NAME,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "curve": curve,
        "auctions": auctions,
        "auctions_note": got.get("auctions_note") or (previous or {}).get("auctions_note"),
        "sources": got.get("sources") or (previous or {}).get("sources"),
        "errors": errors,
    })
    summary = f"{module.NAME}: 금리 {len(curve['rows'])}일(최근 {curve['rows'][-1][0]})"
    if auctions:
        summary += (f", 입찰 결과 {len(auctions['results'])}건(최근 {auctions['latest_result'] or '없음'})"
                    f"·예정 {len(auctions['pending'])}건")
    if errors:
        summary += " | 경고: " + "; ".join(errors)
    return fresh, summary


def main() -> int:
    now = datetime.now(timezone.utc)
    succeeded = 0
    for module in SOURCES:
        ok, summary = run_one(module, now)
        succeeded += ok
        print(("완료  " if ok else "실패  ") + summary)
    print(f"{succeeded}/{len(SOURCES)}개 나라 수집")
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
