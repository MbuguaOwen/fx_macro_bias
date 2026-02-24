import unittest

import pandas as pd

from fxbias.scoring import conviction_from_score
from fxbias.timeseries import (
    age_days,
    last_report_on_or_before,
    last_value_on_or_before,
    stale_flag,
)


class TestTimeseriesHelpers(unittest.TestCase):
    def test_last_value_on_or_before(self):
        s = pd.Series(
            [1.0, 2.0, 3.0],
            index=pd.to_datetime(["2026-02-01", "2026-02-08", "2026-02-15"]),
        )
        v, d = last_value_on_or_before(s, "2026-02-10")
        self.assertEqual(v, 2.0)
        self.assertEqual(pd.Timestamp("2026-02-08"), d)

        v2, d2 = last_value_on_or_before(s, "2026-01-01")
        self.assertIsNone(v2)
        self.assertIsNone(d2)

    def test_cot_eligibility_selection(self):
        df = pd.DataFrame(
            {
                "report_date": pd.to_datetime(["2026-02-03", "2026-02-10", "2026-02-17"]),
                "release_dt": pd.to_datetime(
                    ["2026-02-06 23:59:59Z", "2026-02-13 23:59:59Z", "2026-02-20 23:59:59Z"],
                    utc=True,
                ),
                "value": [10, 20, 30],
            }
        )
        row, report_date = last_report_on_or_before(df, "2026-02-19")
        self.assertIsNotNone(row)
        self.assertEqual(20, row["value"])
        self.assertEqual(pd.Timestamp("2026-02-10"), report_date)

        row2, report_date2 = last_report_on_or_before(df, "2026-02-20")
        self.assertEqual(30, row2["value"])
        self.assertEqual(pd.Timestamp("2026-02-17"), report_date2)

    def test_staleness_computation(self):
        self.assertEqual(7, age_days("2026-02-20", "2026-02-13"))
        self.assertTrue(stale_flag("2026-02-20", "2026-02-13", 5))
        self.assertFalse(stale_flag("2026-02-20", "2026-02-13", 10))
        self.assertIsNone(stale_flag("2026-02-20", None, 10))


class TestConviction(unittest.TestCase):
    def test_conviction_mapping(self):
        cfg = {
            "neutral_threshold": 0.15,
            "bands": {"weak": 0.20, "moderate": 0.45, "strong": 0.70, "extreme": 1.01},
        }
        self.assertEqual("NONE", conviction_from_score(0.10, cfg))
        self.assertEqual("WEAK", conviction_from_score(0.17, cfg))
        self.assertEqual("MODERATE", conviction_from_score(-0.30, cfg))
        self.assertEqual("STRONG", conviction_from_score(0.60, cfg))
        self.assertEqual("EXTREME", conviction_from_score(-0.90, cfg))


class TestRiskStalenessBehavior(unittest.TestCase):
    def test_dxy_stale_disables_usd_tilt(self):
        # We unit-test the scoring behavior (pillar_risk) directly.
        from fxbias.engine import MacroBiasEngine

        cfg = {
            "cache_dir": ".cache",
            "weights": {"rates": 0.45, "growth": 0.20, "risk": 0.15, "positioning": 0.20},
            "stooq": {"risk": {"spx": "^spx"}},
            "fred": {"risk": {"vix": "VIXCLS", "dxy": "DTWEXBGS"}},
            "cftc": {},
            "growth": {"mode": "proxy"},
            "thresholds": {"bias_threshold": 0.20},
            "conviction": {},
            "staleness": {"days": {"risk": 5}},
        }
        engine = MacroBiasEngine(cfg)

        # DXY stale => usd_bid=None => USD tilt not applied.
        regime = {
            "risk_on": True,
            "usd_bid": None,
            "dxy_stale": True,
            "obs_date": "2026-02-13",
        }
        # For USDJPY, risk_on doesn't affect USD leg; only USD tilt would.
        r = engine.pillar_risk(base="USD", quote="JPY", regime=regime, asof="2026-02-20")
        self.assertIsNotNone(r.score)
        # With usd_bid=None, USD tilt adds 0, haven (JPY) adds +0.5 in risk-on.
        self.assertAlmostEqual(+0.5, float(r.score), places=6)


if __name__ == "__main__":
    unittest.main()

