"""
Network Scraper — entry point.

Scrapes connections/contacts from LinkedIn profiles to identify
potential intro paths and company mappings.

Usage:
    1. Add LinkedIn profile URLs to profiles.txt (one per line)
    2. Run: python network_scraper.py
"""

import logging
import sys

from scrapers.network.config import CONFIG, load_profiles
from scrapers.network.runner import NetworkScraper
from scrapers.network.export import export_all

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/network_scraper.log'),
    ],
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    profiles = load_profiles(CONFIG)

    if not profiles:
        print("\nKeine Profile gefunden.")
        print("Bitte profiles.txt erstellen mit LinkedIn-URLs (eine pro Zeile):")
        print("  https://www.linkedin.com/in/beispiel-profil/")
        sys.exit(1)

    print(f"\n{len(profiles)} Profil(e) geladen. Starte Scraper...\n")

    try:
        scraper = NetworkScraper(CONFIG)
        results = scraper.run(profiles)

        if results:
            total = sum(len(conns) for conns in results.values())
            overview_path = export_all(results, CONFIG)

            print("\n" + "=" * 60)
            print("ERFOLGREICH ABGESCHLOSSEN")
            print(f"Profile: {len(results)}")
            print(f"Kontakte gesamt: {total}")
            if overview_path:
                print(f"Gesamt-Datei: {overview_path}")
            print("=" * 60)
        else:
            print("\nKeine Kontakte gesammelt.")

    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        print(f"\nFEHLER: {e}")
