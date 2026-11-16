"""미국 수집 파싱 테스트. 네트워크는 쓰지 않는다."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
import fetch_us  # noqa: E402

CURVE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns="http://www.w3.org/2005/Atom">
  <entry><content type="application/xml"><m:properties>
    <d:Id m:type="Edm.Int32">356</d:Id>
    <d:NEW_DATE m:type="Edm.DateTime">2026-11-12T00:00:00</d:NEW_DATE>
    <d:BC_1MONTH m:type="Edm.Double">4.11</d:BC_1MONTH>
    <d:BC_10YEAR m:type="Edm.Double">5.12</d:BC_10YEAR>
    <d:BC_30YEAR m:type="Edm.Double">5.44</d:BC_30YEAR>
    <d:BC_30YEARDISPLAY m:type="Edm.Double">5.44</d:BC_30YEARDISPLAY>
  </m:properties></content></entry>
  <entry><content type="application/xml"><m:properties>
    <d:Id m:type="Edm.Int32">357</d:Id>
    <d:NEW_DATE m:type="Edm.DateTime">2026-11-13T00:00:00</d:NEW_DATE>
    <d:BC_1MONTH m:type="Edm.Double">4.10</d:BC_1MONTH>
    <d:BC_1_5MONTH m:type="Edm.Double">4.18</d:BC_1_5MONTH>
    <d:BC_2YEAR m:type="Edm.Double">4.88</d:BC_2YEAR>
    <d:BC_10YEAR m:type="Edm.Double">5.15</d:BC_10YEAR>
    <d:BC_30YEAR m:type="Edm.Double">5.47</d:BC_30YEAR>
  </m:properties></content></entry>
</feed>"""

