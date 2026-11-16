"""캐나다·독일·영국·일본·유로존 파싱 테스트. 자료는 2026-11-16 실제 응답에서 옮겼다."""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import collect  # noqa: E402
import common  # noqa: E402
import fetch_ca  # noqa: E402
import fetch_de  # noqa: E402
import fetch_ez  # noqa: E402
import fetch_jp  # noqa: E402
import fetch_uk  # noqa: E402

TODAY = date(2026, 11, 16)
SINCE = "2026-08-18"


class CanadaTest(unittest.TestCase):
    YIELDS = {"observations": [
        {"d": "2026-11-12", "BD.CDN.RRB.DQ.YLD": {"v": "1.94"}, "BD.CDN.2YR.DQ.YLD": {"v": "3.33"},
         "BD.CDN.3YR.DQ.YLD": {"v": "3.41"}, "BD.CDN.5YR.DQ.YLD": {"v": "3.53"},
         "BD.CDN.7YR.DQ.YLD": {"v": "3.61"}, "BD.CDN.10YR.DQ.YLD": {"v": "3.78"},
         "BD.CDN.LONG.DQ.YLD": {"v": "4.09"}},
        {"d": "2026-11-09", "BD.CDN.2YR.DQ.YLD": {"v": "3.13"}},
    ]}
    AUCTIONS = {"observations": [
        {"bond_id": "2026-11-12_19002066696", "AUC_BOND_AUCTION_DATE": {"v": "2026-11-12"},
         "AUC_BOND_BID_DEADLINE": {"v": "12:00"}, "AUC_BOND_ISSUE_DATE": {"v": "2026-11-13"}},
        {"bond_id": "2026-11-12_19002066696-1", "AUC_BOND_AUCTION_DATE": {"v": "2026-11-12"},
         "AUC_BOND_ISSUE_DATE": {"v": "2026-11-13"}, "AUC_BOND_TERM_YEARS": {"v": "2"},
         "AUC_BOND_MATURITY_DATE": {"v": "2029-02-01"}, "AUC_BOND_AMOUNT": {"v": "5500.000"},
         "AUC_BOND_COUPON_RATE": {"v": "3.250"}, "AUC_BOND_AVG_YIELD": {"v": "3.377"},
         "AUC_BOND_HIGH_YIELD": {"v": "3.379"}, "AUC_BOND_COVERAGE": {"v": "2.698"},
         "AUC_BOND_OUTSTANDING_AFTER": {"v": "5500.000"}},
        {"bond_id": "2026-11-09_19002066695-1", "AUC_BOND_AUCTION_DATE": {"v": "2026-11-09"},
         "AUC_BOND_ISSUE_DATE": {"v": "2026-11-10"}, "AUC_BOND_TERM_YEARS": {"v": "10"},
         "AUC_BOND_MATURITY_DATE": {"v": "2036-12-01"}, "AUC_BOND_AMOUNT": {"v": "5000.000"},
         "AUC_BOND_COUPON_RATE": {"v": "3.500"}, "AUC_BOND_HIGH_YIELD": {"v": "3.687"},
         "AUC_BOND_COVERAGE": {"v": "2.224"}, "AUC_BOND_OUTSTANDING_AFTER": {"v": "30000.000"}},
        {"bond_id": "2026-11-19_19002066698-1", "AUC_BOND_AUCTION_DATE": {"v": "2026-11-19"},
         "AUC_BOND_ISSUE_DATE": {"v": "2026-11-20"}, "AUC_BOND_TERM_YEARS": {"v": "5"},
         "AUC_BOND_MATURITY_DATE": {"v": "2032-03-01"}, "AUC_BOND_COUPON_RATE": {"v": "3.500"},
         "AUC_BOND_AMOUNT": {"v": "5000.000"}},
        {"bond_id": "1998-10-28_HIST_BOND_1", "AUC_BOND_AUCTION_DATE": {"v": "1998-10-28"},
         "AUC_BOND_MATURITY_DATE": {"v": "2008-06-01"}},
    ]}

    def test_yields(self):
        rows = fetch_ca.parse_yields(self.YIELDS, SINCE)
        self.assertEqual(rows[0], ["2026-11-09", 3.13, None, None, None, None, None])
        self.assertEqual(rows[1], ["2026-11-12", 3.33, 3.41, 3.53, 3.61, 3.78, 4.09])

    def test_auctions(self):
        rows = fetch_ca.parse_auctions(self.AUCTIONS, SINCE)
        self.assertEqual(len(rows), 3)             # 머리 행과 옛 자료는 빠진다
        results, pending = common.split_auctions(rows, TODAY)
        self.assertEqual([r["auction_date"] for r in results], ["2026-11-12", "2026-11-09"])
        first = results[0]
        self.assertEqual((first["term"], first["offering_amt"], first["high_rate"]), ("2-Year", 5.5e9, 3.379))
        self.assertEqual((first["bid_to_cover"], first["coupon"], first["tag"]), (2.698, 3.25, "신규"))
        self.assertEqual(results[1]["tag"], "리오픈")
        self.assertEqual([(r["auction_date"], r["term"], r["tag"]) for r in pending],
                         [("2026-11-19", "5-Year", "")])


