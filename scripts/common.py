"""공용 함수. 허용 목록(config/allowlist.json)에 등록된 주소만 호출한다."""
from __future__ import annotations

import io
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "config" / "allowlist.json"
DATA_DIR = ROOT / "docs" / "data"
USER_AGENT = "GovBondDashboard/1.0 (public-data collector)"

KEEP_DAYS = 400       # 금리 이력 보관 기간(달력일)
AUCTION_DAYS = 90     # 입찰 결과 보관 기간(달력일)


class PolicyError(RuntimeError):
    """운영 정책에 어긋나는 호출. 수집 전체를 멈춘다."""


class RedirectRefused(RuntimeError):
    """상대 서버가 허용 목록 밖으로 넘기려 해서 따라가지 않았다. 해당 출처만 실패로 처리한다."""


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
        try:
            check_url(newurl)
        except PolicyError:
            host = urlsplit(newurl).hostname or "알 수 없는 주소"
            raise RedirectRefused(f"허용 목록 밖 주소({host})로 넘기려 해서 따라가지 않음") from None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirect)


def fetch(url: str, timeout: int = 40, retries: int = 3, pause: float = 2.0) -> bytes:
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
        except (PolicyError, RedirectRefused):
            raise
        except Exception as exc:  # 네트워크·HTTP 오류
            last = exc
            if attempt < retries - 1:
                time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"수집 실패: {urlsplit(url).hostname} ({last})")


# ---------- 값 다루기 ----------

def to_float(value) -> float | None:
    """숫자 문자열을 float로. 빈 값, "null", "-", "." 은 None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").rstrip("%").strip()
    if text in ("", "-", ".", "N/A") or text.lower() == "null":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def iso_day(value) -> str | None:
    """'2026-11-12T00:00:00' 같은 값에서 날짜만. 형식이 다르면 None."""
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[:4].isdigit():
        return text[:10]
    return None


def days_ago(today: date, days: int) -> str:
    return (today - timedelta(days=days)).isoformat()


def curve_rows(tenors: list[str], by_tenor: dict[str, dict[str, float]], since: str) -> list[list]:
    """만기별 {날짜: 금리} 를 [[날짜, 만기 순서대로 금리...]] 로 합친다. 날짜 오름차순."""
    days = sorted({day for series in by_tenor.values() for day in series if day >= since})
    rows = []
    for day in days:
        values = [by_tenor.get(tenor, {}).get(day) for tenor in tenors]
        if any(v is not None for v in values):
            rows.append([day] + values)
    return rows


def merge_rows(old: list[list] | None, new: list[list], since: str) -> list[list]:
    """이전에 받아 둔 행과 새로 받은 행을 합친다. 같은 날짜는 새 값이 이긴다."""
    by_day = {row[0]: row for row in (old or []) if row and row[0] >= since}
    by_day.update({row[0]: row for row in new if row[0] >= since})
    return [by_day[day] for day in sorted(by_day)]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def decode_text(body: bytes) -> str:
    """UTF-8 을 먼저 시도하고, 안 되면 일본어 사이트용 인코딩으로 읽는다."""
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


# ---------- XML · XLSX · HTML ----------

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
            (n for n in names
             if n.lower().startswith("xl/worksheets/sheet") and n.lower().endswith(".xml")),
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


class _TableParser(HTMLParser):
    """HTML 표를 [표][행][(글자, 첫 링크)] 로 뽑는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, str | None]]]] = []
        self._open: list[list] = []
        self._row: list | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._open.append([])
        elif tag == "tr" and self._open:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": [], "href": None}
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href and not self._cell["href"]:
                self._cell["href"] = href.strip()
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell["text"]).split())
            self._row.append((text, self._cell["href"]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._open and self._row:
                self._open[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._open:
            self.tables.append(self._open.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)


def html_tables(html: str) -> list[list[list[tuple[str, str | None]]]]:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return parser.tables


# ---------- 입찰 공통 ----------

def auction_row(**fields) -> dict:
    """나라마다 다른 입찰 자료를 한 가지 모양으로 맞춘 행."""
    row = {
        "auction_date": None, "issue_date": None, "maturity": None,
        "type": "", "bill": False, "term": None,
        "offering_amt": None, "high_rate": None, "rate_kind": None,
        "coupon": None, "bid_to_cover": None, "tag": "",
    }
    unknown = set(fields) - set(row)
    if unknown:
        raise KeyError(f"모르는 항목: {sorted(unknown)}")
    row.update(fields)
    return row


def has_result(row: dict) -> bool:
    return row["high_rate"] is not None or row["bid_to_cover"] is not None


def split_auctions(rows: list[dict], today: date, pending_days: int = 45) -> tuple[list[dict], list[dict]]:
    """결과가 나온 입찰(최근 순)과, 아직 결과가 없는 입찰(가까운 순)으로 나눈다."""
    seen = set()
    unique = []
    for row in rows:
        key = (row["auction_date"], row["type"], row["term"], row["maturity"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    since = days_ago(today, AUCTION_DAYS)
    cutoff = days_ago(today, pending_days)
    results = sorted((r for r in unique if has_result(r) and r["auction_date"] >= since),
                     key=lambda r: r["auction_date"], reverse=True)
    pending = sorted((r for r in unique if not has_result(r) and r["auction_date"] >= cutoff),
                     key=lambda r: r["auction_date"])
    return results, pending


def latest_result(rows: list[dict]) -> str:
    return max((r["auction_date"] for r in rows if has_result(r)), default="")
