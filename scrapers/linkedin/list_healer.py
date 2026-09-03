"""Self-healing list management — resets exhausted lists and generates new ones."""

import json
import logging
import os
from datetime import datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)

PALETTE_FILE = 'config/filter_palette.json'
HEALER_STATE_FILE = 'healer_state.json'
HEALTH_FILE = 'data/stats/list_health.json'
LISTS_FILE = 'config/lists.json'

BASE_URL = 'https://www.linkedin.com/sales/search/people?query='


class ListHealer:
    """Evaluates list health and takes corrective action (reset or generate)."""

    def __init__(self, config):
        self.config = config
        self.output_dir = config.get('DATA_DIR', config['OUTPUT_DIR'])
        self.palette = self._load_json(PALETTE_FILE)
        self.healer_state = self._load_json(
            os.path.join(self.output_dir, HEALER_STATE_FILE),
            default={"used_combinations": [], "resets": {}},
        )
        self.health_data = None  # loaded lazily after refresh
        self.scraper_state = None  # loaded lazily in evaluate_and_heal

    # ── Public API ──

    def evaluate_and_heal(self):
        """Main entry point. Returns summary dict of actions taken."""
        if not self.palette:
            logger.warning("Keine filter_palette.json gefunden — Healer übersprungen.")
            return {"actions": []}

        # Refresh health data from log
        try:
            from reporting.health import main as refresh_health
            refresh_health()
        except Exception as e:
            logger.warning(f"Health-Daten konnten nicht aktualisiert werden: {e}")

        self.health_data = self._load_json(HEALTH_FILE, default={})
        list_health = self.health_data.get('list_health', [])

        if not list_health:
            return {"actions": []}

        # Load current scraper state for page resets
        from scrapers.linkedin.history import History
        self.scraper_state = History.load_state(self.config)

        actions = []
        generates_left = self.palette.get('max_new_lists_per_run', 2)

        for entry in list_health:
            name = entry['name']
            status = entry.get('status', 'healthy')
            yield_pct = entry.get('yield_pct', 100)

            if status in ('healthy', 'declining'):
                continue

            # Status is exhausted or dead
            reset_info = self.healer_state['resets'].get(name)

            if reset_info is None:
                # Never been reset — try a reset first
                if self._cooldown_passed(entry):
                    self._do_reset(name, yield_pct)
                    actions.append(f"RESET '{name}' auf Seite 1 (yield war {yield_pct}%)")
            else:
                # Was reset before — did it help?
                if yield_pct < 10 and generates_left > 0:
                    # Yield still low after reset → generate replacement
                    new_list = self._generate_new_list()
                    if new_list:
                        actions.append(
                            f"GENERATE '{new_list['name']}' als Ersatz für '{name}' (yield {yield_pct}%)"
                        )
                        generates_left -= 1
                elif self._cooldown_passed_since_reset(reset_info):
                    # Try another reset if under limit
                    if reset_info.get('reset_count', 0) < 2:
                        self._do_reset(name, yield_pct)
                        actions.append(f"RE-RESET '{name}' auf Seite 1 (yield war {yield_pct}%)")

        self._save_healer_state()

        return {"actions": actions}

    # ── Reset Logic ──

    def _cooldown_passed(self, health_entry):
        """Check if enough time has passed since the list was last seen active."""
        last_seen = health_entry.get('last_seen', '')
        if not last_seen:
            return True
        try:
            last_date = datetime.strptime(last_seen, '%Y-%m-%d')
            cooldown = self.palette.get('cooldown_days', 14)
            return datetime.now() - last_date >= timedelta(days=cooldown)
        except ValueError:
            return True

    def _cooldown_passed_since_reset(self, reset_info):
        """Check if cooldown has passed since last reset."""
        last_reset = reset_info.get('last_reset_date', '')
        if not last_reset:
            return True
        try:
            last_date = datetime.strptime(last_reset, '%Y-%m-%d')
            cooldown = self.palette.get('cooldown_days', 14)
            return datetime.now() - last_date >= timedelta(days=cooldown)
        except ValueError:
            return True

    def _do_reset(self, list_name, current_yield):
        """Reset a list's page position back to 1."""
        if self.scraper_state is None:
            from scrapers.linkedin.history import History
            self.scraper_state = History.load_state(self.config)

        # Update scraper state
        if list_name in self.scraper_state:
            self.scraper_state[list_name]['last_page'] = 1
            self.scraper_state[list_name]['exhausted'] = False

            from scrapers.linkedin.history import History
            History.save_state(self.config, self.scraper_state)

        # Record the reset
        reset_info = self.healer_state['resets'].setdefault(list_name, {
            'reset_count': 0,
        })
        reset_info['last_reset_date'] = datetime.now().strftime('%Y-%m-%d')
        reset_info['reset_count'] = reset_info.get('reset_count', 0) + 1
        reset_info['pre_reset_yield'] = current_yield

        logger.info(f"List healer: '{list_name}' auf Seite 1 zurückgesetzt.")

    # ── Generation Logic ──

    def _generate_new_list(self):
        """Generate a new list from an unused filter combination."""
        combo = self._pick_combination()
        if not combo:
            logger.info("List healer: Alle Filter-Kombinationen aufgebraucht.")
            return None

        region, titles = combo
        url = self._build_url(region, titles)

        title_names = [t['text'] for t in titles]
        list_name = f"auto_{region['text']}_{'+'.join(title_names)}"

        new_entry = {
            "name": list_name,
            "url": url,
            "pages_per_run": self.palette.get('pages_per_run_generated', 10),
        }

        # Add to lists.json
        self._add_to_lists_json(new_entry)

        # Record the combination
        self.healer_state['used_combinations'].append({
            "region_id": region['id'],
            "title_ids": [t.get('id', t['text']) for t in titles],
            "generated_at": datetime.now().strftime('%Y-%m-%d'),
            "list_name": list_name,
        })

        logger.info(f"List healer: Neue Liste generiert: '{list_name}'")
        return new_entry

    def _pick_combination(self):
        """Pick the first unused region × title group combination."""
        title_groups = self.palette.get('title_groups', [])
        regions = self.palette.get('regions', [])
        used = self.healer_state.get('used_combinations', [])

        used_keys = set()
        for u in used:
            key = (u['region_id'], tuple(sorted(u['title_ids'])))
            used_keys.add(key)

        for region in regions:
            for group in title_groups:
                title_ids = tuple(sorted(t.get('id', t['text']) for t in group))
                key = (region['id'], title_ids)
                if key not in used_keys:
                    return region, group

        return None

    def _build_url(self, region, titles):
        """Compose a Sales Navigator search URL with inline filters."""
        # Build region filter
        region_value = f"(id:{region['id']},text:{region['text']},selectionType:INCLUDED)"
        region_filter = f"(type:REGION,values:List({region_value}))"

        # Build title filter
        title_values = []
        for t in titles:
            if 'id' in t:
                title_values.append(f"(id:{t['id']},text:{t['text']},selectionType:INCLUDED)")
            else:
                title_values.append(f"(text:{t['text']},selectionType:INCLUDED)")
        title_filter = f"(type:CURRENT_TITLE,values:List({','.join(title_values)}))"

        query = f"(filters:List({region_filter},{title_filter}))"
        encoded = quote(query, safe='')

        return BASE_URL + encoded

    # ── Lists.json Management ──

    def _add_to_lists_json(self, new_entry):
        """Append a new list entry to lists.json."""
        lists = self._load_json(LISTS_FILE, default=[])
        # Don't add duplicates
        existing_names = {l['name'] for l in lists}
        if new_entry['name'] in existing_names:
            logger.info(f"Liste '{new_entry['name']}' existiert bereits, überspringe.")
            return

        lists.append(new_entry)
        self._save_json(LISTS_FILE, lists)

    # ── State I/O ──

    def _load_json(self, path, default=None):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Konnte {path} nicht laden: {e}")
        return default

    def _save_json(self, path, data):
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception as e:
            logger.error(f"Fehler beim Speichern von {path}: {e}")

    def _save_healer_state(self):
        path = os.path.join(self.output_dir, HEALER_STATE_FILE)
        self._save_json(path, self.healer_state)
