"""Core scraping engine for LinkedIn Sales Navigator."""


def __getattr__(name):
    if name == 'LinkedInScraper':
        from scrapers.linkedin.runner import LinkedInScraper
        return LinkedInScraper
    raise AttributeError(f"module 'scrapers.linkedin' has no attribute {name!r}")
