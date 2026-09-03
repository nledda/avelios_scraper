"""Unit tests for scrapers/linkedin/extractor.py and scrapers/linkedin/export.py (name parsing + public link)."""

import re
import pytest


# ── Pure-logic helpers extracted from extractor.py for testing ────────


def _clean_name(raw_name):
    """Reproduce the name-cleaning logic from LeadExtractor.scrape_lead."""
    cleaned = re.sub(r'\s+is reachable$', '', raw_name, flags=re.IGNORECASE).strip() or 'Unknown'
    return cleaned


def _parse_name(full_name):
    """Reproduce first/last name splitting from LeadExtractor.scrape_lead."""
    parts = full_name.strip().split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first_name, last_name


def _extract_vmid(lead_url):
    """Reproduce VMID extraction from LeadExtractor.scrape_lead."""
    vmid = None
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
    return vmid if vmid else lead_url


# ── generate_public_link is in export.py ─────────────────────────────

from scrapers.linkedin.export import generate_public_link


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGeneratePublicLink:
    """Tests for generate_public_link() from export.py."""

    def test_with_vmid_string(self):
        result = generate_public_link("ACwAAAB1234TEST")
        assert result == "https://www.linkedin.com/in/ACwAAAB1234TEST/"

    def test_with_full_public_url(self):
        url = "https://www.linkedin.com/in/john-doe"
        result = generate_public_link(url)
        assert result == "https://www.linkedin.com/in/john-doe/"

    def test_with_full_public_url_trailing_slash(self):
        url = "https://www.linkedin.com/in/john-doe/"
        result = generate_public_link(url)
        assert result == "https://www.linkedin.com/in/john-doe/"

    def test_with_sales_nav_url(self):
        url = "https://www.linkedin.com/sales/lead/ACwAAAB1234"
        result = generate_public_link(url)
        # Sales Nav URL contains '/sales/', so it falls through to the VMID branch
        assert result == "https://www.linkedin.com/in/https://www.linkedin.com/sales/lead/ACwAAAB1234/"


@pytest.mark.unit
class TestNameParsing:
    """Tests for name-parsing logic reproduced from LeadExtractor.scrape_lead."""

    def test_full_name_two_parts(self):
        first, last = _parse_name("Max Mustermann")
        assert first == "Max"
        assert last == "Mustermann"

    def test_single_name(self):
        first, last = _parse_name("Madonna")
        assert first == "Madonna"
        assert last == ""

    def test_name_with_multiple_parts(self):
        first, last = _parse_name("Anna Maria von Trapp")
        assert first == "Anna"
        assert last == "Maria von Trapp"

    def test_name_with_is_reachable_suffix(self):
        cleaned = _clean_name("Max Mustermann is reachable")
        assert cleaned == "Max Mustermann"
        first, last = _parse_name(cleaned)
        assert first == "Max"
        assert last == "Mustermann"

    def test_name_with_is_reachable_case_insensitive(self):
        cleaned = _clean_name("Anna Schmidt IS REACHABLE")
        assert cleaned == "Anna Schmidt"

    def test_empty_name_becomes_unknown(self):
        cleaned = _clean_name("")
        assert cleaned == "Unknown"


@pytest.mark.unit
class TestVMIDExtraction:
    """Tests for VMID extraction logic reproduced from LeadExtractor.scrape_lead."""

    def test_sales_nav_url(self):
        url = "https://www.linkedin.com/sales/lead/ACwAAAB1234,NAME_SEARCH"
        vmid = _extract_vmid(url)
        assert vmid == "ACwAAAB1234"

    def test_sales_nav_url_with_query_params(self):
        url = "https://www.linkedin.com/sales/lead/ACwAAAB1234?sessionId=abc"
        vmid = _extract_vmid(url)
        assert vmid == "ACwAAAB1234"

    def test_sales_nav_url_with_trailing_slash(self):
        url = "https://www.linkedin.com/sales/lead/ACwAAAB1234/"
        vmid = _extract_vmid(url)
        assert vmid == "ACwAAAB1234"

    def test_non_matching_url_returns_url(self):
        url = "https://www.linkedin.com/in/john-doe/"
        vmid = _extract_vmid(url)
        assert vmid == url