class GermanyTest(unittest.TestCase):
    CSV = '''"",BBSSY.D.REN.EUR.A630.000000WT1010.A,BBSSY.D.REN.EUR.A630.000000WT1010.A_FLAGS
"",Daily yield of the current 10 year federal bond,
unit,PROZENT,
last update,2026-11-13 12:42:40,
2001-10-01,4.78,
2026-11-06,3.22,
2026-11-07,.,No value available
2026-11-12,3.29,
2026-11-13,3.37,
'''
    SHEET = [
        ["Auction Results"],
        ["No.", "Date", "", "Bond1", "Coupon", "Maturity", "Maturity-", "volume", "Type2", "Issuance",
         "Bids", "tive Bids", "competi-", "Volumes", "accepted", "Average", "Average", "Quote", "Cover-"],
        ["1", "46027", "DE000BU0E287", "Bubill", "", "46127", "12 M", "2000", "R", "M-A",
         "3590", "2510", "1080", "1400", "99.46147", "99.46174", "1.988", "600", "2.6"],
        ["108", "46335", "DE000BU0E469", "Bubill", "", "46672", "12 M", "2500", "R", "M-A",
         "3540", "2955", "585", "2065", "97.34937", "97.36612", "2.907", "435", "1.7"],
        ["109", "46337", "DE000BU2D012", "Bund", "0.029", "57207", "30 Y", "1500", "R", "M-A",
         "1398", "908", "490", "1078", "86.39", "86.43", "3.66", "422", "1.3"],
        ["Sum:", "", "", "", "", "", "", "485500", "", "", "637161", "380336", "256825",
         "377797.9", "", "", "", "", "1.685922925987"],
        ["1", "Bund = Federal bond,  Bobl = Federal note"],
    ]

    def test_yield_csv(self):
        got = fetch_de.parse_bundesbank_csv(self.CSV, SINCE)
        self.assertEqual(got, {"2026-11-06": 3.22, "2026-11-12": 3.29, "2026-11-13": 3.37})

    def test_auctions(self):
        rows = fetch_de.parse_auctions([self.SHEET], SINCE)
        self.assertEqual([r["auction_date"] for r in rows], ["2026-11-09", "2026-11-11"])
        bill, bund = rows
        self.assertTrue(bill["bill"])
        self.assertEqual((bill["term"], bill["offering_amt"], bill["high_rate"]), ("12-Month", 2.5e9, 2.907))
        self.assertIsNone(bill["coupon"])
        self.assertEqual((bund["type"], bund["term"], bund["coupon"]), ("Bund", "30-Year", 2.9))
        self.assertEqual((bund["maturity"], bund["bid_to_cover"], bund["tag"]), ("2056-08-15", 1.3, "리오픈"))


