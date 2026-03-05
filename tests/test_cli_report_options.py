import pytest

from fxbias.cli import _resolve_report_weeks


def test_resolve_report_weeks_supports_months_and_defaults():
    assert _resolve_report_weeks(weeks=None, months=None, asof=None) == 4
    assert _resolve_report_weeks(weeks=8, months=None, asof=None) == 8
    assert _resolve_report_weeks(weeks=None, months=3, asof=None) == 13
    assert _resolve_report_weeks(weeks=99, months=3, asof=None) == 13
    assert _resolve_report_weeks(weeks=99, months=3, asof="2026-03-20") == 1


def test_resolve_report_weeks_rejects_invalid_values():
    with pytest.raises(ValueError, match="--weeks must be >= 1"):
        _resolve_report_weeks(weeks=0, months=None, asof=None)

    with pytest.raises(ValueError, match="--months must be >= 1"):
        _resolve_report_weeks(weeks=None, months=0, asof=None)
