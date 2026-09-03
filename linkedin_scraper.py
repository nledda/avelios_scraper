"""
LinkedIn Sales Navigator Scraper — entry point.

This is a thin facade that re-exports the core classes for backward
compatibility.  All logic lives in the `scraper/`, `config`, `history`,
and `export` modules.
"""

import logging

from scrapers.linkedin.config import CONFIG
from scrapers.linkedin.runner import LinkedInScraper

# ── Logging (kept at top level so the log file path stays the same) ──

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/linkedin_scraper.log'),
    ],
)

# Re-export for backward compatibility
__all__ = ['LinkedInScraper', 'CONFIG']


if __name__ == "__main__":
    from scrapers.linkedin.export import export_to_file

    logger = logging.getLogger(__name__)

    try:
        scraper = LinkedInScraper(CONFIG)
        results = scraper.run()

        if results:
            export_path = export_to_file(results, CONFIG)

            if export_path:
                print("\n" + "=" * 60)
                print("✓ ERFOLGREICH ABGESCHLOSSEN")
                print(f"Datei: {export_path}")
                print(f"Leads: {len(results)}")
                print("=" * 60)
            else:
                print("\n⚠ Scraping erfolgreich, aber Export fehlgeschlagen")
        else:
            print("\n⚠ Keine Leads gesammelt")

    except Exception as e:
        logger.error(f"Programmfehler: {e}", exc_info=True)
        print(f"\n❌ FEHLER: {e}")