class UnitedKingdomTest(unittest.TestCase):
    CSV = """DATE,IUDSNPY,IUDMNPY,IUDLNPY
10 Nov 2026,4.8471,5.1906,5.4859
11 Nov 2026,4.8852,5.2044,5.4858
"""
    XML = """

<Data>
  <View_Gilt_Issuance_History INSTRUMENT_NAME="4 1/8% Treasury Gilt 2033" ISIN_CODE="GB00BVP99780" ACTUAL_DATE="2026-11-13T00:00:00" ISSUANCE_TYPE="Outright" NOMINAL_ISSUED="4000.000000000000000000" ISSUE_CLEAN_PRICE="95.34" ISSUE_YIELD="4.993188000000" INDEXATION_LAG="" />
  <View_Gilt_Issuance_History INSTRUMENT_NAME="1 1/8% Index-linked Treasury Gilt 2035" ISIN_CODE="GB00BT7HZZ68" ACTUAL_DATE="2026-10-07T00:00:00" ISSUANCE_TYPE="Outright" NOMINAL_ISSUED="1250.000000000000000000" ISSUE_CLEAN_PRICE="93.96" ISSUE_YIELD="1.860047000000" INDEXATION_LAG="3 months" />
  <View_Gilt_Issuance_History INSTRUMENT_NAME="5 3/8% Treasury Gilt 2056" ISIN_CODE="GB00BT7J0241" ACTUAL_DATE="2026-09-09T00:00:00" ISSUANCE_TYPE="Syndication" NOMINAL_ISSUED="4250.000000000000000000" ISSUE_CLEAN_PRICE="93.80" ISSUE_YIELD="5.816800000000" INDEXATION_LAG="" />
  <View_Gilt_Issuance_History INSTRUMENT_NAME="4 5/8% Green Gilt 2037" ISIN_CODE="GB00BVP99905" ACTUAL_DATE="2026-11-04T00:00:00" ISSUANCE_TYPE="Outright" NOMINAL_ISSUED="3250.000000000000000000" ISSUE_CLEAN_PRICE="94.91" ISSUE_YIELD="5.267781000000" INDEXATION_LAG="" />
  <View_Gilt_Issuance_History INSTRUMENT_NAME="9½% Conversion Stock 2005" ISIN_CODE="GB0008987777" ACTUAL_DATE="2026-09-23T00:00:00" ISSUANCE_TYPE="Cancellation" NOMINAL_ISSUED="-0.000001000000000000" ISSUE_CLEAN_PRICE="N/A" ISSUE_YIELD="N/A" INDEXATION_LAG="" />
  <View_Gilt_Issuance_History INSTRUMENT_NAME="0 1/8% Index-linked Treasury Gilt 2019" ISIN_CODE="GB00BBDR7T29" ACTUAL_DATE="2013-08-21T00:00:00" ISSUANCE_TYPE="Outright" NOMINAL_ISSUED="1794.585000000000000000" ISSUE_CLEAN_PRICE="106.52" ISSUE_YIELD="-0.886797000000" INDEXATION_LAG="3 months" />
</Data>"""

    def test_yields(self):
        rows = fetch_uk.parse_boe_csv(self.CSV, SINCE)
        self.assertEqual(rows, [["2026-11-10", 4.847, 5.191, 5.486], ["2026-11-11", 4.885, 5.204, 5.486]])

    def test_error_page_is_rejected(self):
        with self.assertRaises(ValueError):
            fetch_uk.parse_boe_csv("<html><body>Error</body></html>", SINCE)

    def test_coupon_from_name(self):
        cases = {"4 5/8% Treasury Gilt 2032": 4.625, "0½% Treasury Gilt 2029": 0.5,
                 "4¼% Treasury Gilt 2040": 4.25, "4% Treasury Gilt 2063": 4.0,
                 "0 1/8% Treasury Gilt 2028": 0.125, "1 7/8% Index-linked Treasury Gilt 2049": 1.875}
        for name, want in cases.items():
            self.assertEqual(fetch_uk.parse_coupon(name), want, name)

    def test_issuance(self):
        rows = fetch_uk.parse_issuance(self.XML, SINCE)
        results, pending = common.split_auctions(rows, TODAY)
        self.assertEqual(pending, [])
        self.assertEqual([r["auction_date"] for r in results],
                         ["2026-11-13", "2026-11-04", "2026-10-07", "2026-09-09"])
        gilt, green, linker, syndicated = results
        self.assertEqual((gilt["type"], gilt["maturity"], gilt["coupon"]), ("Gilt", "2033", 4.125))
        self.assertEqual((gilt["offering_amt"], gilt["high_rate"], gilt["tag"]), (4e9, 4.993, "입찰"))
        self.assertEqual(green["type"], "Green Gilt")
        self.assertEqual(linker["type"], "IL Gilt")
        self.assertEqual(syndicated["tag"], "신디케이션")


