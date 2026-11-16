"""확인용 브랜치 전용 임시 분석. main 에는 올리지 않는다."""
import io, json, sys, zipfile, csv
from collections import Counter
import xml.etree.ElementTree as ET
import common

def head(title): print("\n" + "#" * 8, title)

# (a) Finanzagentur XLSX 구조
try:
    head("DE XLSX")
    body = common.fetch("https://www.deutsche-finanzagentur.de/fileadmin/user_upload/Institutionelle-investoren/auktionen/emissionsergebnisse_aktuell_en.xlsx")
    print(len(body), body[:8])
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for info in z.infolist():
            print("  ", info.filename, info.file_size)
        for name in z.namelist():
            if name.endswith(".xml") and ("sheet" in name.lower() or "workbook" in name.lower() or "sharedStrings" in name):
                raw = z.read(name).decode("utf-8", "replace")
                print("  ---", name, len(raw)); print(raw[:1800])
except Exception as exc:
    print("실패", exc)

# (b) DMO 발행 내역: 유형 분포와 최근 건
try:
    head("UK DMO D2.1E")
    body = common.fetch("https://www.dmo.gov.uk/data/XmlDataReport?reportCode=D2.1E")
    root = ET.fromstring(body.decode("utf-8-sig").strip())
    recs = [dict(el.attrib) for el in root]
    print(len(recs), "건", "| 유형", Counter(r.get("ISSUANCE_TYPE") for r in recs).most_common(20))
    recent = sorted((r for r in recs if r.get("ACTUAL_DATE", "") >= "2026-08-01"), key=lambda r: r["ACTUAL_DATE"])
    print("2026-08-01 이후", len(recent), "건")
    for r in recent[-45:]:
        print("  ", json.dumps(r, ensure_ascii=False))
except Exception as exc:
    print("실패", exc)

# (c) 캐나다 입찰: 마지막 14건 전체 항목
try:
    head("CA AUC_BOND_RESULTS")
    data = json.loads(common.fetch("https://www.bankofcanada.ca/valet/observations/group/AUC_BOND_RESULTS/json"))
    obs = data["observations"]
    for o in obs[-14:]:
        print("  ", json.dumps({k.replace("AUC_BOND_", ""): (v.get("v") if isinstance(v, dict) else v) for k, v in o.items()}, ensure_ascii=False))
    for key, detail in list(data["seriesDetail"].items())[:3]:
        print("  detail", key, json.dumps(detail, ensure_ascii=False)[:300])
except Exception as exc:
    print("실패", exc)

# (d) ECB: 한 번에 여러 만기, 받은 키 목록
try:
    head("ECB YC")
    url = ("https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM."
           "SR_3M+SR_6M+SR_1Y+SR_2Y+SR_3Y+SR_5Y+SR_7Y+SR_10Y+SR_15Y+SR_20Y+SR_30Y?format=csvdata&lastNObservations=2")
    rows = list(csv.DictReader(io.StringIO(common.fetch(url).decode("utf-8-sig"))))
    print(len(rows), "행")
    for r in rows: print("  ", r["DATA_TYPE_FM"], r["TIME_PERIOD"], r["OBS_VALUE"])
except Exception as exc:
    print("실패", exc)

# (e) 분데스방크: 다른 만기 지표물·추정 곡선 키가 있는지
for label, url in [
    ("BBSSY 2Y", "https://api.statistiken.bundesbank.de/rest/download/BBSSY/D.REN.EUR.A610.000000WT0202.A?format=csv&lang=en"),
    ("BBSSY 30Y", "https://api.statistiken.bundesbank.de/rest/download/BBSSY/D.REN.EUR.A640.000000WT3030.A?format=csv&lang=en"),
    ("BBSIS Svensson 10Y", "https://api.statistiken.bundesbank.de/rest/download/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A?format=csv&lang=en"),
    ("BBSIS Svensson 1Y", "https://api.statistiken.bundesbank.de/rest/download/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R01XX.R.A.A._Z._Z.A?format=csv&lang=en"),
    ("BBSIS Svensson 0.5Y", "https://api.statistiken.bundesbank.de/rest/download/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R005X.R.A.A._Z._Z.A?format=csv&lang=en"),
]:
    try:
        head("DE " + label)
        text = common.fetch(url, retries=1).decode("utf-8-sig", "replace")
        lines = text.strip().splitlines()
        print(len(lines), "줄"); print("\n".join(lines[:3])); print("\n".join(lines[-3:]))
    except Exception as exc:
        print("실패", exc)

# (f) 캐나다 금리: recent=400 이 통하는지
try:
    head("CA yields recent=400")
    data = json.loads(common.fetch("https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=400"))
    obs = data["observations"]
    print(len(obs), obs[0]["d"], obs[-1]["d"], json.dumps(obs[0])[:400])
except Exception as exc:
    print("실패", exc)
