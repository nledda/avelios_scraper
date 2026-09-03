"""Centralized configuration for LinkedIn Scraper."""

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CONFIG = {
    'TARGET': 1200,
    'EMAIL': os.getenv('LINKEDIN_EMAIL'),
    'PASSWORD': os.getenv('LINKEDIN_PASSWORD'),
    # Fallback used only when config/lists.json is absent.
    # Set LINKEDIN_SEARCH_ID in .env to your own Sales Navigator saved search.
    'SEARCH_ID': os.getenv(
        'LINKEDIN_SEARCH_ID',
        'https://www.linkedin.com/sales/search/people?savedSearchId=0000000000'
        '&viewAllFilters=true',
    ),
    'LISTS_FILE': 'config/lists.json',
    'COOKIE_FILE': 'cookies.json',
    'HISTORY_FILE': 'scraped_history.txt',
    'DATA_DIR': './data/linkedin',
    'OUTPUT_DIR': './output/linkedin',
    'WAIT_SHORT': 3,
    'WAIT_MEDIUM': 5,
    'WAIT_LONG': 10,
    'MAX_RETRIES': 3,
    'PAGE_LOAD_TIMEOUT': 30,
    'MAX_PAGES': 100,
    'MAX_MINUTES': int(os.getenv('MAX_MINUTES', '90')),
    'HEADLESS': os.getenv('HEADLESS', 'False').lower() == 'true',
    'NTFY_TOPIC': os.getenv('NTFY_TOPIC', ''),
}


def load_lists(config):
    """Loads lists.json; falls back to single-list mode using SEARCH_ID."""
    lists_path = config['LISTS_FILE']
    if os.path.exists(lists_path):
        try:
            with open(lists_path, 'r', encoding='utf-8') as f:
                lists = json.load(f)
            logger.info(f"{len(lists)} Liste(n) aus {lists_path} geladen.")
            return lists
        except Exception as e:
            logger.warning(f"Konnte {lists_path} nicht laden: {e}. Verwende Fallback.")
    else:
        logger.warning(f"{lists_path} nicht gefunden. Verwende SEARCH_ID als Fallback-Liste.")

    return [{
        "name": "default",
        "url": config['SEARCH_ID'],
        "pages_per_run": config['MAX_PAGES'],
    }]
