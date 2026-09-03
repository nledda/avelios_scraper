"""Page navigation, loading, and pagination for Sales Navigator."""

import logging
import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)


class SessionBlockedError(Exception):
    """Raised when LinkedIn is blocking or redirecting the session."""
    pass


class Navigator:
    """Handles page loading, lead counting, and pagination."""

    def __init__(self, browser, extractor):
        self.browser = browser
        self.extractor = extractor

    @property
    def driver(self):
        return self.browser.driver

    def _diagnose_page(self):
        """Check current page for signs of blocking, login redirect, or CAPTCHA."""
        try:
            url = (self.driver.current_url or "").lower()

            # Login redirect — session expired
            if "login" in url or "uas/login" in url or "authwall" in url:
                return "login_redirect"

            # Challenge / CAPTCHA
            if "challenge" in url or "checkpoint" in url:
                return "challenge"

            # Restriction page
            if "restricted" in url or "unavailable" in url:
                return "restricted"

            # Check page content for restriction messages
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text[:2000].lower()
                if any(phrase in page_text for phrase in [
                    "you've reached the", "commercial use limit",
                    "eingeschränkt", "temporarily restricted",
                    "unusual activity", "ungewöhnliche aktivität",
                ]):
                    return "rate_limited"
            except Exception:
                pass

            return "unknown"
        except Exception:
            return "unknown"

    def scrape_page(self, page_num, base_url, config):
        """
        Scrapes a single search results page.

        Returns:
            list: Lead data dicts extracted from the page.
        Raises:
            SessionBlockedError: If LinkedIn is blocking the session globally.
        """
        try:
            if '?' in base_url:
                search_url = f"{base_url}&page={page_num}"
            else:
                search_url = f"{base_url}?page={page_num}"

            logger.info(f"Lade Seite {page_num}...")
            self.driver.get(search_url)
            self.browser.smart_wait(config['WAIT_MEDIUM'])

            self.browser.human_like_scroll()

            # First, try JavaScript to count /sales/lead links (works for both page types: search results and saved lists)
            logger.debug(f"Seite {page_num}: Zähle /sales/lead links mit JavaScript...")
            lead_link_count = self.driver.execute_script("""
                return document.querySelectorAll('a[href*="/sales/lead"]').length;
            """)

            leads = []
            page_loaded = False
            selected_selector = None

            # If we found /sales/lead links via JavaScript, use the direct link approach
            if lead_link_count > 0:
                logger.debug(f"Seite {page_num}: JavaScript fand {lead_link_count} /sales/lead links")
                leads = self.driver.find_elements(By.XPATH, '//a[contains(@href, "/sales/lead")]')
                page_loaded = True
                selected_selector = "/sales/lead links (JavaScript)"
                logger.info(f"Seite {page_num}: {len(leads)} Lead-Container gefunden via Selector: {selected_selector}")
            else:
                # Fallback to artdeco-list selectors for search result pages
                lead_selectors = [
                    (By.XPATH, '//ol[contains(@class, "artdeco-list")]//li[contains(@class, "artdeco-list__item")]'),
                    (By.CSS_SELECTOR, 'ol.artdeco-list li.artdeco-list__item'),
                    (By.XPATH, '//*[@id="search-results-container"]/div/ol/li'),
                ]

                for by_method, selector in lead_selectors:
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((by_method, selector))
                        )
                        potential_leads = self.driver.find_elements(by_method, selector)
                        if potential_leads:
                            leads = potential_leads
                            page_loaded = True
                            selected_selector = selector
                            logger.info(f"Seite {page_num}: {len(leads)} Lead-Container gefunden via Selector: {selector[:100]}")
                            break
                    except TimeoutException:
                        logger.debug(f"Seite {page_num}: Selector nicht gefunden: {selector[:60]}")
                        continue

            # If no leads found with selectors, check if page is loaded but empty
            if not leads:
                page_loaded = self.driver.execute_script("""
                    // Check if page has loaded (by looking for typical LinkedIn elements)
                    var hasPageContent = document.querySelectorAll('[class*="artdeco"], [class*="sales"]').length > 0;
                    var bodyHasText = document.body.innerText.length > 500;
                    return hasPageContent && bodyHasText;
                """)

                if not page_loaded:
                    # Diagnose WHY the page is empty
                    reason = self._diagnose_page()
                    if reason in ("login_redirect", "challenge", "restricted", "rate_limited"):
                        logger.error(f"Session-Problem erkannt: {reason} (URL: {self.driver.current_url})")
                        self.browser.save_debug_info(f"session_{reason}")
                        raise SessionBlockedError(reason)
                    logger.warning(f"Seite {page_num} hat nicht geladen (Timeout)")
                    return []
                else:
                    # Page loaded but no leads — empty search results is OK
                    logger.info(f"Seite {page_num}: Keine Leads gefunden (Seite geladen, aber leer)")
                    return []

            lead_count = len(leads)
            logger.info(f"Seite {page_num}: {lead_count} Leads gefunden")

            if lead_count == 0:
                return []

            page_data = []
            for i in range(1, lead_count + 1):
                data = self.extractor.scrape_lead_with_retry(i)
                if data:
                    page_data.append(data)
                time.sleep(random.uniform(0.5, 1.5))

            logger.info(f"Seite {page_num}: {len(page_data)} Leads erfolgreich gescraped")
            return page_data

        except Exception as e:
            logger.error(f"Fehler beim Scrapen von Seite {page_num}: {e}")
            return []

    def has_next_page(self):
        """Checks whether there is a next page of results."""
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)

            next_button_selectors = [
                (By.CSS_SELECTOR, "button.artdeco-pagination__button--next"),
                (By.CSS_SELECTOR, "button[aria-label='Next']"),
                (By.CSS_SELECTOR, "button[aria-label='Weiter']"),
                (By.XPATH, "//button[contains(@aria-label, 'Next') or contains(@aria-label, 'Weiter')]"),
                (By.XPATH, "//li[contains(@class,'artdeco-pagination__indicator--number') and contains(@class,'active')]/following-sibling::li/button"),
            ]

            for by_method, selector in next_button_selectors:
                try:
                    next_button = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((by_method, selector))
                    )
                    enabled = next_button.is_enabled() and next_button.is_displayed()
                    logger.debug(f"Next-Button gefunden ({selector}): enabled={enabled}")
                    return enabled
                except Exception:
                    continue

            logger.debug("Kein Next-Button gefunden nach allen Selektoren.")
            return False

        except Exception as e:
            logger.debug(f"Fehler bei Next-Page-Check: {e}")
            return False
