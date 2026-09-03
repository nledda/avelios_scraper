"""WebDriver lifecycle, login, cookies, 2FA, and anti-detection."""

import json
import logging
import os
import random
import time
import urllib.request
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


class Browser:
    """Manages the Chrome WebDriver, login flow, and session persistence."""

    def __init__(self, config):
        self.config = config
        self.driver = None

    def _get_file_path(self, filename):
        return os.path.join(self.config.get('DATA_DIR', self.config['OUTPUT_DIR']), filename)

    # ── Driver Setup ──

    def setup_driver(self):
        """Creates a stealth Chrome driver with anti-detection measures."""
        chrome_options = webdriver.ChromeOptions()

        chrome_binary = os.environ.get('CHROME_BIN')
        if chrome_binary:
            chrome_options.binary_location = chrome_binary

        chrome_options.add_argument("--no-sandbox")
        if self.config['HEADLESS']:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")

        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
        chrome_options.add_argument("--lang=de-DE")

        try:
            chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
            if chromedriver_path:
                service = Service(chromedriver_path)
            else:
                service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['de-DE', 'de', 'en-US', 'en']
                    });
                '''
            })

            driver.set_page_load_timeout(self.config['PAGE_LOAD_TIMEOUT'])
            driver.implicitly_wait(5)

            logger.info("Chrome Driver erfolgreich initialisiert.")
            return driver

        except Exception as e:
            logger.error(f"Fehler beim Setup des Drivers: {e}")
            raise

    # ── Session Management ──

    def prepare(self):
        """Sets up driver and completes LinkedIn login."""
        self.driver = self.setup_driver()

        logger.info("Navigiere zu LinkedIn...")
        self.driver.get("https://www.linkedin.com/sales/login")
        self.smart_wait(self.config['WAIT_MEDIUM'])

        cookies_loaded = self.load_cookies()

        if cookies_loaded:
            logger.info("Cookies geladen, aktualisiere Seite...")
            self.driver.refresh()
            self._wait_for_page_fully_loaded()
        else:
            # Even without cookies, wait for page to load
            self._wait_for_page_fully_loaded(timeout=15)

        current_url = self.driver.current_url.lower() if self.driver.current_url else ""

        if "challenge" in current_url:
            logger.info("Challenge erkannt, behandle Verifizierung...")
            if self._handle_verification():
                self.save_cookies()
            else:
                logger.warning("Verifizierung fehlgeschlagen, versuche normalen Login...")
                self._login_with_credentials()
        elif "feed" not in current_url and "sales" not in current_url:
            logger.info("Nicht eingeloggt, starte Login-Prozess...")
            self._login_with_credentials()
        else:
            logger.info("URL deutet auf Login hin, validiere Session...")
            if self._validate_session():
                logger.info("Session validiert — eingeloggt!")
            else:
                logger.warning("Session abgelaufen, starte Login-Prozess...")
                self._login_with_credentials()

    def _validate_session(self):
        """Navigate to Sales Navigator and verify the session is actually valid."""
        try:
            self.driver.get("https://www.linkedin.com/sales/home")
            self.smart_wait(self.config['WAIT_LONG'])

            current_url = self.driver.current_url.lower() if self.driver.current_url else ""

            if "login" in current_url or "authwall" in current_url or "uas/login" in current_url:
                logger.warning(f"Session ungültig — Redirect zu: {self.driver.current_url}")
                self._notify(
                    "LinkedIn Session abgelaufen",
                    "Cookies sind ungültig. Bitte manuell einloggen um neue Cookies zu speichern.",
                    tags="rotating_light",
                )
                return False

            if "challenge" in current_url or "checkpoint" in current_url:
                logger.info("Challenge bei Session-Validierung erkannt...")
                if self._handle_verification():
                    self.save_cookies()
                    return True
                return False

            if "sales" in current_url:
                logger.info("Sales Navigator erreichbar — Session gültig.")
                self.save_cookies()
                return True

            logger.warning(f"Unerwartete URL bei Validierung: {self.driver.current_url}")
            return False
        except Exception as e:
            logger.error(f"Fehler bei Session-Validierung: {e}")
            return False

    def is_alive(self):
        """Checks whether the browser session is still active."""
        try:
            self.driver.current_url  # noqa: B018
            return True
        except Exception:
            return False

    def restart(self):
        """Restarts the browser after a session crash."""
        logger.warning("Browser-Session verloren. Starte Browser neu...")
        try:
            self.driver.quit()
        except Exception:
            pass
        self.driver = None
        self.prepare()
        logger.info("Browser erfolgreich neu gestartet.")

    def quit(self):
        """Closes the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    # ── Cookies ──

    def save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            path = self._get_file_path(self.config['COOKIE_FILE'])
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2, default=str)
            logger.info(f"Cookies gespeichert: {path}")
        except Exception as e:
            logger.error(f"Cookie-Fehler: {e}")

    def load_cookies(self):
        cookie_path = self._get_file_path(self.config['COOKIE_FILE'])
        if not os.path.exists(cookie_path):
            logger.info("Keine gespeicherten Cookies gefunden.")
            return False

        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Cookie konnte nicht geladen werden: {e}")

            logger.info("Cookies erfolgreich geladen.")
            return True
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Fehler beim Laden der Cookies: {e}")
            return False

    # ── Login ──

    def _login_with_credentials(self):
        """Performs login with username and password."""
        try:
            if self.driver.current_url and "login" not in self.driver.current_url and "challenge" not in self.driver.current_url:
                self.driver.get("https://www.linkedin.com/sales/login")
                self.smart_wait(self.config['WAIT_MEDIUM'])

            logger.info("Gebe Anmeldedaten ein...")

            # Wait for JS-rendered form to load
            self._wait_for_page_fully_loaded()
            self.smart_wait(self.config['WAIT_LONG'])

            # The form is in an iframe! Switch to it first
            logger.info("Suche authentication iframe...")
            try:
                # Wait for the authentication iframe to be present
                iframe = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe.authentication-iframe'))
                )
                logger.info("Authentication iframe gefunden, wechsle Kontext...")
                self.driver.switch_to.frame(iframe)
                logger.info("Im iframe-Kontext")
            except TimeoutException:
                logger.warning("Authentication iframe nicht gefunden, versuche direkt auf der Seite...")

            # Email — find all text-like inputs and interact with the FIRST visible one
            email_found = False
            try:
                logger.info("Suche Email-Input via JavaScript...")
                email_elem = self.driver.execute_script("""
                    // Find the first visible input that looks like an email field
                    var inputs = document.querySelectorAll('input[type="text"], input[type="email"], input:not([type])');
                    for (var i = 0; i < inputs.length; i++) {
                        var input = inputs[i];
                        var rect = input.getBoundingClientRect();
                        var style = window.getComputedStyle(input);
                        // Check if visible
                        if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
                            // Check if enabled
                            if (!input.disabled && !input.readOnly) {
                                return input;
                            }
                        }
                    }
                    return null;
                """)

                if email_elem:
                    logger.info("Email-Input gefunden, fülle aus...")
                    # Clear and fill via JavaScript to avoid issues
                    self.driver.execute_script("""
                        arguments[0].focus();
                        arguments[0].value = '';
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    """, email_elem)
                    time.sleep(0.3)

                    # Type slowly like a human
                    for char in self.config['EMAIL']:
                        email_elem.send_keys(char)
                        time.sleep(random.uniform(0.05, 0.15))

                    email_elem.send_keys(Keys.TAB)  # Tab to next field
                    email_found = True
                    logger.info("Email eingegeben.")
                    self.smart_wait(1)
            except Exception as e:
                logger.warning(f"Email-Feld Fehler: {e}")

            if not email_found:
                logger.warning("Email-Feld nicht gefunden")

            # Password — find via JavaScript (form is React-rendered)
            pass_elem = None
            try:
                logger.info("Suche Passwort-Input via JavaScript...")
                pass_elem = self.driver.execute_script("""
                    // Find the first visible password input
                    var inputs = document.querySelectorAll('input[type="password"]');
                    for (var i = 0; i < inputs.length; i++) {
                        var input = inputs[i];
                        var rect = input.getBoundingClientRect();
                        var style = window.getComputedStyle(input);
                        // Check if visible
                        if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
                            // Check if enabled
                            if (!input.disabled && !input.readOnly) {
                                return input;
                            }
                        }
                    }
                    // Fallback: return first password input even if not visible (might be selected)
                    return inputs[0] || null;
                """)

                if pass_elem:
                    logger.info("Passwort-Input gefunden, fülle aus...")
                else:
                    # Try alternative: look for input with any attribute containing 'password'
                    logger.warning("Keine password inputs gefunden, versuche alternative Selektoren...")
                    pass_elem = self.driver.execute_script("""
                        var inputs = document.querySelectorAll('input');
                        for (var i = 0; i < inputs.length; i++) {
                            var input = inputs[i];
                            // Check attributes for password-related hints
                            if (input.name && input.name.includes('password')) return input;
                            if (input.id && input.id.includes('password')) return input;
                            if (input.getAttribute('data-testid') && input.getAttribute('data-testid').includes('password')) return input;
                        }
                        return null;
                    """)

                    if pass_elem:
                        logger.info("Passwort-Input via Attribut-Suche gefunden")
            except Exception as e:
                logger.warning(f"Fehler beim Suchen von Passwort-Input: {e}")

            if not pass_elem:
                self.save_debug_info("login_password_not_found")
                raise Exception("Passwort-Feld nicht gefunden!")

            # Scroll into view and fill password
            logger.info("Fülle Passwort aus...")
            self.driver.execute_script("""
                arguments[0].scrollIntoView(true);
                arguments[0].focus();
            """, pass_elem)
            time.sleep(0.5)

            # Clear the field first
            self.driver.execute_script("""
                arguments[0].value = '';
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """, pass_elem)
            time.sleep(0.3)

            # Type password slowly like a human
            for char in self.config['PASSWORD']:
                pass_elem.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            # Trigger change event after typing
            self.driver.execute_script("""
                var el = arguments[0];
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            """, pass_elem)
            time.sleep(0.5)
            self.smart_wait(1)

            # Submit — find button via JavaScript
            logger.info("Suche Submit-Button...")
            submitted = False

            try:
                submit_btn = self.driver.execute_script("""
                    // Look for Sign in / Einloggen button
                    var buttons = document.querySelectorAll('button');
                    for (var b of buttons) {
                        var text = (b.innerText || b.textContent || '').trim();
                        if (text.includes('Sign in') || text.includes('Einloggen')) {
                            return b;
                        }
                    }
                    // Fallback: find first enabled button
                    for (var b of buttons) {
                        if (!b.disabled) return b;
                    }
                    return null;
                """)

                if submit_btn:
                    logger.info("Submit-Button gefunden, klicke...")
                    self.driver.execute_script("arguments[0].click();", submit_btn)
                    submitted = True
                    logger.info("Formular abgeschickt.")
            except Exception as e:
                logger.warning(f"Fehler beim Submit: {e}")

            if not submitted:
                logger.info("Versuche Submit via Enter-Taste...")
                pass_elem.send_keys(Keys.RETURN)
                submitted = True

            logger.info("Login-Formular abgeschickt, warte auf Antwort...")
            self.smart_wait(self.config['WAIT_MEDIUM'])

            # Switch back to main content (if we were in iframe)
            try:
                self.driver.switch_to.default_content()
                logger.info("Zurück zum Hauptinhalts-Kontext")
            except Exception:
                pass

            if self.driver.current_url and "challenge" in self.driver.current_url:
                logger.info("2FA Challenge erkannt...")
                if self._handle_verification():
                    self.save_cookies()
                else:
                    self.save_debug_info("2fa_failed")
                    raise Exception("2FA Verifizierung fehlgeschlagen")

            current_url = self.driver.current_url.lower() if self.driver.current_url else ""
            if "feed" in current_url or "sales" in current_url:
                logger.info("Login erfolgreich!")
                self.save_cookies()
            else:
                logger.warning(f"Login-Status unklar. Aktuelle URL: {self.driver.current_url}")
                self.save_debug_info("login_after_submit")

        except Exception as e:
            logger.error(f"Login-Fehler: {e}")
            self.save_debug_info("login_exception")
            self._notify(
                "LinkedIn Login fehlgeschlagen",
                f"Login konnte nicht durchgeführt werden: {e}",
                tags="x",
            )
            raise

    # ── 2FA ──

    def _handle_verification(self):
        """Handles 2FA verification challenge."""
        try:
            logger.info("2FA-Verifizierung erforderlich. Suche nach Eingabefeld...")

            verification_input = self.driver.execute_script("""
                // Look for 2FA input field
                var inputs = document.querySelectorAll('input');
                for (var i = 0; i < inputs.length; i++) {
                    var input = inputs[i];
                    var id = input.id || '';
                    var name = input.name || '';
                    var testid = input.getAttribute('data-testid') || '';
                    var autocomplete = input.getAttribute('autocomplete') || '';

                    if (id.includes('verification') || id.includes('pin') ||
                        name.includes('pin') || name.includes('verification') ||
                        testid.includes('verification') || testid.includes('pin') ||
                        autocomplete.includes('one-time-code')) {
                        var rect = input.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return input;
                    }
                }
                // Fallback: return first visible tel or text input on challenge page
                for (var i = 0; i < inputs.length; i++) {
                    var input = inputs[i];
                    if (input.type === 'tel' || input.type === 'text') {
                        var rect = input.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return input;
                    }
                }
                return null;
            """)

            if not verification_input:
                logger.error("Kein Verifizierungsfeld gefunden!")
                return False

            logger.info("2FA-Eingabefeld gefunden")

            verification_code = self._get_verification_code()

            # Clear and fill 2FA code
            self.driver.execute_script("arguments[0].value = ''; arguments[0].focus();", verification_input)
            time.sleep(0.3)

            for digit in verification_code:
                verification_input.send_keys(digit)
                time.sleep(random.uniform(0.1, 0.3))

            time.sleep(0.5)

            # Find and click submit button
            submit_button = self.driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var b of buttons) {
                    var text = (b.innerText || b.textContent || '').toUpperCase();
                    if (text.includes('VERIFY') || text.includes('SUBMIT') || text.includes('BESTÄTIGEN')) {
                        return b;
                    }
                }
                // Fallback: first enabled button
                for (var b of buttons) {
                    if (!b.disabled) return b;
                }
                return null;
            """)

            if submit_button:
                logger.info("2FA Submit-Button gefunden, klicke...")
                self.driver.execute_script("arguments[0].click();", submit_button)
            else:
                logger.info("Sende Enter-Taste für 2FA...")
                verification_input.send_keys(Keys.RETURN)

            time.sleep(self.config['WAIT_MEDIUM'])

            if self.driver.current_url and "challenge" not in self.driver.current_url:
                logger.info("Verifizierung erfolgreich!")
                return True
            else:
                logger.warning("Verifizierung möglicherweise fehlgeschlagen")
                return False

        except Exception as e:
            logger.error(f"Fehler bei Verifizierung: {e}")
            return False

    @staticmethod
    def _get_verification_code():
        if os.getenv('CI'):
            logger.error("2FA erforderlich, aber im CI-Modus nicht möglich.")
            raise SystemExit(1)

        max_attempts = 3
        for attempt in range(max_attempts):
            code = input(f"Bitte geben Sie den 6-stelligen Bestätigungscode ein (Versuch {attempt + 1}/{max_attempts}): ").strip()
            if code.isdigit() and len(code) == 6:
                return code
            logger.warning("Ungültiger Code. Bitte genau 6 Ziffern eingeben.")

        raise ValueError("Ungültiger Verifizierungscode nach mehreren Versuchen")

    # ── Notifications ──

    def _notify(self, title, message, priority="high", tags="warning"):
        """Send a push notification via ntfy.sh."""
        topic = self.config.get('NTFY_TOPIC', '')
        if not topic:
            logger.debug("NTFY_TOPIC nicht gesetzt — keine Benachrichtigung gesendet.")
            return
        try:
            url = f"https://ntfy.sh/{topic}"
            data = message.encode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Title', title)
            req.add_header('Priority', priority)
            req.add_header('Tags', tags)
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"Benachrichtigung gesendet: {title}")
        except Exception as e:
            logger.warning(f"Benachrichtigung fehlgeschlagen: {e}")

    # ── Helpers ──

    def _wait_for_page_fully_loaded(self, timeout=20):
        """Waits for the page to be fully loaded with JavaScript executed.

        Checks for:
        1. document.readyState === 'complete'
        2. At least one input field in the DOM (form is rendered)
        """
        logger.info("Warte auf vollständiges Laden der Seite...")
        try:
            # Wait for document.readyState === 'complete'
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            logger.info("document.readyState === complete")

            # Wait for at least one input field to be present in DOM
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input"))
            )
            logger.info("Input-Felder im DOM gefunden")
        except TimeoutException:
            logger.warning(f"Timeout beim Warten auf Seite (>{timeout}s). Fahre fort...")

    def smart_wait(self, base_seconds=None, variance=2):
        if base_seconds is None:
            base_seconds = self.config['WAIT_SHORT']
        wait_time = max(0.5, base_seconds + random.uniform(-variance, variance))
        time.sleep(wait_time)

    def human_like_scroll(self):
        try:
            total_height = int(self.driver.execute_script("return document.body.scrollHeight"))
            current_position = 0

            while current_position < total_height:
                scroll_amount = random.randint(200, 500)
                current_position += scroll_amount
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(random.uniform(0.1, 0.4))

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            logger.warning(f"Fehler beim Scrollen: {e}")

    def save_debug_info(self, prefix="debug"):
        try:
            timestamp = datetime.now().strftime("%H_%M_%S")
            base_name = f"{prefix}_{timestamp}"

            screenshot_path = self._get_file_path(f"{base_name}.png")
            self.driver.save_screenshot(screenshot_path)

            html_path = self._get_file_path(f"{base_name}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)

            logger.info(f"Debug-Infos gespeichert: {base_name} (.png & .html)")
        except Exception as e:
            logger.error(f"Konnte Debug-Infos nicht speichern: {e}")
