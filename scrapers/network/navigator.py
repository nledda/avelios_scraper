"""Navigates to a profile's connections and handles pagination."""

import logging
import re
import time
import urllib.parse

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


class SessionBlockedError(Exception):
    pass


class Navigator:
    """Handles navigating to connections pages and pagination."""

    def __init__(self, browser):
        self.browser = browser
        self.driver = browser.driver

    def get_connections_url(self, profile_url):
        """Navigates to a profile and extracts the connections search URL.

        LinkedIn's connections link on a profile points to a people search
        filtered by ``connectionOf`` with the profile's URN.

        Returns:
            str: The connections search URL, or None if connections are hidden.
        """
        logger.info(f"Navigiere zu Profil: {profile_url}")
        self.driver.get(profile_url)
        self.browser.smart_wait(self.browser.config['WAIT_LONG'])

        # Check for login redirect
        current = self.driver.current_url.lower()
        if 'login' in current or 'challenge' in current:
            raise SessionBlockedError("Session wurde umgeleitet zum Login.")

        # Wait for profile content to load
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    'h1.text-heading-xlarge, section.artdeco-card, main'
                ))
            )
        except TimeoutException:
            logger.warning("Profil-Seite nicht vollständig geladen.")
            self.browser.save_debug_info("profile_load_timeout")

        self.browser.human_like_scroll()

        # Strategy 1: find connections/Kontakte links by href
        conn_selectors = [
            'a[href*="connectionOf"]',
            'a[href*="/search/results/people/?connectionOf"]',
            'li.text-body-small a[href*="/search/results/people"]',
        ]

        for sel in conn_selectors:
            try:
                links = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for link in links:
                    href = link.get_attribute('href')
                    if href and ('connectionOf' in href or '/search/results/people' in href):
                        logger.info(f"Connections-Link gefunden: {href}")
                        return href
            except Exception:
                continue

        # Strategy 2: find by link text (Kontakte / connections)
        try:
            conn_link = self.driver.find_element(
                By.XPATH,
                '//a[contains(@href, "connectionOf")]'
            )
            href = conn_link.get_attribute('href')
            if href:
                logger.info(f"Connections-Link (XPath) gefunden: {href}")
                return href
        except Exception:
            pass

        # Strategy 3: find all links and check href content
        try:
            all_links = self.driver.find_elements(By.TAG_NAME, 'a')
            for link in all_links:
                try:
                    href = link.get_attribute('href') or ''
                    if 'connectionOf' in href:
                        logger.info(f"Connections-Link (scan) gefunden: {href}")
                        return href
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 4: Build URL from member URN in page source
        urn = self._extract_member_urn()
        if urn:
            connections_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?connectionOf=%5B%22{urn}%22%5D"
                f"&network=%5B%22F%22%2C%22S%22%5D"
                f"&origin=MEMBER_PROFILE_CANNED_SEARCH"
            )
            logger.info(f"Connections-URL aus URN erstellt: {connections_url}")
            return connections_url

        # Debug: save page for analysis
        self.browser.save_debug_info("no_connections_link")
        logger.warning("Konnte keine Connections-URL finden. Kontakte möglicherweise verborgen.")
        return None

    def verify_logged_in(self):
        """Navigates to LinkedIn feed to verify session is active."""
        logger.info("Verifiziere Login-Status...")
        self.driver.get("https://www.linkedin.com/feed/")
        self.browser.smart_wait(self.browser.config['WAIT_MEDIUM'])
        current = self.driver.current_url.lower()
        if 'feed' in current or 'mynetwork' in current:
            logger.info("Session aktiv.")
            return True
        logger.warning(f"Nicht eingeloggt. URL: {self.driver.current_url}")
        return False

    def load_connections_page(self, connections_url, page_num):
        """Loads a specific page of the connections search results.

        Returns:
            bool: True if the page loaded with results.
        """
        separator = '&' if '?' in connections_url else '?'
        page_url = f"{connections_url}{separator}page={page_num}"

        logger.info(f"Lade Kontakte-Seite {page_num}...")
        self.driver.get(page_url)
        self.browser.smart_wait(self.browser.config['WAIT_LONG'])

        # Check for blocking / redirect
        current = self.driver.current_url.lower()
        if 'login' in current or 'challenge' in current:
            raise SessionBlockedError("Session blockiert (Login-Redirect).")

        # LinkedIn sometimes redirects to homepage if search params are rejected
        if current.rstrip('/') == 'https://www.linkedin.com' or 'feed' in current:
            logger.warning(f"Seite {page_num}: Redirect zur Startseite. Suche möglicherweise blockiert.")
            self.browser.save_debug_info(f"search_redirect_page{page_num}")
            return False

        # Scroll first to trigger lazy loading
        self.browser.human_like_scroll()
        self.browser.smart_wait(self.browser.config['WAIT_SHORT'])

        # Wait for results with broad selectors (including new hashed-class layout)
        result_selectors = [
            'div.search-results-container',
            'ul.reusable-search__entity-result-list',
            'li.reusable-search__result-container',
            'div.entity-result',
            'div[data-view-name="search-entity-result-universal-template"]',
            'div.scaffold-layout__main',
            'div[data-component-type="LazyColumn"]',
        ]

        found = False
        for sel in result_selectors:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    logger.info(f"Ergebnisse gefunden mit: {sel} ({len(elems)} Elemente)")
                    found = True
                    break
            except Exception:
                continue

        # Fallback: check if there are profile links on the page
        if not found:
            try:
                profile_links = self.driver.find_elements(
                    By.CSS_SELECTOR, 'a[href*="/in/"]'
                )
                if len(profile_links) >= 3:
                    logger.info(f"Ergebnisse via Profil-Links erkannt ({len(profile_links)} Links)")
                    found = True
            except Exception:
                pass

        if not found:
            reason = self._diagnose_page()
            if reason:
                raise SessionBlockedError(f"Seite blockiert: {reason}")
            # Save debug info to analyze page structure
            self.browser.save_debug_info(f"no_results_page{page_num}")
            logger.info(f"Keine Ergebnisse auf Seite {page_num}.")
            return False

        return True

    def has_next_page(self):
        """Checks if there is a next page button."""
        # Try CSS selectors first
        selectors = [
            'button.artdeco-pagination__button--next:not([disabled])',
            'button[aria-label="Weiter"]:not([disabled])',
            'button[aria-label="Next"]:not([disabled])',
        ]
        for sel in selectors:
            try:
                next_btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                if next_btn.is_displayed():
                    return True
            except Exception:
                continue

        # Fallback: find button by text content "Weiter" or "Next"
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, 'button')
            for btn in buttons:
                text = btn.text.strip()
                if text in ('Weiter', 'Next') and btn.is_displayed() and btn.is_enabled():
                    return True
        except Exception:
            pass

        return False

    def get_total_results(self):
        """Extracts the total number of results from the page header."""
        try:
            header = self.driver.find_element(
                By.CSS_SELECTOR,
                'div.search-results-container h2, '
                'div.pb2 span.t-normal span'
            )
            text = header.text.strip()
            match = re.search(r'([\d.,]+)', text.replace('.', '').replace(',', ''))
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None

    def _extract_profile_id(self, url):
        """Extracts the vanity name or ID from a profile URL."""
        match = re.search(r'linkedin\.com/in/([^/?]+)', url)
        return match.group(1) if match else None

    def _extract_member_urn(self):
        """Tries to extract the member URN from the current page source."""
        try:
            source = self.driver.page_source
            # Pattern: "urn:li:fsd_profile:ACoAA..."
            match = re.search(r'urn:li:fsd_profile:(ACoAA[A-Za-z0-9_-]+)', source)
            if match:
                return match.group(1)
            # Alternative pattern
            match = re.search(r'"publicIdentifier":"[^"]+","trackingId":"[^"]+","entityUrn":"urn:li:fs_miniProfile:(ACoAA[A-Za-z0-9_-]+)"', source)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _diagnose_page(self):
        """Checks for common blocking patterns."""
        try:
            current_url = self.driver.current_url.lower()
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()

            if 'login' in current_url:
                return 'login_redirect'
            if 'challenge' in current_url or 'checkpoint' in current_url:
                return 'challenge'
            if 'restricted' in current_url or 'unavailable' in current_url:
                return 'restricted'
            if any(phrase in page_text for phrase in [
                "you've reached the", "commercial use limit",
                "unusual activity", "ungewöhnliche aktivität",
            ]):
                return 'rate_limit'
        except Exception:
            pass
        return None
