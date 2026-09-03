"""End-to-end smoke test — requires LinkedIn credentials.

Only runs when LINKEDIN_EMAIL and LINKEDIN_PASSWORD are set.
Scrapes 1 page and verifies lead extraction works.
"""

import os
import pytest

# Skip entire module if credentials not available
pytestmark = pytest.mark.e2e

HAS_CREDENTIALS = bool(
    os.getenv("LINKEDIN_EMAIL") and os.getenv("LINKEDIN_PASSWORD")
)


@pytest.mark.skipif(not HAS_CREDENTIALS, reason="LinkedIn credentials not set")
class TestLinkedInE2E:
    """Smoke test: login, scrape 1 page, verify leads extracted."""

    def test_linkedin_scraper_one_page(self):
        from scrapers.linkedin.config import CONFIG
        from scrapers.linkedin.runner import LinkedInScraper

        test_config = CONFIG.copy()
        test_config["MAX_PAGES"] = 1
        test_config["TARGET"] = 25
        test_config["MAX_MINUTES"] = 10
        test_config["HEADLESS"] = True

        scraper = LinkedInScraper(test_config)
        results = scraper.run()

        assert results is not None, "Scraper returned None"
        assert len(results) > 0, "No leads extracted from 1 page"

        # Verify lead structure
        lead = results[0]
        assert "vmid" in lead
        assert "full_name" in lead
        assert "company" in lead
        assert lead["full_name"] != "Unknown"
