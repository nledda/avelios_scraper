"""Unit tests for scrapers/linkedin/export.py."""

import os
import pytest
import pandas as pd

from scrapers.linkedin.export import generate_public_link, export_to_file


@pytest.mark.unit
class TestGeneratePublicLink:
    """Tests for generate_public_link()."""

    def test_with_vmid(self):
        result = generate_public_link("ACwAAAB1234TEST")
        assert result == "https://www.linkedin.com/in/ACwAAAB1234TEST/"

    def test_with_full_url_no_trailing_slash(self):
        url = "https://www.linkedin.com/in/john-doe"
        result = generate_public_link(url)
        assert result == "https://www.linkedin.com/in/john-doe/"

    def test_with_full_url_trailing_slash(self):
        url = "https://www.linkedin.com/in/john-doe/"
        result = generate_public_link(url)
        # rstrip('/') removes the slash, then '/' is appended => single trailing slash
        assert result == "https://www.linkedin.com/in/john-doe/"

    def test_with_full_url_multiple_trailing_slashes(self):
        url = "https://www.linkedin.com/in/john-doe///"
        result = generate_public_link(url)
        assert result.endswith("/")
        # rstrip('/') removes all trailing slashes, then one is added
        assert result == "https://www.linkedin.com/in/john-doe/"

    def test_with_sales_nav_url_goes_to_vmid_branch(self):
        # '/sales/' in URL means it doesn't match the http+no-sales branch
        url = "https://www.linkedin.com/sales/lead/ACwAAAB5678"
        result = generate_public_link(url)
        # Falls through to the VMID template because '/sales/' is in the URL
        assert "linkedin.com/in/" in result


@pytest.mark.unit
class TestExportToFile:
    """Tests for export_to_file()."""

    def test_empty_data_returns_none(self, sample_config):
        result = export_to_file([], sample_config)
        assert result is None

    def test_export_creates_file(self, sample_config, sample_leads_list):
        filepath = export_to_file(sample_leads_list, sample_config)
        assert filepath is not None
        assert os.path.exists(filepath)
        assert filepath.endswith(".xlsx")

    def test_export_column_names(self, sample_config, sample_leads_list):
        filepath = export_to_file(sample_leads_list, sample_config)
        df = pd.read_excel(filepath)
        expected_columns = [
            "company", "Name", "Vorname", "Nachname",
            "LinkedIn Profil", "Leadquelle", "Owner", "Komitee",
        ]
        assert list(df.columns) == expected_columns

    def test_export_row_count(self, sample_config, sample_leads_list):
        filepath = export_to_file(sample_leads_list, sample_config)
        df = pd.read_excel(filepath)
        assert len(df) == len(sample_leads_list)

    def test_export_leadquelle_always_linkedin(self, sample_config, sample_leads_list):
        filepath = export_to_file(sample_leads_list, sample_config)
        df = pd.read_excel(filepath)
        assert (df["Leadquelle"] == "LinkedIn").all()

    def test_export_linkedin_profil_contains_vmid(self, sample_config, sample_leads_list):
        filepath = export_to_file(sample_leads_list, sample_config)
        df = pd.read_excel(filepath)
        for i, row in df.iterrows():
            vmid = sample_leads_list[i]["vmid"]
            assert vmid in row["LinkedIn Profil"]
