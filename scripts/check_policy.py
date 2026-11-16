"""운영 정책 점검. 어긋나는 것이 있으면 실패(종료 코드 1)한다.

1. 스크립트와 화면에 적힌 주소는 모두 허용 목록에 있어야 한다.
2. docs/data/ 에는 등록된 산출 파일만 있어야 한다.
3. 엑셀·PDF 같은 수동 자료는 저장소에 둘 수 없다.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urlsplit

from common import ROOT, load_allowlist

URL_RE = re.compile(r"https?://[^\s\"'<>)\]}`]+")
SCAN_DIRS = ("scripts", "docs")
SCAN_SUFFIXES = {".py", ".html", ".js", ".css"}
BANNED_SUFFIXES = {
    ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".pdf", ".doc", ".docx",
    ".ppt", ".pptx", ".hwp", ".hwpx", ".zip", ".7z", ".msg", ".eml",
}
SKIP_PARTS = {".git", "__pycache__", "node_modules"}


def tracked_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not SKIP_PARTS.intersection(path.parts):
            yield path


def main() -> int:
    allow = load_allowlist()
    hosts = set(allow["hosts"])
    outputs = set(allow["outputs"])
    identifiers = set(allow.get("identifiers", []))
    problems: list[str] = []

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()

        if path.suffix.lower() in BANNED_SUFFIXES:
            problems.append(f"{rel}: 수동 자료 형식은 올릴 수 없음")

        if rel.startswith("docs/data/") and path.name not in outputs:
            problems.append(f"{rel}: 등록되지 않은 데이터 파일 (config/allowlist.json outputs)")

        if rel.split("/")[0] in SCAN_DIRS and path.suffix.lower() in SCAN_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            for url in sorted(set(URL_RE.findall(text))):
                if url in identifiers:
                    continue
                parts = urlsplit(url)
                if parts.scheme != "https" or parts.hostname not in hosts:
                    problems.append(f"{rel}: 허용 목록에 없는 주소 {url}")

    if problems:
        print("정책 점검 실패")
        for line in problems:
            print(" -", line)
        return 1
    print(f"정책 점검 통과 (허용 주소 {len(hosts)}곳, 산출 파일 {len(outputs)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
