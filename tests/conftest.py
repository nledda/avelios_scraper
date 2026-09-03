"""Shared test fixtures."""

import os
import json
import pytest
import tempfile
import shutil


@pytest.fixture
def tmp_dir(tmp_path):
    """Provides a temporary directory that gets cleaned up after the test."""
    return tmp_path


@pytest.fixture
def sample_lead():
    """A realistic lead data dict."""
    return {
        "vmid": "ACwAAAB1234TEST",
        "full_name": "Max Mustermann",
        "first_name": "Max",
        "last_name": "Mustermann",
        "company": "TechStartup GmbH",
        "linkedin_url": "https://www.linkedin.com/in/ACwAAAB1234TEST/",
        "sales_nav_url": "https://www.linkedin.com/sales/lead/ACwAAAB1234TEST",
        "created_date": "2026-08-25",
    }


@pytest.fixture
def sample_config(tmp_path):
    """A minimal LinkedIn scraper config using temp directories."""
    data_dir = tmp_path / "data" / "linkedin"
    data_dir.mkdir(parents=True)
    output_dir = tmp_path / "output" / "linkedin"
    output_dir.mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    return {
        "TARGET": 10,
        "EMAIL": "test@example.com",
        "PASSWORD": "testpass",
        "SEARCH_ID": "https://www.linkedin.com/sales/search/people?savedSearchId=123",
        "LISTS_FILE": str(config_dir / "lists.json"),
        "COOKIE_FILE": "cookies.pkl",
        "HISTORY_FILE": "scraped_history.txt",
        "DATA_DIR": str(data_dir),
        "OUTPUT_DIR": str(output_dir),
        "WAIT_SHORT": 1,
        "WAIT_MEDIUM": 1,
        "WAIT_LONG": 1,
        "MAX_RETRIES": 2,
        "PAGE_LOAD_TIMEOUT": 10,
        "MAX_PAGES": 1,
        "MAX_MINUTES": 5,
        "HEADLESS": True,
        "NTFY_TOPIC": "",
    }


@pytest.fixture
def sample_leads_list():
    """Multiple sample leads for batch operations."""
    return [
        {
            "vmid": f"ACwAAAB{i:04d}TEST",
            "full_name": f"Person {i}",
            "first_name": f"Person",
            "last_name": f"{i}",
            "company": f"Company {i} GmbH",
            "komitee": "",
        }
        for i in range(5)
    ]
