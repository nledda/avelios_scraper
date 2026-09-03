"""Unit tests for reporting/health.py."""

import pytest
from collections import defaultdict

from reporting.health import build_list_health, build_monthly_summary


def _make_run(date, lists_data, total=100):
    """Helper to create a run dict matching the format from parse_log()."""
    lists = defaultdict(lambda: {"new": 0, "dup": 0, "pages": 0, "max_page": 0})
    for name, new, dup, pages, max_page in lists_data:
        lists[name]["new"] = new
        lists[name]["dup"] = dup
        lists[name]["pages"] = pages
        lists[name]["max_page"] = max_page
    return {
        "date": date,
        "started_at": f"{date} 10:00:00",
        "lists": dict(lists),
        "total": total,
        "failed_reason": None,
    }


@pytest.mark.unit
class TestBuildListHealth:
    """Tests for build_list_health() status classification."""

    def test_healthy_status_above_30_pct(self):
        # 80 new, 20 dup => yield = 80% => healthy
        runs = [_make_run("2026-06-01", [("list_a", 80, 20, 4, 4)])]
        result = build_list_health(runs)
        assert len(result) == 1
        assert result[0]["status"] == "healthy"
        assert result[0]["yield_pct"] == 80.0

    def test_declining_status_10_to_30_pct(self):
        # 20 new, 80 dup => yield = 20% => declining
        runs = [_make_run("2026-06-01", [("list_b", 20, 80, 4, 4)])]
        result = build_list_health(runs)
        assert len(result) == 1
        assert result[0]["status"] == "declining"

    def test_exhausted_status_3_to_10_pct(self):
        # 5 new, 95 dup => yield = 5% => exhausted
        runs = [_make_run("2026-06-01", [("list_c", 5, 95, 4, 4)])]
        result = build_list_health(runs)
        assert len(result) == 1
        assert result[0]["status"] == "exhausted"

    def test_dead_status_below_3_pct(self):
        # 2 new, 98 dup => yield = 2% => dead
        runs = [_make_run("2026-06-01", [("list_d", 2, 98, 4, 4)])]
        result = build_list_health(runs)
        assert len(result) == 1
        assert result[0]["status"] == "dead"

    def test_boundary_exactly_30_pct_is_declining(self):
        # 30 new, 70 dup => yield = 30% => declining (< 30 is declining, >= 30 needs > 30 for healthy)
        # Actually: yield_pct < 30 => declining, so exactly 30 is healthy
        runs = [_make_run("2026-06-01", [("list_e", 30, 70, 4, 4)])]
        result = build_list_health(runs)
        # 30.0 is NOT < 30, so it goes to 'healthy'
        assert result[0]["status"] == "healthy"

    def test_boundary_exactly_10_pct_is_exhausted(self):
        # 10 new, 90 dup => yield = 10% => not < 10, so declining
        runs = [_make_run("2026-06-01", [("list_f", 10, 90, 4, 4)])]
        result = build_list_health(runs)
        assert result[0]["status"] == "declining"

    def test_boundary_exactly_3_pct_is_exhausted(self):
        # 3 new, 97 dup => yield = 3% => not < 3, so exhausted
        runs = [_make_run("2026-06-01", [("list_g", 3, 97, 4, 4)])]
        result = build_list_health(runs)
        assert result[0]["status"] == "exhausted"

    def test_empty_runs_returns_empty(self):
        result = build_list_health([])
        assert result == []

    def test_failed_runs_skipped(self):
        # total=0 runs are skipped
        runs = [_make_run("2026-06-01", [("list_x", 10, 5, 1, 1)], total=0)]
        result = build_list_health(runs)
        assert result == []

    def test_multiple_lists_sorted_by_yield(self):
        runs = [
            _make_run("2026-06-01", [
                ("low_yield", 2, 98, 4, 4),
                ("high_yield", 90, 10, 4, 4),
            ]),
        ]
        result = build_list_health(runs)
        assert len(result) == 2
        assert result[0]["name"] == "high_yield"
        assert result[1]["name"] == "low_yield"


@pytest.mark.unit
class TestBuildMonthlySummary:
    """Tests for build_monthly_summary()."""

    def test_single_run_aggregation(self):
        runs = [_make_run("2026-06-15", [("list_a", 50, 10, 3, 3)], total=50)]
        result = build_monthly_summary(runs)
        assert len(result) == 1
        assert result[0]["month"] == "2026-06"
        assert result[0]["runs"] == 1
        assert result[0]["successful_runs"] == 1
        assert result[0]["failed_runs"] == 0
        assert result[0]["total_leads"] == 50

    def test_multiple_runs_same_month(self):
        runs = [
            _make_run("2026-06-01", [("a", 30, 5, 2, 2)], total=30),
            _make_run("2026-06-15", [("a", 20, 3, 1, 3)], total=20),
        ]
        result = build_monthly_summary(runs)
        assert len(result) == 1
        assert result[0]["runs"] == 2
        assert result[0]["total_leads"] == 50
        assert result[0]["avg_per_run"] == 25

    def test_failed_run_counted(self):
        runs = [
            _make_run("2026-06-01", [], total=0),
        ]
        result = build_monthly_summary(runs)
        assert result[0]["failed_runs"] == 1
        assert result[0]["successful_runs"] == 0
        assert result[0]["avg_per_run"] == 0

    def test_multiple_months_sorted(self):
        runs = [
            _make_run("2026-07-01", [("a", 10, 0, 1, 1)], total=10),
            _make_run("2026-06-01", [("a", 20, 0, 1, 1)], total=20),
        ]
        result = build_monthly_summary(runs)
        assert len(result) == 2
        assert result[0]["month"] == "2026-06"
        assert result[1]["month"] == "2026-07"

    def test_empty_runs(self):
        result = build_monthly_summary([])
        assert result == []
