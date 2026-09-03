"""Excel export for network/connection data."""

import logging
import os
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def export_to_file(connections, profile_name, config):
    """Exports connections for a single profile to Excel.

    Args:
        connections: List of connection dicts.
        profile_name: Name of the profile owner (for filename).
        config: Config dict with OUTPUT_DIR.

    Returns:
        str: File path, or None on failure.
    """
    if not connections:
        logger.warning("Keine Kontakte zum Exportieren.")
        return None

    try:
        df = pd.DataFrame(connections)

        export_df = pd.DataFrame()
        export_df['Name'] = df['full_name']
        export_df['Vorname'] = df['first_name']
        export_df['Nachname'] = df['last_name']
        export_df['Position'] = df['position']
        export_df['Firma'] = df['company']
        export_df['LinkedIn Profil'] = df['linkedin_url']

        storage_path = config['OUTPUT_DIR']
        os.makedirs(storage_path, exist_ok=True)

        safe_name = "".join(c if c.isalnum() or c in ' _-' else '_' for c in profile_name)
        safe_name = safe_name.strip()[:50]
        current_date = datetime.now().strftime("%d.%m.%Y")
        num_contacts = len(export_df)
        filename = f"Kontakte_{safe_name}_{current_date}_{num_contacts}.xlsx"
        filepath = os.path.join(storage_path, filename)

        export_df.to_excel(filepath, index=False)
        logger.info(f"Export erfolgreich: {filepath} ({num_contacts} Kontakte)")

        return filepath

    except Exception as e:
        logger.error(f"Export fehlgeschlagen: {e}", exc_info=True)
        return None


def export_all(all_results, config):
    """Exports a combined overview of all profiles and their connections.

    Args:
        all_results: Dict mapping profile_name -> list of connection dicts.
        config: Config dict with OUTPUT_DIR.

    Returns:
        str: File path, or None on failure.
    """
    if not all_results:
        return None

    try:
        rows = []
        for profile_name, connections in all_results.items():
            for conn in connections:
                row = dict(conn)
                row['Quelle_Profil'] = profile_name
                rows.append(row)

        if not rows:
            return None

        df = pd.DataFrame(rows)
        export_df = pd.DataFrame()
        export_df['Quelle_Profil'] = df['Quelle_Profil']
        export_df['Name'] = df['full_name']
        export_df['Vorname'] = df['first_name']
        export_df['Nachname'] = df['last_name']
        export_df['Position'] = df['position']
        export_df['Firma'] = df['company']
        export_df['LinkedIn Profil'] = df['linkedin_url']

        storage_path = config['OUTPUT_DIR']
        os.makedirs(storage_path, exist_ok=True)

        current_date = datetime.now().strftime("%d.%m.%Y")
        total = len(export_df)
        filename = f"Netzwerk_Gesamt_{current_date}_{total}.xlsx"
        filepath = os.path.join(storage_path, filename)

        export_df.to_excel(filepath, index=False)
        logger.info(f"Gesamt-Export: {filepath} ({total} Kontakte)")

        return filepath

    except Exception as e:
        logger.error(f"Gesamt-Export fehlgeschlagen: {e}", exc_info=True)
        return None
