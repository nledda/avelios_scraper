"""Extracts connection data from LinkedIn people search results."""

import logging
import re
import time

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class ConnectionExtractor:
    """Extracts name, position, company, and LinkedIn URL from search result cards."""

    def __init__(self, driver):
        self.driver = driver

    def extract_connections(self):
        """Extracts all connection cards visible on the current page.

        Returns:
            list[dict]: Each dict has keys: full_name, first_name, last_name,
                        position, company, linkedin_url.
        """
        connections = []

        # Try legacy selectors first
        cards = self.driver.find_elements(
            By.CSS_SELECTOR,
            'li.reusable-search__result-container'
        )

        if not cards:
            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                'div.entity-result'
            )

        # Fallback: new LinkedIn layout uses LazyColumn with div-only cards
        if not cards:
            cards = self._find_cards_via_profile_links()

        logger.info(f"{len(cards)} Kontakt-Karten auf der Seite gefunden.")

        for i, card in enumerate(cards):
            try:
                contact = self._extract_card(card)
                if contact:
                    connections.append(contact)
            except StaleElementReferenceException:
                logger.debug(f"Karte {i + 1} stale, überspringe.")
            except Exception as e:
                logger.debug(f"Karte {i + 1} nicht extrahierbar: {e}")

        return connections

    def _find_cards_via_profile_links(self):
        """Finds card containers in the new LinkedIn layout by locating
        the LazyColumn and identifying its card-level children."""
        try:
            lazy_col = self.driver.find_element(
                By.CSS_SELECTOR,
                'div[data-component-type="LazyColumn"]'
            )
        except NoSuchElementException:
            return []

        # Navigate to the level where each child is one person card.
        # The LazyColumn has nested wrappers; we traverse until we find a
        # level with multiple children that each contain profile links.
        container = lazy_col
        for _ in range(8):
            children = container.find_elements(By.XPATH, './div')
            if not children:
                break

            # Count children that have profile links
            children_with_links = []
            for child in children:
                links = child.find_elements(
                    By.CSS_SELECTOR, 'a[href*="/in/"]'
                )
                if links:
                    children_with_links.append(child)

            if len(children_with_links) >= 3:
                # This is the card level
                return children_with_links

            # Go deeper into the child that has the most links
            if len(children) == 1:
                container = children[0]
            else:
                # Pick the child with the most profile links
                best = max(children, key=lambda c: len(
                    c.find_elements(By.CSS_SELECTOR, 'a[href*="/in/"]')
                ))
                container = best

        return []

    def _extract_card(self, card):
        """Extracts data from a single search result card."""
        # Name & profile link
        name_elem = None
        linkedin_url = ''

        # Legacy selectors
        link_selectors = [
            'a.app-aware-link span[dir="ltr"] span[aria-hidden="true"]',
            'span.entity-result__title-text a.app-aware-link span[dir="ltr"] span[aria-hidden="true"]',
            'a.app-aware-link span[aria-hidden="true"]',
        ]

        for sel in link_selectors:
            try:
                name_elem = card.find_element(By.CSS_SELECTOR, sel)
                break
            except NoSuchElementException:
                continue

        # New layout fallback: extract from profile links directly
        if not name_elem:
            result = self._extract_card_new_layout(card)
            if result:
                return result
            return None

        full_name = name_elem.text.strip()
        if not full_name or full_name.lower() == 'linkedin member':
            return None

        # Get profile URL from the parent link
        try:
            link_elem = card.find_element(
                By.CSS_SELECTOR,
                'span.entity-result__title-text a.app-aware-link'
            )
            linkedin_url = link_elem.get_attribute('href') or ''
        except NoSuchElementException:
            try:
                link_elem = card.find_element(By.CSS_SELECTOR, 'a.app-aware-link')
                linkedin_url = link_elem.get_attribute('href') or ''
            except NoSuchElementException:
                pass

        linkedin_url = self._clean_url(linkedin_url)

        # Split name
        name_parts = full_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else full_name
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Position / Headline
        position = ''
        headline_selectors = [
            'div.entity-result__primary-subtitle',
            'div.linked-area div.entity-result__primary-subtitle',
            'p.entity-result__summary',
        ]
        for sel in headline_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                position = elem.text.strip()
                break
            except NoSuchElementException:
                continue

        # Extract company from position (usually "Title at Company" or "Title bei Company")
        company = self._extract_company(position)

        return {
            'full_name': full_name,
            'first_name': first_name,
            'last_name': last_name,
            'position': position,
            'company': company,
            'linkedin_url': linkedin_url,
        }

    def _extract_card_new_layout(self, card):
        """Extracts contact data from LinkedIn's new div-based layout.

        The card structure has profile links (a[href*='/in/']) and
        span elements with name, headline, and location text.
        """
        # Find all profile links in this card
        profile_links = card.find_elements(
            By.CSS_SELECTOR, 'a[href*="/in/"]'
        )
        if not profile_links:
            return None

        # The first profile link with text is the person's name link
        full_name = ''
        linkedin_url = ''
        for link in profile_links:
            href = link.get_attribute('href') or ''
            if '/in/' not in href:
                continue
            text = link.text.strip()
            # Skip links that are mutual connection names (shorter, later in DOM)
            if text and not full_name:
                full_name = text
                linkedin_url = href
                break

        if not full_name or full_name.lower() == 'linkedin member':
            return None

        # Take only the first line if multi-line (headline may be concatenated)
        if '\n' in full_name:
            full_name = full_name.split('\n')[0].strip()
        # Clean up name: remove degree indicator like "• 1." that may be appended
        full_name = re.sub(r'\s*•\s*\d+\.?\s*$', '', full_name).strip()

        linkedin_url = self._clean_url(linkedin_url)

        # Split name
        name_parts = full_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else full_name
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Extract headline/position from spans
        # In the new layout, spans contain: degree ("• 1."), headline, location
        position = ''
        spans = card.find_elements(By.TAG_NAME, 'span')
        for span in spans:
            text = span.text.strip()
            if not text or len(text) > 200:
                continue
            # Skip degree indicators, location, mutual connection text
            if re.match(r'^•\s*\d+\.?$', text):
                continue
            if text == full_name:
                continue
            if 'gemeinsame Kontakte' in text or 'mutual connection' in text.lower():
                continue
            if text in ('Nachricht', 'Message', 'Folgen', 'Follow', 'Vernetzen', 'Connect'):
                continue
            # This is likely the headline
            position = text
            break

        company = self._extract_company(position)

        return {
            'full_name': full_name,
            'first_name': first_name,
            'last_name': last_name,
            'position': position,
            'company': company,
            'linkedin_url': linkedin_url,
        }

    def _extract_company(self, headline):
        """Tries to extract the company name from a headline like 'CEO at Acme Corp'."""
        if not headline:
            return ''

        # Common separators: "at", "bei", "@", "|", "-", "·"
        patterns = [
            r'\bat\b\s+(.+)',
            r'\bbei\b\s+(.+)',
            r'@\s*(.+)',
            r'\|\s*(.+)',
            r'\s[-–—]\s+(.+)',
            r'·\s*(.+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, headline, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ''

    @staticmethod
    def _clean_url(url):
        """Cleans up LinkedIn profile URLs, removing query params."""
        if not url:
            return ''
        url = url.split('?')[0].rstrip('/')
        if '/in/' in url:
            return url + '/'
        return url