class JapanTest(unittest.TestCase):
    CSV = """Interest Rate (November 2026),,,,,,,,,,,,,,,(Unit : %)
Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y,15Y,20Y,25Y,30Y,40Y
2026/11/12,1.653,1.857,1.953,2.1,2.209,2.307,2.423,2.562,2.694,2.841,3.382,3.698,4.004,3.974,4.006
2026/11/13,1.663,1.882,1.983,2.145,2.262,2.363,2.481,2.626,2.758,2.899,3.445,3.757,4.053,4.038,-
,,,,,,,,,,,,,,,
"  If you cannot download the latest csv data, please clear the browser's cache.",,,,,,,,,,,,,,,
"""
    CALENDAR = """<html><body>
<table>
<tr><th>Auction Date</th><th>Issue</th><th>Auction<br>Announcement</th><th>Auction<br>Result</th><th>Non-price - competitive Auction II</th></tr>
<tr><td>Nov. 5, 2026</td><td>10-year(384)</td><td><a href="announcement/auct20261029e.htm">Detail</a></td>
    <td><a href="	https://www.mof.go.jp/english/policy/jgbs/auction/calendar/eresul/eresul20261105.htm">Detail</a></td><td><a href="eresul/eresul20261105a.htm">Detail</a></td></tr>
<tr><td>Nov. 6, 2026</td><td>Treasury Discount Bills (3-month)(1417)</td><td>Detail</td><td><a href="etbill/etbillresul/eresul20261106.htm">Detail</a></td><td>-</td></tr>
<tr><td>Nov. 16, 2026</td><td>10-year Inflation-Indexed Bonds(31)</td><td>Detail</td><td><a href="eresul/eresul20261116.htm">Detail</a></td><td>-</td></tr>
<tr><td>Nov. 18, 2026</td><td>20-year</td><td>Detail</td><td>Detail</td><td>Detail</td></tr>
<tr><td>Nov. 20, 2026</td><td>Liquidity Enhancement Auction (remaining maturities of 1-5 years)</td><td>Detail</td><td>Detail Issues Re-opened</td><td>-</td></tr>
<tr><td>May 7, 2026</td><td>5-year Japan Climate Transition Bonds(6)</td><td>Detail</td><td>Detail</td><td>-</td></tr>
</table>
<table><tr><th>Auction Date</th><th>Borrowing Date</th><th>Issue</th></tr><tr><td>Nov. 5, 2026</td><td>Nov. 13, 2026</td><td>Borrowing</td></tr></table>
</body></html>"""
    RESULT = """<table>
<tr><th>Security</th><th>Issue Number</th><th>Auction Date</th><th>Issue Date</th><th>Maturity Date</th><th>Nominal Coupon</th>
<th>Amounts of Competitive Bids (billion yen)</th><th>Amounts of Bids Accepted (billion yen)</th><th>Lowest Accepted Price (per 100 yen)</th>
<th>Yield at the Lowest Accepted Price</th><th>Allotment for Bids at the Lowest Accepted Price</th><th>Weighted Average Price (per 100 yen)</th>
<th>Yield at the Average Price</th><th>Amounts of Bids Accepted at the Non-price -competitive Auction I (billion yen)</th></tr>
<tr><td>10-Year</td><td>384</td><td>11/5/2026</td><td>11/6/2026</td><td>9/20/2036</td><td>3.1%</td><td>6,335.5</td><td>1,971.9</td>
<td>102.32</td><td>2.800%</td><td>11.4317%</td><td>102.57</td><td>2.768%</td><td>626.6</td></tr></table>"""
    RESULT_DUTCH = """<table>
<tr><th>Security</th><th>Issue Number</th><th>Auction Date</th><th>Issue Date</th><th>Maturity Date</th><th>Nominal Coupon</th>
<th>Amounts of Competitive Bids (billion yen)</th><th>Amounts of Bids Accepted (billion yen)</th><th>Price at the Highest Accepted Yield (per 100 yen)</th>
<th>Highest Accepted Yield</th><th>Allotment for Bids at the Highest Accepted Yield</th><th>Weighted Average Price (per 100 yen)</th><th>Yield at the Average Price</th></tr>
<tr><td>5-Year Climate Transition</td><td>6</td><td>11/2/2026</td><td>11/4/2026</td><td>9/20/2031</td><td>2.2%</td><td>959.9</td><td>249.8</td>
<td>100.00</td><td>2.200%</td><td>35.2066%</td><td>-</td><td>-</td></tr></table>"""

    def test_yields(self):
        rows = fetch_jp.parse_yield_csv(self.CSV, SINCE)
        self.assertEqual([r[0] for r in rows], ["2026-11-12", "2026-11-13"])
        self.assertEqual(rows[1][1], 1.663)
        self.assertEqual(rows[1][10], 2.899)       # 10년
        self.assertIsNone(rows[1][15])             # '-' 는 값 없음
        self.assertEqual(len(rows[1]), len(fetch_jp.TENORS) + 1)

    def test_classify(self):
        self.assertEqual(fetch_jp.classify("10-year(384)"), ("JGB", "10-Year"))
        self.assertEqual(fetch_jp.classify("10-year Inflation-Indexed Bonds(31)"), ("JGBi", "10-Year"))
        self.assertEqual(fetch_jp.classify("5-Year Climate Transition"), ("GX", "5-Year"))
        self.assertEqual(fetch_jp.classify("40-year"), ("JGB", "40-Year"))

    def test_calendar(self):
        page = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/2611e.htm"
        got = fetch_jp.parse_calendar(self.CALENDAR, page)
        self.assertEqual([(e["date"], e["issue"]) for e in got], [
            ("2026-11-05", "10-year(384)"),
            ("2026-11-16", "10-year Inflation-Indexed Bonds(31)"),
            ("2026-11-18", "20-year"),
            ("2026-05-07", "5-year Japan Climate Transition Bonds(6)"),
        ])
        self.assertEqual(got[0]["result_url"],
                         "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/eresul/eresul20261105.htm")
        self.assertEqual(got[1]["result_url"],
                         "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/eresul/eresul20261116.htm")
        self.assertIsNone(got[2]["result_url"])

    def test_result(self):
        row = fetch_jp.parse_result(self.RESULT)
        self.assertEqual((row["auction_date"], row["issue_date"], row["maturity"]),
                         ("2026-11-05", "2026-11-06", "2036-09-20"))
        self.assertEqual((row["type"], row["term"], row["coupon"]), ("JGB", "10-Year", 3.1))
        self.assertEqual((row["offering_amt"], row["high_rate"], row["bid_to_cover"]), (1971.9e9, 2.8, 3.21))

    def test_result_yield_auction(self):
        row = fetch_jp.parse_result(self.RESULT_DUTCH)
        self.assertEqual((row["type"], row["term"], row["high_rate"]), ("GX", "5-Year", 2.2))
        self.assertEqual(row["bid_to_cover"], 3.84)

    def test_result_without_table(self):
        self.assertIsNone(fetch_jp.parse_result("<html><body><p>Not yet</p></body></html>"))

    def test_auctions_use_cache_and_mark_upcoming(self):
        """받아 둔 결과는 다시 열지 않고, 결과 링크가 없는 건은 예정으로 싣는다."""
        cached = fetch_jp.parse_result(self.RESULT)
        previous = {"auctions": {"results": [cached]}}
        opened = []

        def fake_fetch(url, **kwargs):
            opened.append(url)
            if url.endswith("2611e.htm"):
                return self.CALENDAR.encode()
            if "eresul20261116" in url:
                return self.RESULT_DUTCH.replace("11/2/2026", "11/16/2026").replace(
                    "5-Year Climate Transition", "10-year Inflation-Indexed Bonds").encode()
            raise RuntimeError("없는 페이지")

        original, original_sleep = common.fetch, fetch_jp.time.sleep
        common.fetch, fetch_jp.time.sleep = fake_fetch, lambda s: None
        try:
            errors: list[str] = []
            got = fetch_jp.collect_auctions(TODAY, previous, errors)
        finally:
            common.fetch, fetch_jp.time.sleep = original, original_sleep
        self.assertFalse(any("eresul20261105" in url for url in opened))
        self.assertEqual([r["auction_date"] for r in got["results"]], ["2026-11-16", "2026-11-05"])
        self.assertEqual([(r["auction_date"], r["term"]) for r in got["pending"]], [("2026-11-18", "20-Year")])
        self.assertEqual(got["latest_result"], "2026-11-16")


