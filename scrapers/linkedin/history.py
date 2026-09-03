"""Lead history tracking — VMID and name-based duplicate detection."""

import json
import logging
import os

logger = logging.getLogger(__name__)


class History:
    """Manages VMID and name-based history files to prevent duplicate leads."""

    def __init__(self, config):
        self.config = config
        self.data_dir = config.get('DATA_DIR', config['OUTPUT_DIR'])
        self._ensure_dirs()
        self.vmids = self._load_file(config['HISTORY_FILE'], 'Historie')
        self.names = self._load_file('name_history.txt', 'Namens-Historie', normalize=True)

    def _ensure_dirs(self):
        for d in [self.data_dir, self.config['OUTPUT_DIR']]:
            if not os.path.exists(d):
                os.makedirs(d)
                logger.info(f"Verzeichnis erstellt: {d}")

    def _get_path(self, filename):
        return os.path.join(self.data_dir, filename)

    def _load_file(self, filename, label, normalize=False):
        path = self._get_path(filename)
        loaded = set()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        cleaned = line.strip()
                        if normalize:
                            cleaned = cleaned.lower()
                        if cleaned:
                            loaded.add(cleaned)
                logger.info(f"{len(loaded)} Einträge aus der {label} geladen.")
            except Exception as e:
                logger.warning(f"Konnte {label} nicht laden: {e}")
        else:
            logger.info(f"Keine {label} gefunden. Starte mit leerer {label}.")
        return loaded

    def has_vmid(self, vmid):
        return vmid in self.vmids

    def add_vmid(self, vmid):
        self.vmids.add(vmid)
        self._append(self.config['HISTORY_FILE'], vmid)

    def has_name(self, name_key):
        return name_key.lower() in self.names

    def add_name(self, name_key):
        self.names.add(name_key.lower())
        self._append('name_history.txt', name_key)

    def _append(self, filename, value):
        path = self._get_path(filename)
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(f"{value}\n")
        except Exception as e:
            logger.error(f"Fehler beim Speichern in {filename}: {e}")

    @staticmethod
    def make_name_key(lead):
        name = lead.get('full_name', '').strip().lower()
        company = lead.get('company', '').strip().lower()
        return f"{name}|{company}"

    def __len__(self):
        return len(self.vmids)

    # State persistence

    @staticmethod
    def load_state(config):
        state_path = os.path.join(config.get('DATA_DIR', config['OUTPUT_DIR']), 'scraper_state.json')
        if os.path.exists(state_path):
            try:
                with open(state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                logger.info(f"State geladen: {state_path}")
                return state
            except Exception as e:
                logger.warning(f"Konnte State nicht laden: {e}. Starte mit leerem State.")
        return {}

    @staticmethod
    def save_state(config, state):
        state_path = os.path.join(config.get('DATA_DIR', config['OUTPUT_DIR']), 'scraper_state.json')
        try:
            tmp_path = state_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, state_path)
        except Exception as e:
            logger.error(f"Fehler beim Speichern des States: {e}")
