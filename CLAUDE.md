# LinkedIn Scraper

## Project overview

This scraper extracts leads from LinkedIn Sales Navigator and saves them to Excel files. It uses Selenium with random delays to avoid detection.

### Output file structure

| Column | Notes |
|---|---|
| Produkt-/Projektname | |
| Name | |
| Vorname | |
| Nachname | |
| LinkedIn Profil | Must be the public profile URL (not Sales Navigator), must contain the VMID, must end with `/` |
| Leadquelle | Always `LinkedIn` |
| Owner | Always empty |
| Komitee | Always empty |

### Tech stack

- Python 3.12
- Selenium + webdriver-manager
- pandas + openpyxl for Excel output
- Dependencies in `requirements.txt`

### Directory structure

```
config/          — user-editable config (lists.json, filters)
data/            — runtime state (scraper state, history, stats)
output/          — scraped lead exports (Excel files)
logs/            — all log files
scrapers/        — scraper modules (linkedin, network)
reporting/       — stats and health analytics
tests/           — test scripts
```

---

## Git workflow

### Branch structure

- **`main`** — production-ready code. Never commit directly to `main`.
- **`dev`** — integration branch. All feature branches merge into `dev` via pull request.
- `main` is updated from `dev` only through reviewed and approved pull requests (CI/CD pipeline will be added later).

### For every change (mandatory)

1. **Create a feature branch** from `dev`:
   ```
   git checkout dev && git pull origin dev
   git checkout -b <type>/<short-description>
   ```
   Branch naming: `feature/`, `fix/`, `refactor/`, `docs/`, `test/` prefix + kebab-case description.
   Example: `feature/add-alumni-filter`, `fix/vmid-extraction`

2. **Work on the feature branch.** Commit early and often with clear messages.

3. **Test before pushing.** Run relevant tests and verify the scraper works as expected. Document what was tested in the PR description.

4. **Push and create a pull request into `dev`:**
   ```
   git push -u origin <branch-name>
   gh pr create --base dev
   ```

5. **Never push directly to `main` or `dev`.** All changes go through pull requests.

### Commit messages

Use short, descriptive commit messages in English. Format:
```
<type>: <what changed and why>
```
Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Examples:
- `feat: add pagination support for large lead lists`
- `fix: correct VMID extraction for profiles with special characters`

---

## What must never be committed

- `output/` — scraped data
- `data/linkedin/cookies.pkl` — browser session
- `.env` — credentials and secrets
- `logs/` — log files
- `*.log`, `*.pid` — log and process files
- `__pycache__/`, `*.pyc` — Python cache
- `.DS_Store` — macOS metadata

If any of these files show up in `git status`, add them to `.gitignore` before proceeding.

---

## CI/CD

_To be defined. A deployment pipeline will be added later — this section will be updated with build, test, and deploy instructions._
