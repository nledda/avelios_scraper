"""Configuration for the Network (Connections) Scraper."""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CONFIG = {
    'EMAIL': os.getenv('LINKEDIN_EMAIL'),
    'PASSWORD': os.getenv('LINKEDIN_PASSWORD'),
    'PROFILES_FILE': 'config/profiles.txt',
    'COOKIE_FILE': 'cookies.json',
    'DATA_DIR': './data/linkedin',
    'OUTPUT_DIR': './output/network',
    'WAIT_SHORT': 3,
    'WAIT_MEDIUM': 5,
    'WAIT_LONG': 10,
    'MAX_RETRIES': 3,
    'PAGE_LOAD_TIMEOUT': 30,
    'MAX_PAGES_PER_PROFILE': 100,
    'MAX_MINUTES': int(os.getenv('MAX_MINUTES', '90')),
    'HEADLESS': os.getenv('HEADLESS', 'False').lower() == 'true',
}


def load_profiles(config):
    """Loads profile URLs from profiles.txt (one URL per line)."""
    path = config['PROFILES_FILE']
    if not os.path.exists(path):
        logger.error(f"{path} nicht gefunden. Bitte Datei mit LinkedIn-Profil-URLs erstellen.")
        return []

    profiles = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                profiles.append(line)

    logger.info(f"{len(profiles)} Profil(e) aus {path} geladen.")
    return profiles