EMPTY_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>empty</title></feed>"""

FISCAL_BOND = {
    "security_type": "Bond", "security_term": "29-Year 10-Month",
    "auction_date": "2026-10-08", "issue_date": "2026-10-15", "maturity_date": "2056-08-15",
    "offering_amt": "22000000000", "high_yield": "5.6180", "high_discnt_rate": "null",
    "high_discnt_margin": "null", "int_rate": "5.125000", "bid_to_cover_ratio": "2.540000",
    "reopening": "Yes", "inflation_index_security": "No", "floating_rate": "No",
    "cash_management_bill_cmb": "No",
}
FISCAL_BILL = {
    "security_type": "Bill", "security_term": "4-Week",
    "auction_date": "2026-10-15", "issue_date": "2026-10-20", "maturity_date": "2026-11-17",
    "offering_amt": "110000000000", "high_yield": "null", "high_discnt_rate": "4.000000",
    "high_discnt_margin": "null", "int_rate": "null", "bid_to_cover_ratio": "2.560000",
    "reopening": "Yes", "inflation_index_security": "No", "floating_rate": "No",
    "cash_management_bill_cmb": "No",
}
FISCAL_TIPS_PENDING = {
    "security_type": "Note", "security_term": "5-Year",
    "auction_date": "2026-10-22", "issue_date": "2026-10-30", "maturity_date": "2031-10-15",
    "offering_amt": "26000000000", "high_yield": "null", "high_discnt_rate": "null",
    "high_discnt_margin": "null", "int_rate": "null", "bid_to_cover_ratio": "null",
    "reopening": "No", "inflation_index_security": "Yes", "floating_rate": "No",
    "cash_management_bill_cmb": "No",
}
# TreasuryDirect 실제 응답에서 옮긴 항목 (2026-11-12 입찰 4주물)
TD_BILL = {
    "securityType": "Bill", "securityTerm": "4-Week",
    "competitiveAuctionCloseDate": "2026-11-12T00:00:00", "issueDate": "2026-11-17T00:00:00",
    "maturityDate": "2026-12-15T00:00:00", "offeringAmount": "115000000000",
    "highYield": "", "highRate": "3.955", "highDiscountMargin": "",
    "interestRate": "", "bidToCoverRatio": "2.94", "reopening": "Yes",
    "inflationProtected": "", "floatingRate": "", "cashManagementBill": "No",
}
TD_UPCOMING = {
    "securityType": "Bill", "securityTerm": "13-Week",
    "competitiveAuctionCloseDate": "2026-11-16T00:00:00", "issueDate": "2026-11-19T00:00:00",
    "maturityDate": "2027-02-18T00:00:00", "offeringAmount": "95000000000",
    "highYield": "", "highRate": "", "highDiscountMargin": "",
    "interestRate": "", "bidToCoverRatio": "", "reopening": "Yes",
    "inflationProtected": "", "floatingRate": "", "cashManagementBill": "No",
}


class CurveTest(unittest.TestCase):
    def test_parse(self):
        rows = fetch_us.parse_curve(CURVE_XML)
        self.assertEqual([r[0] for r in rows], ["2026-11-12", "2026-11-13"])
        tenors = [label for label, _ in fetch_us.TENORS]
        last = dict(zip(tenors, rows[1][1:]))
        self.assertEqual(last["1M"], 4.10)
        self.assertEqual(last["1.5M"], 4.18)
        self.assertEqual(last["10Y"], 5.15)
        self.assertEqual(last["30Y"], 5.47)
        self.assertIsNone(last["20Y"])          # 피드에 없는 만기는 비워 둔다
        self.assertEqual(len(rows[1]), len(tenors) + 1)

    def test_empty_feed(self):
        self.assertEqual(fetch_us.parse_curve(EMPTY_FEED), [])

    def test_months_back(self):
        self.assertEqual(fetch_us.months_back(date(2026, 2, 3), 4),
                         ["202511", "202512", "202601", "202602"])


class AuctionTest(unittest.TestCase):
    def test_fiscal_bond(self):
        row = fetch_us.normalize(FISCAL_BOND, fetch_us.FISCAL_KEYS)
        self.assertEqual(row["type"], "Bond")
        self.assertFalse(row["bill"])
        self.assertEqual((row["high_rate"], row["rate_kind"]), (5.618, "yield"))
        self.assertEqual(row["offering_amt"], 22e9)
        self.assertEqual(row["coupon"], 5.125)
        self.assertEqual(row["maturity"], "2056-08-15")
        self.assertEqual(row["tag"], "리오픈")

    def test_fiscal_bill_uses_discount_rate(self):
        row = fetch_us.normalize(FISCAL_BILL, fetch_us.FISCAL_KEYS)
        self.assertEqual((row["high_rate"], row["rate_kind"]), (4.0, "discount"))
        self.assertTrue(row["bill"])
        self.assertIsNone(row["coupon"])

    def test_tips_without_result_is_pending(self):
        row = fetch_us.normalize(FISCAL_TIPS_PENDING, fetch_us.FISCAL_KEYS)
        self.assertEqual(row["type"], "TIPS")
        self.assertEqual(row["tag"], "신규")
        self.assertFalse(common.has_result(row))

    def test_treasurydirect_result(self):
        row = fetch_us.normalize(TD_BILL, fetch_us.TD_KEYS)
        self.assertEqual(row["auction_date"], "2026-11-12")
        self.assertEqual(row["maturity"], "2026-12-15")
        self.assertEqual((row["high_rate"], row["rate_kind"]), (3.955, "discount"))
        self.assertEqual(row["bid_to_cover"], 2.94)
        self.assertEqual(row["offering_amt"], 115e9)

    def test_treasurydirect_upcoming_is_pending(self):
        row = fetch_us.normalize(TD_UPCOMING, fetch_us.TD_KEYS)
        self.assertEqual(row["auction_date"], "2026-11-16")
        self.assertFalse(common.has_result(row))

    def test_missing_keys_are_dropped(self):
        self.assertIsNone(fetch_us.normalize({"foo": "bar"}, fetch_us.TD_KEYS))

    def test_split_and_dedupe(self):
        rows = [fetch_us.normalize(x, fetch_us.FISCAL_KEYS)
                for x in (FISCAL_BOND, FISCAL_BILL, FISCAL_BILL, FISCAL_TIPS_PENDING)]
        results, pending = common.split_auctions(rows, date(2026, 11, 16))
        self.assertEqual([r["auction_date"] for r in results], ["2026-10-15", "2026-10-08"])
        self.assertEqual([r["type"] for r in pending], ["TIPS"])
        self.assertEqual(common.latest_result(rows), "2026-10-15")

    def test_old_rows_are_hidden(self):
        rows = [fetch_us.normalize(x, fetch_us.FISCAL_KEYS) for x in (FISCAL_BOND, FISCAL_TIPS_PENDING)]
        results, pending = common.split_auctions(rows, date(2027, 3, 1))
        self.assertEqual((results, pending), ([], []))


if __name__ == "__main__":
    unittest.main()
