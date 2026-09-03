"""Lead data extraction from Sales Navigator search results."""

import logging
import re
import time
import random
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)

logger = logging.getLogger(__name__)


class LeadExtractor:
    """Extracts lead information from Sales Navigator list items."""

    def __init__(self, browser, config):
        self.browser = browser
        self.config = config

    @property
    def driver(self):
        return self.browser.driver

    def find_element_safe(self, selectors_list, parent=None, timeout=5):
        search_context = parent if parent else self.driver
        for by_method, selector in selectors_list:
            try:
                element = WebDriverWait(search_context, timeout).until(
                    EC.presence_of_element_located((by_method, selector))
                )
                return element
            except (TimeoutException, NoSuchElementException):
                continue
        return None

    def extract_company_name(self, base_xpath, lead_element):
        """Extracts company name using multiple fallback strategies."""
        company = ""
        try:
            # Strategy 1: data-anonymize="company-name"
            try:
                company_elem = self.driver.find_element(
                    By.XPATH, f'{base_xpath}//*[@data-anonymize="company-name"]'
                )
                company = company_elem.text.strip()
                if company:
                    return company
            except NoSuchElementException:
                pass

            # Strategy 2: Company page link
            try:
                company_links = self.driver.find_elements(
                    By.XPATH,
                    f'{base_xpath}//a[contains(@href, "/company/") or contains(@href, "/school/")]',
                )
                if company_links:
                    company = company_links[0].text.strip()
                    if company:
                        return company
            except NoSuchElementException:
                pass

            # Strategy 3: Subtitle area
            try:
                subtitle_selectors = [
                    f'{base_xpath}/div/div/div[2]/div[1]/div[1]/div/div[2]/div[2]',
                    f'{base_xpath}//div[contains(@class, "artdeco-entity-lockup__subtitle")]',
                    f'{base_xpath}//*[@data-anonymize="title"]/parent::*/following-sibling::*',
                ]

                sub_info_elem = None
                for xpath in subtitle_selectors:
                    try:
                        sub_info_elem = self.driver.find_element(By.XPATH, xpath)
                        break
                    except NoSuchElementException:
                        continue

                if sub_info_elem:
                    sub_info_text = sub_info_elem.text.strip()

                    # Try subtracting the title
                    try:
                        title_elem = self.driver.find_element(
                            By.XPATH, f'{base_xpath}//span[@data-anonymize="title"]'
                        )
                        title_text = title_elem.text.strip()

                        if title_text and sub_info_text.startswith(title_text):
                            potential_company = sub_info_text[len(title_text):].strip()
                            clean_pattern = r"^[\s\W]*(at|bei|@|von|for|für|und|and|&|\|-)+[\s\W]*"
                            potential_company = re.sub(clean_pattern, "", potential_company, flags=re.IGNORECASE).strip()

                            if potential_company and len(potential_company) > 2:
                                return potential_company
                    except NoSuchElementException:
                        pass

                    # Strategy 4: Split by separator
                    separators = [" bei ", " at ", " @ ", " von ", " für ", " for ", " - ", " | "]
                    for sep in separators:
                        parts = re.split(re.escape(sep), sub_info_text, maxsplit=1, flags=re.IGNORECASE)
                        if len(parts) > 1:
                            company = parts[-1].strip()
                            if company and len(company) > 2:
                                return company

                    # Strategy 5: Remove known title patterns
                    title_patterns = [
                        r"^((Co-?|Vice |Sr\.? |Senior |Junior |Lead |Chief |Head |Executive |Managing |Interim )?",
                        r"(Founder|Gründer(in)?|Inhaber(in)?|Owner|CEO|CTO|CFO|COO|CIO|MD|Partner|",
                        r"Geschäftsführer(in)?|Board Member|Director|Manager|President|VP|Consultant|",
                        r"Berater(in)?|Entwickler(in)?|Architect|Engineer|Specialist|Officer)\s*([,&/]|und)?\s*)+",
                    ]
                    full_pattern = "".join(title_patterns)
                    match = re.search(full_pattern, sub_info_text, re.IGNORECASE)

                    if match:
                        company = sub_info_text[match.end():].strip()
                        if company and len(company) > 2:
                            return company

                    if sub_info_text and 2 < len(sub_info_text) < 100:
                        return sub_info_text

            except Exception as e:
                logger.debug(f"Strategie 3 fehlgeschlagen: {e}")

        except Exception as e:
            logger.debug(f"Company-Extraction Fehler: {e}")

        return "Unknown"

    def scrape_lead(self, lead_index):
        """Extracts lead information from /sales/lead links using JavaScript (works for all page types)."""
        try:
            # Use JavaScript to extract lead data by index from /sales/lead links
            # This works for both search results pages and saved list pages
            lead_data_js = self.driver.execute_script(f"""
                var leadLinks = document.querySelectorAll('a[href*="/sales/lead"]');
                var leadLink = leadLinks[{lead_index - 1}];

                if (!leadLink) {{
                    return null;
                }}

                var leadURL = leadLink.href;

                // Find the parent container (list item or card)
                var current = leadLink;
                var container = null;
                for (var i = 0; i < 15 && current; i++) {{
                    // Look for a proper card container: li, article, or element with role
                    var tag = current.tagName ? current.tagName.toLowerCase() : '';
                    if (tag === 'li' || tag === 'article' ||
                        current.getAttribute('role') === 'listitem' ||
                        (current.className && current.className.includes('artdeco-list__item'))) {{
                        container = current;
                        break;
                    }}
                    current = current.parentElement;
                }}

                // Fallback: if no semantic container found, walk up to find element with enough text
                if (!container) {{
                    current = leadLink;
                    for (var i = 0; i < 15 && current; i++) {{
                        var text = (current.innerText || current.textContent || '').trim();
                        if (text && text.length > 100) {{
                            container = current;
                            break;
                        }}
                        current = current.parentElement;
                    }}
                }}

                if (!container) {{
                    return null;
                }}

                var fullText = (container.innerText || container.textContent || '').trim();

                // Strategy 1: Use data-anonymize attributes (most reliable)
                var name = '';
                var company = '';

                var nameEl = container.querySelector('[data-anonymize="person-name"]');
                if (nameEl) {{
                    name = (nameEl.innerText || nameEl.textContent || '').trim();
                }}

                var companyEl = container.querySelector('[data-anonymize="company-name"]');
                if (companyEl) {{
                    company = (companyEl.innerText || companyEl.textContent || '').trim();
                }}

                // Strategy 2: Try company/school links
                if (!company) {{
                    var companyLink = container.querySelector('a[href*="/company/"], a[href*="/school/"]');
                    if (companyLink) {{
                        company = (companyLink.innerText || companyLink.textContent || '').trim();
                    }}
                }}

                // Strategy 3: Try artdeco subtitle element
                if (!company) {{
                    var subtitleEl = container.querySelector('.artdeco-entity-lockup__subtitle');
                    if (subtitleEl) {{
                        var subtitleText = (subtitleEl.innerText || subtitleEl.textContent || '').trim();
                        // Try to extract company from subtitle (often "Title at Company")
                        var atMatch = subtitleText.match(/(?:\\bat\\b|\\bbei\\b|@)\\s+(.+)/i);
                        if (atMatch) {{
                            company = atMatch[1].trim();
                        }} else {{
                            // If no "at" separator, try splitting by common separators
                            var parts = subtitleText.split(/\\s*[|·]\\s*/);
                            if (parts.length > 1) {{
                                company = parts[parts.length - 1].trim();
                            }}
                        }}
                    }}
                }}

                // Strategy 4: Fall back to text line parsing
                if (!company) {{
                    var lines = fullText.split('\\n').map(function(l) {{ return l.trim(); }}).filter(function(l) {{ return l.length > 0; }});
                    for (var i = 0; i < lines.length; i++) {{
                        var line = lines[i];
                        if (line.includes('Founder') || line.includes('CEO') || line.includes('Director') ||
                            line.includes('Manager') || line.includes(' at ') || line.includes(' @ ')) {{
                            var extracted = line.replace(/^(Co-)?Founder\\s+/, '').replace(/^CEO\\s+/, '')
                                             .replace(/^Director\\s+/, '').replace(/^Manager\\s+/, '')
                                             .replace(/.*\\bat\\b\\s+/, '').replace(/.*@\\s+/, '').trim();
                            if (extracted && extracted.length > 2) {{
                                company = extracted;
                                break;
                            }}
                        }}
                    }}
                }}

                // Strategy 5 for name: fall back to text line parsing
                if (!name) {{
                    var lines = fullText.split('\\n').map(function(l) {{ return l.trim(); }}).filter(function(l) {{ return l.length > 0; }});
                    for (var i = 0; i < lines.length && !name; i++) {{
                        var line = lines[i];
                        if (line.length > 2 && line.length < 100 &&
                            !line.includes('connection') &&
                            !line.includes('degree') &&
                            !line.includes('Select') &&
                            !line.includes('Add to') &&
                            !line.includes('Badge') &&
                            !line.includes('is reachable')) {{
                            name = line;
                        }}
                    }}
                }}

                // Clean name: remove trailing status indicators
                if (name) {{
                    name = name.replace(/\\s+is reachable$/i, '').trim();
                }}

                return {{
                    linkedin_url: leadURL,
                    full_name: name,
                    company: company,
                    full_text: fullText.substring(0, 500)
                }};
            """)

            if not lead_data_js:
                logger.warning(f"Lead {lead_index}: JavaScript extraction returned null")
                return None

            # Build final lead data from JavaScript extraction
            lead_data = {}

            # URL and name
            lead_data['linkedin_url'] = lead_data_js['linkedin_url']
            raw_name = lead_data_js['full_name'] or 'Unknown'
            # Clean status indicators from name (e.g. "John Doe is reachable")
            lead_data['full_name'] = re.sub(r'\s+is reachable$', '', raw_name, flags=re.IGNORECASE).strip() or 'Unknown'

            # Parse name into first/last
            if lead_data['full_name'] and lead_data['full_name'] != 'Unknown':
                name_parts = lead_data['full_name'].strip().split()
                lead_data['first_name'] = name_parts[0] if name_parts else ""
                lead_data['last_name'] = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            else:
                logger.warning(f"Lead {lead_index}: No name extracted from JavaScript")
                return None

            # Company
            lead_data['company'] = lead_data_js['company'] or 'Unknown'
            if lead_data['company'] == 'Unknown':
                logger.debug(f"Lead {lead_index}: company not found. Container text: {lead_data_js.get('full_text', '')[:200]}")

            # Metadata
            lead_data['created_date'] = datetime.now().strftime("%Y-%m-%d")

            # Extract VMID from URL
            vmid = None
            lead_url = lead_data['linkedin_url']
            try:
                if lead_url and "/sales/lead/" in lead_url:
                    raw = lead_url.split("/sales/lead/", 1)[1]
                    vmid = raw.split(",")[0].split("?")[0].strip("/")
            except (IndexError, AttributeError):
                pass

            if not vmid and lead_url:
                match = re.search(r'/lead/([A-Za-z0-9_-]{10,})', lead_url)
                if match:
                    vmid = match.group(1)

            lead_data['vmid'] = vmid if vmid else lead_url

            logger.debug(f"Lead {lead_index}: ✓ {lead_data['full_name']} @ {lead_data['company']}")
            return lead_data

        except Exception as e:
            logger.error(f"Fehler bei Lead {lead_index}: {e}")
            return None

    def scrape_lead_with_retry(self, lead_index, max_retries=None, list_stats=None, current_page=0):
        """Scrapes a lead with retry logic for transient errors."""
        if max_retries is None:
            max_retries = self.config['MAX_RETRIES']

        for attempt in range(max_retries):
            try:
                return self.scrape_lead(lead_index)
            except StaleElementReferenceException:
                logger.warning(f"Stale element bei Lead {lead_index}, Versuch {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return None
            except (TimeoutException, WebDriverException) as e:
                logger.warning(f"Timeout bei Lead {lead_index}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        logger.error(f"Lead {lead_index} nach {max_retries} Versuchen fehlgeschlagen")
        if list_stats is not None:
            list_stats["errors"].append({
                "type": "max_retries_exceeded",
                "page": current_page,
                "message": f"Lead {lead_index} nach {max_retries} Versuchen fehlgeschlagen",
            })
        return None
