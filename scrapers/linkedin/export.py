"""Excel export for scraped lead data."""

import logging
import os
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def generate_public_link(vmid):
    """Generates a public LinkedIn URL from a VMID."""
    if vmid.startswith('http') and '/sales/' not in vmid:
        return vmid.rstrip('/') + '/'
    return f"https://www.linkedin.com/in/{vmid}/"


def export_to_file(scraped_data, config):
    """
    Exports collected leads to an Excel file.

    Returns:
        str: Path to the created file, or None on failure.
    """
    if not scraped_data:
        logger.warning("Keine Daten zum Exportieren vorhanden.")
        return None

    try:
        df = pd.DataFrame(scraped_data)

        export_df = pd.DataFrame()
        export_df['company'] = df.get('company', '')
        export_df['Name'] = df.get('full_name', '')
        export_df['Vorname'] = df.get('first_name', '')
        export_df['Nachname'] = df.get('last_name', '')
        export_df['LinkedIn Profil'] = df['vmid'].apply(generate_public_link)
        export_df['Leadquelle'] = 'LinkedIn'
        export_df['Owner'] = ''
        export_df['Komitee'] = df.get('komitee', '')

        current_date = datetime.now().strftime("%d.%m.%Y")
        base_pattern = f"Leads_{current_date}_V2_"

        counter = 1
        storage_path = config['OUTPUT_DIR']

        if os.path.exists(storage_path):
            try:
                for f in os.listdir(storage_path):
                    if f.startswith(base_pattern) and f.endswith(".xlsx"):
                        parts = f.replace(".xlsx", "").split("_")
                        if len(parts) >= 4:
                            try:
                                c = int(parts[3])
                                if c >= counter:
                                    counter = c + 1
                            except ValueError:
                                continue
            except Exception as e:
                logger.warning(f"Konnte Verzeichnis nicht scannen: {e}")

        num_leads = len(export_df)
        filename = f"{base_pattern}{counter}_{num_leads}.xlsx"
        filepath = os.path.join(storage_path, filename)

        export_df.to_excel(filepath, index=False)
        logger.info(f"✓ Export erfolgreich: {filepath}")
        logger.info(f"  {num_leads} Leads exportiert")

        return filepath

    except Exception as e:
        logger.error(f"Export fehlgeschlagen: {e}", exc_info=True)
        return None
