"""Unit tests for reporting/stats.py."""

import json
import os
import pytest
from datetime import datetime, timedelta

from reporting.stats import (
    create_run_record,
    create_list_stats,
    load_stats,
    save_stats,
    append_run,
)


@pytest.mark.unit
class TestCreateRunRecord:
    """Tests for create_run_record()."""

    def test_required_fields_exist(self):
        record = create_run_record()
        required = [
            "id", "date", "started_at", "finished_at",
            "duration_seconds", "source", "target",
            "total_collected", "total_duplicates",
            "total_pages_scraped", "target_reached",
            "all_lists_exhausted", "lists", "errors_summary",
        ]
        for field in required:
            assert field in record, f"Missing field: {field}"

    def test_default_source_is_script(self):
        record = create_run_record()
        assert record["source"] == "script"

    def test_custom_source(self):
        record = create_run_record(source="notebook")
        assert record["source"] == "notebook"

    def test_finished_at_initially_none(self):
        record = create_run_record()
        assert record["finished_at"] is None

    def test_lists_initially_empty(self):
        record = create_run_record()
        assert record["lists"] == []

    def test_errors_summary_structure(self):
        record = create_run_record()
        summary = record["errors_summary"]
        assert "stale_element" in summary
        assert "timeout" in summary
        assert "session_restart" in summary
        assert "empty_pages" in summary
        assert "other" in summary
        # All should start at 0
        for val in summary.values():
            assert val == 0


@pytest.mark.unit
class TestCreateListStats:
    """Tests for create_list_stats()."""

    def test_structure(self):
        stats = create_list_stats("my_list", 3)
        assert stats["name"] == "my_list"
        assert stats["start_page"] == 3
        assert stats["end_page"] == 3
        assert stats["leads_collected"] == 0
        assert stats["duplicates"] == 0
        assert stats["pages_scraped"] == 0
        assert stats["exhausted"] is False
        assert stats["errors"] == []


@pytest.mark.unit
class TestLoadSaveStats:
    """Tests for load_stats() / save_stats() roundtrip."""

    def test_load_missing_file_returns_empty_runs(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        result = load_stats(path)
        assert result == {"runs": []}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "stats.json")
        stats = {
            "runs": [
                {"id": "20260801_120000", "total_collected": 42}
            ]
        }
        save_stats(stats, path)
        loaded = load_stats(path)
        assert loaded == stats

    def test_save_overwrites(self, tmp_path):
        path = str(tmp_path / "stats.json")
        save_stats({"runs": [{"id": "v1"}]}, path)
        save_stats({"runs": [{"id": "v2"}]}, path)
        loaded = load_stats(path)
        assert len(loaded["runs"]) == 1
        assert loaded["runs"][0]["id"] == "v2"


@pytest.mark.unit
class TestAppendRun:
    """Tests for append_run()."""

    def test_run_gets_finalized(self, tmp_path, monkeypatch):
        path = str(tmp_path / "stats.json")
        record = create_run_record()

        # Patch the health regeneration to avoid importing reporting.health.main
        # which tries to read log files
        monkeypatch.setattr(
            "reporting.stats.load_stats",
            lambda p=None: {"runs": []} if p else {"runs": []},
            raising=False,
        )

        append_run(record, path)

        loaded = load_stats(path)
        assert len(loaded["runs"]) == 1

        finalized = loaded["runs"][0]
        assert finalized["finished_at"] is not None
        assert isinstance(finalized["duration_seconds"], int)
        assert finalized["duration_seconds"] >= 0

    def test_finished_at_set(self, tmp_path):
        path = str(tmp_path / "stats.json")
        record = create_run_record()
        assert record["finished_at"] is None

        append_run(record, path)

        assert record["finished_at"] is not None

    def test_duration_calculated(self, tmp_path):
        path = str(tmp_path / "stats.json")
        record = create_run_record()
        # Manually set started_at to a time in the past
        past = datetime.now() - timedelta(seconds=10)
        record["started_at"] = past.isoformat(timespec="seconds")

        append_run(record, path)

        assert record["duration_seconds"] >= 10

    def test_total_duplicates_summed_from_lists(self, tmp_path):
        path = str(tmp_path / "stats.json")
        record = create_run_record()
        record["lists"] = [
            {"duplicates": 5, "name": "a"},
            {"duplicates": 3, "name": "b"},
        ]

        append_run(record, path)

        assert record["total_duplicates"] == 8
