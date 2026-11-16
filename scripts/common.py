"""공용 함수. 허용 목록(config/allowlist.json)에 등록된 주소만 호출한다."""
from __future__ import annotations

import json
import time
import urllib.request
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
