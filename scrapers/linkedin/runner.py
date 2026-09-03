"""Main scraper orchestration — composes browser, extractor, navigator, and history."""

import logging
import random
import subprocess
import time
from datetime import datetime, timedelta

from scrapers.linkedin.config import load_lists
from scrapers.linkedin.history import History
from reporting.stats import create_run_record, create_list_stats, append_run
from scrapers.linkedin.browser import Browser
from scrapers.linkedin.extractor import LeadExtractor
from scrapers.linkedin.navigator import Navigator, SessionBlockedError

logger = logging.getLogger(__name__)


class LinkedInScraper:
    """LinkedIn Sales Navigator scraper with error handling and anti-detection."""

    def __init__(self, config):
        self.config = config
        self.history = History(config)
        self.session_start = datetime.now()
        self.scraped_data = []

        # Browser (created lazily in prepare_driver)
        self._browser = Browser(config)

        # Stats tracking
        self.run_stats = create_run_record(source="script")
        self.run_stats["target"] = config['TARGET']
        self._current_list_stats = None
        self._current_page = 0

    # ── Public properties for backward compat ──

    @property
    def driver(self):
        return self._browser.driver

    @driver.setter
    def driver(self, value):
        self._browser.driver = value

    def prepare_driver(self):
        """Prepares the browser and logs into LinkedIn."""
        self._browser.prepare()

    # ── Main Run ──

    def run(self):
        """
        Main entry point: scrapes all configured lists until target or time limit.

        Returns:
            list: Collected lead data.
        """
        try:
            target = self.config['TARGET']
            max_minutes = self.config.get('MAX_MINUTES', 60)
            deadline = self.session_start + timedelta(minutes=max_minutes) if max_minutes > 0 else None

            logger.info("=" * 60)
            logger.info("LINKEDIN SCRAPER GESTARTET")
            logger.info(f"Ziel: {target} neue Leads")
            logger.info(f"Zeitlimit: {max_minutes} Minuten (0 = unbegrenzt)")
            logger.info(f"Bereits in Historie: {len(self.history)} Leads")
            logger.info("=" * 60)

            if deadline:
                logger.info(f"Zeitlimit: {max_minutes} Minuten (bis {deadline.strftime('%H:%M:%S')})")

            lists = load_lists(self.config)
            state = History.load_state(self.config)

            # Sort lists by yield — scrape healthiest first
            lists = self._sort_by_yield(lists)

            self.prepare_driver()

            extractor = LeadExtractor(self._browser, self.config)
            navigator = Navigator(self._browser, extractor)

            total_collected = 0
            unique_vmids = set()
            max_empty_pages = 3
            max_no_new_pages = 3
            session_recovered = False  # only attempt one session recovery per run
            global_timeouts = 0  # track consecutive lists that produce nothing
            max_global_timeouts = 3  # abort if this many lists in a row produce 0

            def time_remaining():
                if deadline is None:
                    return True
                return datetime.now() < deadline

            while total_collected < target and time_remaining():
                all_exhausted = all(
                    state.get(sl['name'], {}).get('exhausted', False)
                    for sl in lists
                )
                if all_exhausted:
                    logger.info("Alle Listen erschöpft — kein weiterer Fortschritt möglich.")
                    break

                if global_timeouts >= max_global_timeouts:
                    logger.error(
                        f"ABBRUCH: {global_timeouts} Listen in Folge ohne Ergebnis. "
                        "LinkedIn blockiert wahrscheinlich diese Session."
                    )
                    break

                for search_list in lists:
                    if total_collected >= target or not time_remaining():
                        break
                    if global_timeouts >= max_global_timeouts:
                        break

                    list_name = search_list['name']
                    list_url = search_list['url']

                    list_state = state.setdefault(list_name, {"last_page": 1, "exhausted": False})

                    if list_state['exhausted']:
                        logger.info(f"Liste '{list_name}' erschöpft, überspringe.")
                        continue

                    current_page = list_state.get('last_page', 1)
                    consecutive_empty = 0
                    consecutive_no_new = 0
                    list_got_data = False

                    list_stats = create_list_stats(list_name, current_page)
                    self._current_list_stats = list_stats

                    logger.info(f"\n{'=' * 40}")
                    logger.info(f"Liste: {list_name} | Start: Seite {current_page}")
                    logger.info(f"{'=' * 40}")

                    while total_collected < target and time_remaining():
                        if not self._browser.is_alive():
                            self._browser.restart()
                            self.run_stats["errors_summary"]["session_restart"] += 1

                        logger.info(f"\n--- [{list_name}] SEITE {current_page} ---")

                        try:
                            data = navigator.scrape_page(current_page, list_url, self.config)
                        except SessionBlockedError as e:
                            logger.error(f"Session blockiert: {e}")
                            if not session_recovered:
                                logger.info("Versuche Session-Recovery (Browser-Neustart)...")
                                self._browser.restart()
                                self.run_stats["errors_summary"]["session_restart"] += 1
                                session_recovered = True
                                # Retry this same page
                                try:
                                    data = navigator.scrape_page(current_page, list_url, self.config)
                                except SessionBlockedError:
                                    logger.error("Session-Recovery fehlgeschlagen. Breche ab.")
                                    global_timeouts = max_global_timeouts
                                    break
                            else:
                                logger.error("Session bereits einmal neu gestartet. Breche ab.")
                                global_timeouts = max_global_timeouts
                                break

                        list_stats["pages_scraped"] += 1
                        list_stats["end_page"] = current_page
                        self._current_page = current_page
                        self.run_stats["total_pages_scraped"] += 1

                        if not data:
                            consecutive_empty += 1
                            self.run_stats["errors_summary"]["empty_pages"] += 1
                            logger.warning(f"Leere Seite {current_page} ({consecutive_empty}/{max_empty_pages})")
                            if consecutive_empty >= max_empty_pages:
                                logger.info(f"Zu viele leere Seiten für '{list_name}', markiere als erschöpft.")
                                list_state['exhausted'] = True
                                list_stats["exhausted"] = True
                                History.save_state(self.config, state)
                                break
                        else:
                            consecutive_empty = 0
                            list_got_data = True
                            new_count = 0
                            duplicate_count = 0

                            for lead in data:
                                if total_collected >= target:
                                    break

                                vmid = lead['vmid']

                                if self.history.has_vmid(vmid) or vmid in unique_vmids:
                                    duplicate_count += 1
                                    list_stats["duplicates"] += 1
                                    logger.debug(f"Lead {vmid} bereits bekannt, überspringe")
                                    continue

                                name_key = History.make_name_key(lead)
                                unique_vmids.add(vmid)
                                if search_list.get('komitee'):
                                    lead['komitee'] = search_list['komitee']
                                self.scraped_data.append(lead)
                                self.history.add_vmid(vmid)
                                self.history.add_name(name_key)

                                total_collected += 1
                                list_stats["leads_collected"] += 1
                                logger.info(f"✓ Neuer Lead: {lead['full_name']} @ {lead['company']} ({total_collected}/{target})")
                                new_count += 1

                            logger.info(f"Seite {current_page} [{list_name}]: {new_count} neue, {duplicate_count} Duplikate")

                            if new_count == 0:
                                consecutive_no_new += 1
                                logger.info(f"Seiten ohne neue Leads: {consecutive_no_new}/{max_no_new_pages}")
                                if consecutive_no_new >= max_no_new_pages:
                                    logger.info(f"Zu viele Seiten ohne neue Leads für '{list_name}', überspringe Liste.")
                                    list_state['exhausted'] = True
                                    list_stats["exhausted"] = True
                                    History.save_state(self.config, state)
                                    break
                            else:
                                consecutive_no_new = 0

                        # Only advance saved page when we got data —
                        # prevents drift past list boundaries on empty pages
                        if data:
                            list_state['last_page'] = current_page + 1
                        History.save_state(self.config, state)

                        if data and not navigator.has_next_page():
                            logger.info(f"Keine weiteren Seiten für '{list_name}', markiere als erschöpft.")
                            list_state['exhausted'] = True
                            list_stats["exhausted"] = True
                            History.save_state(self.config, state)
                            break

                        current_page += 1

                        if total_collected < target:
                            pause = random.uniform(3, 6)
                            logger.info(f"Pause vor nächster Seite: {pause:.1f}s")
                            time.sleep(pause)

                    self.run_stats["lists"].append(list_stats)
                    self._current_list_stats = None

                    # Track global timeout pattern across lists
                    if list_got_data:
                        global_timeouts = 0
                    else:
                        global_timeouts += 1
                        logger.warning(f"Listen ohne Daten in Folge: {global_timeouts}/{max_global_timeouts}")

                    if total_collected >= target:
                        logger.info(f"\nZIEL ERREICHT: {total_collected} Leads gesammelt!")
                        break

            if not time_remaining():
                logger.info(f"\nZEITLIMIT ERREICHT ({max_minutes} Min). {total_collected} Leads gesammelt.")

            # Reset exhausted flags for next run
            for sl in lists:
                state.setdefault(sl['name'], {})['exhausted'] = False
            History.save_state(self.config, state)
            logger.info("State gespeichert (Seitenpositionen behalten, exhausted zurückgesetzt).")

            # Final stats
            self.run_stats["total_collected"] = total_collected
            self.run_stats["target_reached"] = total_collected >= target
            self.run_stats["all_lists_exhausted"] = all(
                state.get(sl['name'], {}).get('exhausted', False) for sl in lists
            )
            append_run(self.run_stats)
            logger.info("Stats in stats.json gespeichert.")

            logger.info("\n" + "=" * 60)
            logger.info("SCRAPING ABGESCHLOSSEN")
            logger.info(f"Gesammelte Leads: {total_collected}")
            logger.info(f"Laufzeit: {datetime.now() - self.session_start}")
            logger.info("=" * 60)

            return self.scraped_data

        except KeyboardInterrupt:
            logger.warning("\n\nScraping durch Nutzer abgebrochen!")
            self.run_stats["total_collected"] = len(self.scraped_data)
            self.run_stats["errors_summary"]["other"] += 1
            append_run(self.run_stats)
            return self.scraped_data
        except Exception as e:
            logger.error(f"Kritischer Fehler: {e}", exc_info=True)
            self.run_stats["errors_summary"]["other"] += 1
            append_run(self.run_stats)
            return self.scraped_data
        finally:
            self._browser.quit()
            self._heal_lists()
            self._push_stats()

    @staticmethod
    def _sort_by_yield(lists):
        """Sort lists so highest-yield lists are scraped first."""
        try:
            import json
            with open('data/stats/list_health.json', 'r', encoding='utf-8') as f:
                health = json.load(f)
            yield_map = {h['name']: h.get('yield_pct', 0) for h in health.get('list_health', [])}

            # Lists with health data: sort by yield descending
            # Lists without health data (new): put them first (they're untested, might be great)
            def sort_key(lst):
                name = lst['name']
                if name not in yield_map:
                    return -1  # new lists first
                return -yield_map[name]  # highest yield first

            sorted_lists = sorted(lists, key=sort_key)
            logger.info("Listen nach Yield sortiert: " + ", ".join(
                f"{l['name']}({yield_map.get(l['name'], '?')}%)" for l in sorted_lists[:5]
            ) + " ...")
            return sorted_lists
        except Exception as e:
            logger.warning(f"Konnte Listen nicht nach Yield sortieren: {e}")
            return lists

    def _heal_lists(self):
        """Evaluate list health and take corrective action."""
        try:
            from scrapers.linkedin.list_healer import ListHealer
            healer = ListHealer(self.config)
            summary = healer.evaluate_and_heal()
            if summary.get('actions'):
                logger.info(f"List healer: {len(summary['actions'])} Aktionen durchgeführt.")
                for action in summary['actions']:
                    logger.info(f"  - {action}")
            else:
                logger.info("List healer: Keine Aktionen nötig.")
        except Exception as e:
            logger.warning(f"List healer Fehler (nicht kritisch): {e}")

    def _push_stats(self):
        """Commits and pushes stats + state files."""
        try:
            files_to_commit = [
                "data/stats/stats.json",
                "data/stats/list_health.json",
                "config/lists.json",
                "data/linkedin/healer_state.json",
                "data/linkedin/scraped_history.txt",
                "data/linkedin/name_history.txt",
                "data/linkedin/scraper_state.json",
            ]
            for f in files_to_commit:
                subprocess.run(["git", "add", f], capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"stats: update after run {self.run_stats['id']}"],
                check=True, capture_output=True,
            )
            subprocess.run(["git", "push"], check=True, capture_output=True)
            logger.info("State + stats committed and pushed to remote.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git push fehlgeschlagen: {e.stderr}")
        except FileNotFoundError:
            logger.warning("Git nicht verfügbar, stats nicht gepusht.")

    def export_to_file(self):
        """Exports collected leads to Excel. Delegates to export module."""
        from scrapers.linkedin.export import export_to_file
        return export_to_file(self.scraped_data, self.config)