class EurozoneTest(unittest.TestCase):
    CSV = """KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-11-11,3.3400829714,A,"AAA yield curve - 10-year spot rate, with a comma"
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_10Y,2026-11-12,3.3672459164,A,x
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_3M,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_3M,2026-11-12,2.6357552721,A,x
YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_9M,B,U2,EUR,4F,G_N_A,SV_C_YM,SR_9M,2026-11-12,2.9,A,x
"""

    def test_parse(self):
        rows = fetch_ez.parse_csv(self.CSV, SINCE)
        tenors = fetch_ez.TENORS
        self.assertEqual([r[0] for r in rows], ["2026-11-11", "2026-11-12"])
        last = dict(zip(tenors, rows[1][1:]))
        self.assertEqual((last["3M"], last["10Y"]), (2.636, 3.367))
        self.assertIsNone(last["2Y"])
        self.assertIsNone(dict(zip(tenors, rows[0][1:]))["3M"])


class CommonTest(unittest.TestCase):
    def test_xlsx_with_capital_sheet_name(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml",
                       '<sst xmlns="x"><si><t>Date</t></si><si><r><t>Bu</t></r><r><t>nd</t></r></si></sst>')
            z.writestr("xl/worksheets/Sheet1.xml",
                       '<worksheet xmlns="x"><sheetData>'
                       '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
                       '<row r="2"><c r="A2"><v>46337</v></c><c r="B2"><v>2.5</v></c>'
                       '<c r="C2" t="inlineStr"><is><t>x</t></is></c></row></sheetData></worksheet>')
        self.assertEqual(common.xlsx_sheets(buf.getvalue()),
                         [[["Date", "", "Bund"], ["46337", "2.5", "x"]]])
        self.assertEqual(common.excel_date("46337"), "2026-11-11")
        self.assertIsNone(common.excel_date("12"))

    def test_to_float(self):
        self.assertEqual(common.to_float("6,335.5"), 6335.5)
        self.assertEqual(common.to_float("2.800%"), 2.8)
        self.assertEqual(common.to_float("-0.886797"), -0.886797)
        for blank in ("", "-", ".", "null", "N/A", None):
            self.assertIsNone(common.to_float(blank))

    def test_merge_rows_prefers_new(self):
        old = [["2026-11-10", 1.0], ["2026-11-11", 1.1], ["2025-01-01", 9.9]]
        new = [["2026-11-11", 1.2], ["2026-11-12", 1.3]]
        self.assertEqual(common.merge_rows(old, new, SINCE),
                         [["2026-11-10", 1.0], ["2026-11-11", 1.2], ["2026-11-12", 1.3]])

    def test_policy(self):
        common.check_url("https://home.treasury.gov/resource-center/x")
        for bad in ("https://example.com/data.json", "http://home.treasury.gov/x"):
            with self.assertRaises(common.PolicyError):
                common.check_url(bad)
        with self.assertRaises(common.PolicyError):
            common.fetch("https://internal.example.net/secret")

    def test_redirect_outside_allowlist_is_refused_not_fatal(self):
        handler = common._CheckedRedirect()
        with self.assertRaises(common.RedirectRefused) as caught:
            handler.redirect_request(None, None, 302, "Found", {}, "https://challenge.example.net/?x=1")
        self.assertIn("challenge.example.net", str(caught.exception))
        self.assertNotIsInstance(caught.exception, common.PolicyError)


