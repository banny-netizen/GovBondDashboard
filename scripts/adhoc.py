"""확인용 브랜치 전용 임시 분석. main 에는 올리지 않는다."""
import re, time
from urllib.parse import urljoin
import common

def head(title): print("\n" + "#" * 8, title)

try:
    head("DE XLSX rows")
    body = common.fetch("https://www.deutsche-finanzagentur.de/fileadmin/user_upload/Institutionelle-investoren/auktionen/emissionsergebnisse_aktuell_en.xlsx")
    for rows in common.xlsx_sheets(body):
        print(len(rows), "행")
        for row in rows[:16] + rows[-14:]:
            print("  | " + " | ".join(cell[:30] for cell in row))
except Exception as exc:
    print("실패", exc)

try:
    head("DE BBSSY 5Y")
    lines = common.fetch("https://api.statistiken.bundesbank.de/rest/download/BBSSY/D.REN.EUR.A620.000000WT0505.A?format=csv&lang=en").decode("utf-8-sig").strip().splitlines()
    print(len(lines)); print("\n".join(lines[:2] + lines[-2:]))
except Exception as exc:
    print("실패", exc)

BASE = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/"
seen_kinds = {}
for ym in ("2611e.htm", "2610e.htm", "2612e.htm"):
    try:
        head("JP calendar " + ym)
        html = common.decode_text(common.fetch(BASE + ym))
        tables = common.html_tables(html)
        print(len(tables), "개 표;", [len(t) for t in tables])
        for row in tables[0][:40]:
            print("  | " + " | ".join(f"{text[:60]}{' -> ' + href if href else ''}" for text, href in row))
        for row in tables[0][1:]:
            if len(row) >= 4 and row[3][1]:
                kind = re.sub(r"\(.*?\)|\d+", "", row[1][0]).strip().lower()
                seen_kinds.setdefault(kind, urljoin(BASE + ym, row[3][1]))
    except Exception as exc:
        print("실패", exc)
    time.sleep(0.5)

for kind, url in list(seen_kinds.items())[:10]:
    try:
        head("JP result [" + kind + "] " + url)
        html = common.decode_text(common.fetch(url))
        for table in common.html_tables(html)[:3]:
            for row in table[:4]:
                print("  | " + " | ".join(text[:70] for text, _ in row))
            print("  --")
    except Exception as exc:
        print("실패", exc)
    time.sleep(0.5)
