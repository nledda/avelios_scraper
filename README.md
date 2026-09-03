# LinkedIn Scraper

Extracts leads from LinkedIn Sales Navigator and exports them to Excel.
Built with Selenium, using randomised delays and session reuse to stay
within normal usage patterns.

## Scrapers

| Module | Entry point | Purpose |
|---|---|---|
| `scrapers/linkedin/` | `linkedin_scraper.py` | Scrapes leads from Sales Navigator saved searches |
| `scrapers/network/` | `network_scraper.py` | Scrapes connections from profile URLs to map intro paths |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
LINKEDIN_EMAIL=you@example.com
LINKEDIN_PASSWORD=your-password
LINKEDIN_SEARCH_ID=https://www.linkedin.com/sales/search/people?savedSearchId=...
```

Quote the password if it contains `#`, spaces, or shell metacharacters.

## Usage

```bash
python linkedin_scraper.py          # scrape leads
python network_scraper.py           # scrape connections (needs profiles.txt)
./auto_scraper.sh start             # run on a schedule
./auto_scraper.sh status            # check scheduler
```

To scrape multiple saved searches, create `config/lists.json`; without it the
scraper falls back to the single `LINKEDIN_SEARCH_ID`.

### Docker

```bash
docker compose up --build
```

## Output

Excel files land in `output/linkedin/`, with these columns:

| Column | Notes |
|---|---|
| Produkt-/Projektname | |
| Name / Vorname / Nachname | |
| LinkedIn Profil | Public profile URL containing the VMID, trailing `/` |
| Leadquelle | Always `LinkedIn` |
| Owner, Komitee | Empty unless set per list |

## Tests

```bash
pytest tests/ -m unit          # fast, no network
pytest tests/ -m e2e           # requires real credentials
```

The e2e test reads credentials from the environment, not from `.env` — export
them first, or add `load_dotenv()` to the test module.

## Notes

- `data/` holds runtime state (cookies, history, stats) and is gitignored.
- The scraper commits state to git after each run; check which branch you are on.
- Login failures write a screenshot and page dump to `data/linkedin/` for debugging.