class CollectTest(unittest.TestCase):
    """한 나라가 실패해도 직전 수집분을 남기고 경고를 적는다."""

    class Fake:
        CODE, NAME = "zz", "시험"
        result: dict | Exception = {}

        @classmethod
        def collect(cls, today, previous):
            if isinstance(cls.result, Exception):
                raise cls.result
            return cls.result

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = common.DATA_DIR
        common.DATA_DIR = Path(self.tmp.name)
        self.now = datetime(2026, 11, 16, 23, 47, tzinfo=timezone.utc)

    def tearDown(self):
        common.DATA_DIR = self.original
        self.tmp.cleanup()

    def read(self):
        return json.loads((Path(self.tmp.name) / "zz.json").read_text(encoding="utf-8"))

    def test_success_then_failure_keeps_previous(self):
        curve = {"title": "t", "tenors": ["10Y"], "rows": [["2026-11-13", 3.0]]}
        auctions = {"source": "s", "latest_result": "2026-11-12", "results": [{"x": 1}], "pending": []}
        self.Fake.result = {"curve": curve, "auctions": auctions, "sources": "출처", "errors": []}
        ok, _ = collect.run_one(self.Fake, self.now)
        self.assertTrue(ok)
        self.assertEqual(self.read()["curve"], curve)

        self.Fake.result = RuntimeError("연결 끊김")
        ok, summary = collect.run_one(self.Fake, self.now)
        self.assertFalse(ok)
        saved = self.read()
        self.assertEqual((saved["curve"], saved["auctions"], saved["sources"]), (curve, auctions, "출처"))
        self.assertTrue(any("연결 끊김" in e for e in saved["errors"]))
        self.assertIn("직전 수집분", summary)

    def test_failed_auctions_keep_previous_ones(self):
        curve = {"title": "t", "tenors": ["10Y"], "rows": [["2026-11-13", 3.0]]}
        auctions = {"source": "s", "latest_result": "2026-11-12", "results": [{"x": 1}], "pending": []}
        self.Fake.result = {"curve": curve, "auctions": auctions, "errors": []}
        collect.run_one(self.Fake, self.now)
        self.Fake.result = {"curve": curve, "auctions": None, "errors": ["입찰: 실패"]}
        ok, _ = collect.run_one(self.Fake, self.now)
        self.assertTrue(ok)
        self.assertEqual(self.read()["auctions"], auctions)

    def test_nothing_written_without_any_curve(self):
        self.Fake.result = RuntimeError("처음부터 실패")
        ok, _ = collect.run_one(self.Fake, self.now)
        self.assertFalse(ok)
        self.assertFalse((Path(self.tmp.name) / "zz.json").exists())

    def test_policy_error_stops_everything(self):
        self.Fake.result = common.PolicyError("허용 목록에 없는 주소")
        with self.assertRaises(common.PolicyError):
            collect.run_one(self.Fake, self.now)


if __name__ == "__main__":
    unittest.main()
