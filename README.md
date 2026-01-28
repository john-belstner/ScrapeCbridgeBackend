# ScrapeCbridgeBackend

A Python script for scraping information from a DMR CBridge front and backend web pages.

## Project Overview

Python utilities used to monitor the CBridge web interface for new users not in a local database, enriches their information via the DMR radioid.net API, and persists the data to local CSV files.

## Commands

```bash
# Run the public CallWatch scraper (no login required)
python3 scrape.py

# Run the backend scraper with authentication (scrapes all pages)
python3 scrape_full.py --user USERNAME --password PASSWORD

# Run via cron wrapper (logs to syslog with tag "aztrbo")
./aztrbo

# Interactive development
jupyter notebook SCRAPE.ipynb
```

## Architecture

**Two Scraping Modes:**

| Feature | scrape.py (Public) | scrape_full.py (Backend) |
|---------|-------------------|-------------------------|
| Authentication | None required | Username/password |
| URL | `/CallWatch` | `/` → login → `/mainwelcome` |
| Max Records | 200 (single table) | 10,000 (100 pages × 100 rows) |
| Data Source | Live call monitor | Historical call database |
| Frame Handling | `CallWatchBody` frame | `leftmainpagebar` + `main` frames |

**Data Flow:**
1. **Web Scraping** - Selenium with Brave browser (headless mode) scrapes the CallWatch system, extracting radio IDs from HTML tables
2. **Filtering** - Radio IDs are filtered by network affiliation ("AZ-TRBONET") and talk group ("MWave" / Group ID 310564)
3. **Comparison** - New radio IDs are compared against `code_plug.csv` to identify unknown users
4. **API Enrichment** - New IDs are queried against `https://database.radioid.net/api/dmr/user/?id={radio_id}` to fetch callsign, name, and state
5. **Persistence** - New AZ-TRBONET users are appended to `code_plug.csv` (main database) and `add_users.csv` (audit trail); MWave users are tracked separately in `mwg_users.csv`

**Key Files:**
- `scrape.py` - Production script (public CallWatch, no auth required)
- `scrape_full.py` - Backend scraper (requires login, scrapes all paginated records)
- `SCRAPE.ipynb` - Development notebook for testing changes
- `aztrbo` - Shell wrapper for cron execution
- `code_plug.csv` - Main database (columns: RADIO_ID, CALLSIGN, FIRST_NAME, STATE)
- `add_users.csv` - Log of newly discovered AZ-TRBONET users
- `mwg_users.csv` - Log of MWave talk group users

## Dependencies

- selenium (with ChromeDriver at `/usr/bin/chromedriver` for Brave browser at `/usr/bin/brave-browser`)
- pandas
- numpy
- requests

No `requirements.txt` exists; dependencies must be installed manually.

## Development Notes

- The Jupyter notebook serves as the primary development environment; working changes are promoted to `scrape.py`
- The scraper filters for "AZ-TRBONET" network affiliations and "MWave" talk groups
- CSV files use deduplication before writes to prevent duplicate entries
- Browser runs in headless mode with `--no-sandbox` and `--disable-dev-shm-usage` flags for stability

## Backend Scraper (scrape_full.py)

The backend scraper (`scrape_full.py`) provides authenticated access to the full call records table, scraping up to 10,000 historical records compared to the 200-row limit of the public CallWatch interface.

**Authentication:**
- Form-based login at `http://184.191.128.77:42420`
- Form fields: `name="user"`, `name="pass"`, button `name="Login"`
- Credentials passed via `--user` and `--password` command-line arguments

**Navigation Flow:**
1. Login → redirects to `/mainwelcome` (frameset page)
2. Switch to `leftmainpagebar` frame → click "Calls" button
3. Switch to `main` frame → click "AZ-TRBONET" button
4. Arrives at DetailCalls page with paginated table

**Pagination:**
- Page size dropdown (`selectpagesize`): 10-100 records per page
- Page number dropdown (`selectpagenumber`): up to 100 pages
- Script sets page size to 100 and iterates through all available pages
- Stops when a page returns no data

**Table Column Mapping:**

| Data | CallWatch (scrape.py) | Backend (scrape_full.py) |
|------|----------------------|--------------------------|
| Radio ID | Column 4 (parsed from alias) | Column 7 (direct ID) |
| Group | Column 5 (name: "MWave") | Column 10 (ID: "310564" = MWave) |
| Network | Column 7 | Column 12 |

**Data Processing:**
1. Scrape radio ID, group ID, and network from each table row
2. Filter for MWave group (ID 310564) and AZ-TRBONET network
3. Compare against `code_plug.csv` to identify new users
4. Enrich new users via radioid.net API (callsign, name, state)
5. Update CSV files with deduplication

**Usage:**
```bash
# Standard usage (headless)
python3 scrape_full.py --user USERNAME --password PASSWORD

# With visible browser for debugging
python3 scrape_full.py --user USERNAME --password PASSWORD --no-headless
```

**Output:**
- Prints progress for each page scraped
- Reports total records collected, new users found, and MWave users tracked
- Updates `code_plug.csv`, `add_users.csv`, and `mwg_users.csv`
