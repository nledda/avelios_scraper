"""Unit tests for scrapers/linkedin/history.py."""

import json
import os
import pytest

from scrapers.linkedin.history import History


@pytest.mark.unit
class TestMakeNameKey:
    """Tests for History.make_name_key() static method."""

    def test_normal_lead(self):
        lead = {"full_name": "Max Mustermann", "company": "TechStartup GmbH"}
        key = History.make_name_key(lead)
        assert key == "max mustermann|techstartup gmbh"

    def test_empty_fields(self):
        lead = {"full_name": "", "company": ""}
        key = History.make_name_key(lead)
        assert key == "|"

    def test_missing_fields(self):
        lead = {}
        key = History.make_name_key(lead)
        assert key == "|"

    def test_whitespace_fields(self):
        lead = {"full_name": "  Anna Schmidt  ", "company": "  ACME  "}
        key = History.make_name_key(lead)
        assert key == "anna schmidt|acme"

    def test_case_insensitive(self):
        lead = {"full_name": "JOHN DOE", "company": "BigCorp"}
        key = History.make_name_key(lead)
        assert key == "john doe|bigcorp"


@pytest.mark.unit
class TestHistoryVMID:
    """Tests for VMID add/check on History class."""

    def test_add_and_check_vmid(self, sample_config):
        history = History(sample_config)
        assert not history.has_vmid("VMID_001")

        history.add_vmid("VMID_001")
        assert history.has_vmid("VMID_001")

    def test_vmid_not_present(self, sample_config):
        history = History(sample_config)
        assert not history.has_vmid("nonexistent")

    def test_multiple_vmids(self, sample_config):
        history = History(sample_config)
        history.add_vmid("VMID_A")
        history.add_vmid("VMID_B")
        assert history.has_vmid("VMID_A")
        assert history.has_vmid("VMID_B")
        assert not history.has_vmid("VMID_C")

    def test_len_reflects_vmids(self, sample_config):
        history = History(sample_config)
        assert len(history) == 0
        history.add_vmid("VMID_X")
        assert len(history) == 1


@pytest.mark.unit
class TestHistoryName:
    """Tests for name-based history."""

    def test_add_and_check_name(self, sample_config):
        history = History(sample_config)
        key = "max mustermann|techstartup gmbh"
        assert not history.has_name(key)

        history.add_name(key)
        assert history.has_name(key)

    def test_name_case_insensitive(self, sample_config):
        history = History(sample_config)
        history.add_name("John Doe|BigCorp")
        # has_name lowercases before checking
        assert history.has_name("JOHN DOE|BIGCORP")
        assert history.has_name("john doe|bigcorp")


@pytest.mark.unit
class TestHistoryDedupDetection:
    """Tests for duplicate detection combining VMID and name."""

    def test_dedup_by_vmid(self, sample_config):
        history = History(sample_config)
        history.add_vmid("VMID_DUP")
        # Second time, should detect as duplicate
        assert history.has_vmid("VMID_DUP")

    def test_dedup_by_name(self, sample_config):
        history = History(sample_config)
        lead = {"full_name": "Max Mustermann", "company": "TechStartup GmbH"}
        name_key = History.make_name_key(lead)
        history.add_name(name_key)
        assert history.has_name(name_key)


@pytest.mark.unit
class TestHistoryFilePersistence:
    """Tests for file persistence using tmp_path."""

    def test_vmid_persisted_to_file(self, sample_config):
        history = History(sample_config)
        history.add_vmid("PERSIST_001")
        history.add_vmid("PERSIST_002")

        # Read the history file directly
        history_path = os.path.join(sample_config['DATA_DIR'], sample_config['HISTORY_FILE'])
        assert os.path.exists(history_path)
        with open(history_path, 'r') as f:
            lines = [l.strip() for l in f if l.strip()]
        assert "PERSIST_001" in lines
        assert "PERSIST_002" in lines

    def test_name_persisted_to_file(self, sample_config):
        history = History(sample_config)
        history.add_name("test name|test company")

        name_path = os.path.join(sample_config['DATA_DIR'], 'name_history.txt')
        assert os.path.exists(name_path)
        with open(name_path, 'r') as f:
            lines = [l.strip() for l in f if l.strip()]
        assert "test name|test company" in lines

    def test_reload_from_file(self, sample_config):
        """Data persists across History instances."""
        h1 = History(sample_config)
        h1.add_vmid("RELOAD_VMID")
        h1.add_name("reload name|reload company")

        # Create new instance from same config
        h2 = History(sample_config)
        assert h2.has_vmid("RELOAD_VMID")
        assert h2.has_name("reload name|reload company")


@pytest.mark.unit
class TestLoadSaveState:
    """Tests for load_state / save_state roundtrip."""

    def test_save_and_load_roundtrip(self, sample_config):
        state = {"current_list": 1, "current_page": 5, "total_scraped": 42}
        History.save_state(sample_config, state)

        loaded = History.load_state(sample_config)
        assert loaded == state

    def test_load_missing_state_returns_empty(self, sample_config):
        loaded = History.load_state(sample_config)
        assert loaded == {}

    def test_save_overwrites_previous(self, sample_config):
        History.save_state(sample_config, {"version": 1})
        History.save_state(sample_config, {"version": 2})

        loaded = History.load_state(sample_config)
        assert loaded == {"version": 2}
