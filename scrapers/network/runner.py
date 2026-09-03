"""Main orchestration for the Network (Connections) Scraper."""

import logging
import os
import time
from datetime import datetime, timedelta

from scrapers.linkedin.browser import Browser
from scrapers.network.navigator import Navigator, SessionBlockedError
from scrapers.network.extractor import ConnectionExtractor
from scrapers.network.export import export_to_file

logger = logging.getLogger(__name__)


class NetworkScraper:
    """Scrapes connections/contacts for given LinkedIn profile URLs."""

    def __init__(self, config):
        self.config = config
        os.makedirs(config['OUTPUT_DIR'], exist_ok=True)
        self.browser = Browser(config)
        self.results = {}  # profile_name -> [connections]

    def run(self, profile_urls):
        """Runs the scraper for all given profile URLs.

        Args:
            profile_urls: List of LinkedIn profile URLs.

        Returns:
            dict: Mapping profile_name -> list of connection dicts.
        """
        if not profile_urls:
            logger.error("Keine Profil-URLs angegeben.")
            return {}

        deadline = datetime.now() + timedelta(minutes=self.config['MAX_MINUTES'])

        try:
            self.browser.prepare()
            navigator = Navigator(self.browser)

            # Verify we're actually logged in before proceeding
            if not navigator.verify_logged_in():
                logger.error("Login-Verifizierung fehlgeschlagen.")
                return {}

            for i, url in enumerate(profile_urls, 1):
                if datetime.now() >= deadline:
                    logger.warning("Zeitlimit erreicht, breche ab.")
                    break

                logger.info(f"\n{'=' * 60}")
                logger.info(f"Profil {i}/{len(profile_urls)}: {url}")
                logger.info(f"{'=' * 60}")

                try:
                    profile_connections = self._scrape_profile(
                        url, navigator, deadline
                    )
                    if profile_connections:
                        profile_name = profile_connections[0].get(
                            'source_profile', url
                        )
                        self.results[profile_name] = profile_connections

                        filepath = export_to_file(
                            profile_connections, profile_name, self.config
                        )
                        if filepath:
                            logger.info(f"Profil abgeschlossen: {len(profile_connections)} Kontakte")

                except SessionBlockedError as e:
                    logger.error(f"Session blockiert: {e}")
                    if not self._try_recover():
                        break
                    navigator = Navigator(self.browser)

                except Exception as e:
                    logger.error(f"Fehler bei Profil {url}: {e}")

                self.browser.smart_wait(self.config['WAIT_LONG'])

        except KeyboardInterrupt:
            logger.info("Abbruch durch Benutzer.")
        finally:
            self.browser.save_cookies()
            self.browser.quit()

        return self.results

    def _scrape_profile(self, profile_url, navigator, deadline):
        """Scrapes all visible connections for a single profile.

        Returns:
            list[dict]: Collected connections.
        """
        # Get profile name before navigating away from the profile page
        # (get_connections_url will navigate to the profile first)
        connections_url = navigator.get_connections_url(profile_url)
        if not connections_url:
            logger.warning(f"Keine Kontakte sichtbar für {profile_url}")
            return []

        # Extract profile name from connectionOf filter in URL or from page
        profile_name = self._get_profile_name_from_url(connections_url, profile_url)

        total = navigator.get_total_results()
        if total:
            logger.info(f"Geschätzte Kontakte: {total}")

        all_connections = []
        empty_pages = 0
        page = 1
        max_pages = self.config['MAX_PAGES_PER_PROFILE']

        while page <= max_pages:
            if datetime.now() >= deadline:
                logger.warning("Zeitlimit erreicht.")
                break

            loaded = navigator.load_connections_page(connections_url, page)
            if not loaded:
                empty_pages += 1
                if empty_pages >= 3:
                    logger.info("3 leere Seiten, Profil erschöpft.")
                    break
                page += 1
                continue

            extractor = ConnectionExtractor(self.browser.driver)
            page_connections = extractor.extract_connections()

            if not page_connections:
                empty_pages += 1
                if empty_pages >= 3:
                    logger.info("3 leere Seiten, Profil erschöpft.")
                    break
            else:
                empty_pages = 0
                # Tag each connection with the source profile
                for conn in page_connections:
                    conn['source_profile'] = profile_name

                all_connections.extend(page_connections)
                logger.info(
                    f"Seite {page}: {len(page_connections)} Kontakte "
                    f"(gesamt: {len(all_connections)})"
                )

            if not navigator.has_next_page():
                logger.info("Letzte Seite erreicht.")
                break

            page += 1
            self.browser.smart_wait(self.config['WAIT_SHORT'])

        return all_connections

    def _get_profile_name_from_url(self, connections_url, profile_url):
        """Extracts the profile name from the profile URL slug."""
        import re
        import urllib.parse

        # Try extracting from the profile URL slug (e.g. /in/nico-ledda/)
        match = re.search(r'/in/([^/?]+)', profile_url)
        if match:
            slug = urllib.parse.unquote(match.group(1))
            # Convert slug to name: "nico-ledda" -> "Nico Ledda"
            name = slug.replace('-', ' ').title()
            # Remove trailing numbers that LinkedIn adds for duplicate slugs
            name = re.sub(r'\s+\d+$', '', name)
            return name

        return "Unbekannt"

    def _try_recover(self):
        """Attempts to recover from a blocked session."""
        try:
            self.browser.restart()
            return True
        except Exception as e:
            logger.error(f"Recovery fehlgeschlagen: {e}")
            return False
