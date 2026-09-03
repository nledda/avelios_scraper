"""Shared stats module for LinkedIn Scraper (script + notebook)."""

import json
import os
from datetime import datetime

STATS_FILE = 'data/stats/stats.json'


def load_stats(path=STATS_FILE):
    """Load existing stats from JSON file."""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"runs": []}


def save_stats(stats, path=STATS_FILE):
    """Write stats to JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def create_run_record(source="script"):
    """Create a new run stats record."""
    return {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "started_at": datetime.now().isoformat(timespec='seconds'),
        "finished_at": None,
        "duration_seconds": 0,
        "source": source,
        "target": 0,
        "total_collected": 0,
        "total_duplicates": 0,
        "total_pages_scraped": 0,
        "target_reached": False,
        "all_lists_exhausted": False,
        "lists": [],
        "errors_summary": {
            "stale_element": 0,
            "timeout": 0,
            "session_restart": 0,
            "empty_pages": 0,
            "other": 0,
        }
    }


def create_list_stats(name, start_page):
    """Create a per-list stats dict."""
    return {
        "name": name,
        "leads_collected": 0,
        "duplicates": 0,
        "pages_scraped": 0,
        "start_page": start_page,
        "end_page": start_page,
        "exhausted": False,
        "errors": []
    }


def append_run(run_record, path=STATS_FILE):
    """Finalize and append a run record to the stats file."""
    stats = load_stats(path)
    now = datetime.now()
    run_record["finished_at"] = now.isoformat(timespec='seconds')
    started = datetime.fromisoformat(run_record["started_at"])
    run_record["duration_seconds"] = int((now - started).total_seconds())
    run_record["total_duplicates"] = sum(
        ls["duplicates"] for ls in run_record["lists"]
    )
    stats["runs"].append(run_record)
    save_stats(stats, path)

    # Regenerate list health analytics
    try:
        from reporting.health import main as generate_health
        generate_health()
    except Exception:
        pass  # non-critical
