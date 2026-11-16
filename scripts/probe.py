"""허용 목록에 있는 주소의 응답 모양을 로그에 찍어 본다. 새 출처를 붙이기 전 확인용.

사용: python3 scripts/probe.py <주소> [<주소> ...]
      주소를 안 주면 저장소 루트의 probe_urls.txt 를 읽는다 (한 줄에 하나).
받은 내용은 화면(로그)에만 찍고 저장소에는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import json
import sys

import common

LIMIT = 100          # 값 하나를 찍는 최대 길이
TEXT_HEAD = 1500     # JSON이 아닐 때 앞부분만 찍는다


def short(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= LIMIT else text[:LIMIT] + "…"


def show_record(rec) -> None:
    if not isinstance(rec, dict):
        print("   ", short(rec))
        return
    for key in rec:
        print(f"    {key} = {short(rec[key])}")


def probe(url: str) -> None:
    print("=" * 70)
    print(url)
    try:
        body = common.fetch(url)
    except Exception as exc:
        print("  실패:", exc)
        return
    print(f"  {len(body)}바이트")
    try:
        data = json.loads(body)
    except ValueError:
        print(body[:TEXT_HEAD].decode("utf-8", errors="replace"))
        return
    if isinstance(data, list):
        print(f"  JSON 목록 {len(data)}건. 첫 항목:")
        if data:
            show_record(data[0])
    elif isinstance(data, dict):
        print(f"  JSON 객체. 최상위 항목: {', '.join(data)}")
        for key, value in data.items():
            if isinstance(value, list) and value:
                print(f"  [{key}] {len(value)}건. 첫 항목:")
                show_record(value[0])
            elif not isinstance(value, list):
                print(f"  [{key}] {short(value)}")
    else:
        print("  ", short(data))


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        path = common.ROOT / "probe_urls.txt"
        if path.exists():
            urls = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
    if not urls:
        print("확인할 주소가 없습니다.")
        return 0
    for url in urls:
        probe(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
