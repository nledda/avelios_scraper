"""Unit tests for scrapers/linkedin/config.py."""

import json
import os
import pytest

from scrapers.linkedin.config import load_lists


@pytest.mark.unit
class TestLoadLists:
    """Tests for load_lists()."""

    def test_with_existing_valid_lists_file(self, sample_config, tmp_path):
        lists_data = [
            {"name": "list_a", "url": "https://linkedin.com/search/1", "pages_per_run": 5},
            {"name": "list_b", "url": "https://linkedin.com/search/2", "pages_per_run": 3},
        ]
        lists_file = sample_config["LISTS_FILE"]
        with open(lists_file, "w", encoding="utf-8") as f:
            json.dump(lists_data, f)

        result = load_lists(sample_config)
        assert len(result) == 2
        assert result[0]["name"] == "list_a"
        assert result[1]["name"] == "list_b"

    def test_with_missing_file_falls_back_to_search_id(self, sample_config):
        # Ensure the lists file doesn't exist
        if os.path.exists(sample_config["LISTS_FILE"]):
            os.remove(sample_config["LISTS_FILE"])

        result = load_lists(sample_config)
        assert len(result) == 1
        assert result[0]["name"] == "default"
        assert result[0]["url"] == sample_config["SEARCH_ID"]
        assert result[0]["pages_per_run"] == sample_config["MAX_PAGES"]

    def test_with_invalid_json_falls_back(self, sample_config):
        lists_file = sample_config["LISTS_FILE"]
        with open(lists_file, "w", encoding="utf-8") as f:
            f.write("this is not valid JSON {{{")

        result = load_lists(sample_config)
        # Should fall back to single-list mode
        assert len(result) == 1
        assert result[0]["name"] == "default"
        assert result[0]["url"] == sample_config["SEARCH_ID"]

    def test_with_empty_list(self, sample_config):
        lists_file = sample_config["LISTS_FILE"]
        with open(lists_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        result = load_lists(sample_config)
        # An empty list is valid JSON, so it should be returned as-is
        assert result == []

    def test_single_list_entry(self, sample_config):
        lists_data = [{"name": "only_list", "url": "https://linkedin.com/search/99", "pages_per_run": 10}]
        with open(sample_config["LISTS_FILE"], "w", encoding="utf-8") as f:
            json.dump(lists_data, f)

        result = load_lists(sample_config)
        assert len(result) == 1
        assert result[0]["name"] == "only_list"
