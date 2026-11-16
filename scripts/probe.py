"""허용 목록에 있는 주소의 응답 모양을 로그에 찍어 본다. 새 출처를 붙이기 전 확인용.

사용: python3 scripts/probe.py <주소> [<주소> ...]
      주소를 안 주면 저장소 루트의 probe_urls.txt 를 읽는다 (한 줄에 하나).
받은 내용은 화면(로그)에만 찍고 저장소에는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import json
import sys

import common

LIMIT = 110          # 값 하나를 찍는 최대 길이
TEXT_HEAD = 2600     # JSON이 아닐 때 앞부분
TEXT_TAIL = 900      # JSON이 아닐 때 끝부분
MAX_KEYS = 45


def short(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= LIMIT else text[:LIMIT] + "…"


def show(value, indent: str = "    ", depth: int = 0) -> None:
    if isinstance(value, dict) and depth < 2:
        for i, key in enumerate(value):
            if i >= MAX_KEYS:
                print(f"{indent}… 외 {len(value) - MAX_KEYS}개")
                break
            item = value[key]
            if isinstance(item, (dict, list)) and item and depth < 1:
                print(f"{indent}{key}:")
                show(item, indent + "    ", depth + 1)
            else:
                print(f"{indent}{key} = {short(item)}")
    elif isinstance(value, list):
        print(f"{indent}목록 {len(value)}건")
        if value:
            print(f"{indent}첫 항목: {short(value[0])}")
            print(f"{indent}끝 항목: {short(value[-1])}")
    else:
        print(f"{indent}{short(value)}")


def probe(url: str) -> None:
    print("=" * 70)
    print(url)
    try:
        body = common.fetch(url)
    except Exception as exc:
        print("  실패:", exc)
        return
    print(f"  {len(body)}바이트")
    if body[:4] == b"PK\x03\x04":
        try:
            for number, rows in enumerate(common.xlsx_sheets(body), 1):
                print(f"  XLSX 시트 {number}: {len(rows)}행")
                for row in rows[:14] + rows[-4:]:
                    print("    | " + " | ".join(short(cell)[:28] for cell in row[:16]))
        except Exception as exc:
            print("  XLSX 읽기 실패:", exc)
        return
    try:
        data = json.loads(body)
    except ValueError:
        text = body.decode("utf-8", errors="replace")
        print(text[:TEXT_HEAD])
        if len(text) > TEXT_HEAD + TEXT_TAIL:
            print("  …(중략)…")
            print(text[-TEXT_TAIL:])
        return
    if isinstance(data, list):
        print(f"  JSON 목록 {len(data)}건. 첫 항목:")
        if data:
            show(data[0])
    else:
        print("  JSON 객체:")
        show(data)


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
