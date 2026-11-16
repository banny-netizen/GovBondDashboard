"""공용 함수. 허용 목록(config/allowlist.json)에 등록된 주소만 호출한다."""
from __future__ import annotations

import io
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "config" / "allowlist.json"
USER_AGENT = "GovBondDashboard/1.0 (public-data collector)"


class PolicyError(RuntimeError):
    """운영 정책에 어긋나는 호출."""


def load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def check_url(url: str) -> None:
    """https이고 허용 목록에 있는 호스트인지 확인한다. 아니면 PolicyError."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise PolicyError(f"https가 아닌 주소: {url}")
    if parts.hostname not in load_allowlist()["hosts"]:
        raise PolicyError(f"허용 목록에 없는 주소: {url}")


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가기 전에 목적지도 허용 목록으로 검사한다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirect)


def fetch(url: str, timeout: int = 30, retries: int = 3, pause: float = 2.0) -> bytes:
    """허용된 주소에서 본문을 받아 온다. 일시 오류는 몇 번 다시 시도한다."""
    check_url(url)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
            )
            with _opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except PolicyError:
            raise
        except Exception as exc:  # 네트워크·HTTP 오류
            last = exc
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"수집 실패: {url} ({last})")


def to_float(value) -> float | None:
    """숫자 문자열을 float로. 빈 값과 문자열 "null"은 None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() == "null":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def local_name(tag: str) -> str:
    """XML 태그에서 네임스페이스를 뗀 이름."""
    return tag.rsplit("}", 1)[-1]


def excel_date(serial) -> str | None:
    """엑셀 날짜 일련번호 → YYYY-MM-DD."""
    number = to_float(serial)
    if number is None or not 20000 <= number <= 80000:
        return None
    return (date(1899, 12, 30) + timedelta(days=int(number))).isoformat()


def _column_index(ref: str) -> int:
    index = 0
    for ch in ref:
        if not ch.isalpha():
            break
        index = index * 26 + (ord(ch.upper()) - 64)
    return index - 1


def xlsx_sheets(data: bytes, max_bytes: int = 30_000_000) -> list[list[list[str]]]:
    """XLSX 파일의 시트별 행 목록. 셀은 문자열(숫자·날짜는 저장된 값 그대로)."""
    sheets = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > max_bytes:
            raise ValueError("XLSX 압축을 풀면 너무 큼")
        names = archive.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                if local_name(item.tag) == "si":
                    shared.append("".join(node.text or "" for node in item.iter()
                                          if local_name(node.tag) == "t"))
        sheet_names = sorted(
            (n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")),
            key=lambda n: int("".join(ch for ch in n.rsplit("/", 1)[-1] if ch.isdigit()) or 0),
        )
        for name in sheet_names:
            rows = []
            for row in ET.fromstring(archive.read(name)).iter():
                if local_name(row.tag) != "row":
                    continue
                cells: dict[int, str] = {}
                for cell in row:
                    if local_name(cell.tag) != "c":
                        continue
                    kind = cell.get("t")
                    if kind == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter()
                                        if local_name(node.tag) == "t")
                    else:
                        value = next((node.text or "" for node in cell
                                      if local_name(node.tag) == "v"), "")
                        if kind == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                    cells[_column_index(cell.get("r", "A"))] = value.strip()
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            sheets.append(rows)
    return sheets
