# price-tracker-scraper

[![CI](https://github.com/Aleksa5000/price-tracker-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/Aleksa5000/price-tracker-scraper/actions/workflows/ci.yml)

A Python scraper that tracks product prices over time, reports every drop and increase, and pings Slack or Discord when a price falls.

## The problem it solves

Checking competitor or supplier prices by hand is slow, and nobody notices a 20% drop the day it happens. This tool visits a product catalogue on a schedule (cron, Task Scheduler), keeps the full price history in a local database, and tells you exactly what changed since the last run. Point it at your own suppliers, competitors or wish-list items and you stop missing price moves.

The demo targets [books.toscrape.com](https://books.toscrape.com), a site built for scraping practice. The parsing layer is a single small function, so adapting it to another shop is a short job.

## Features

- Scrapes title, price, availability, star rating and URL, and follows pagination (`--pages N`)
- Polite by design: custom User-Agent, delay between requests, retry with backoff on failure
- Every run is stored in SQLite, so you get a complete price history, not just the latest snapshot
- Detects price changes against the previous run and prints a drops/increases report
- Exports the latest snapshot to CSV
- Optional webhook alert (Slack/Discord-compatible) when a price falls below a threshold or by X%; silently skipped if no webhook is configured
- Offline test suite that runs on saved HTML fixtures

## Example output

```text
$ python -m tracker scrape --pages 2
Run #1: stored 40 products from 2 page(s).
No price changes since the previous run.

$ python -m tracker scrape --pages 2 --drop-pct 10
Run #2: stored 40 products from 2 page(s).
DROPS (3)
  A Light in the Attic                          £ 64.71 -> £ 51.77  -20.0%
  Sapiens: A Brief History of Humankind         £ 67.79 -> £ 54.23  -20.0%
  The Boys in the Boat: Nine Americans and Thei £ 28.25 -> £ 22.60  -20.0%
INCREASES (2)
  Shakespeare's Sonnets                         £ 18.59 -> £ 20.66  +11.1%
  Soumission                                    £ 45.09 -> £ 50.10  +11.1%

$ python -m tracker export out.csv
Exported 40 rows to out.csv
```

The demo site never changes its prices, so between the two runs above I edited five stored prices in the SQLite file to simulate a price move. Everything else is real output.

## Quickstart

```bash
git clone https://github.com/Aleksa5000/price-tracker-scraper.git
cd price-tracker-scraper
python -m pip install -r requirements.txt

python -m tracker scrape --pages 3      # scrape 3 listing pages and store a run
python -m tracker report                # show changes in the latest run
python -m tracker export out.csv        # export the latest snapshot
```

Run `scrape` on a schedule to build up history. Options for `scrape`:

| Option | Meaning |
|---|---|
| `--pages N` | Number of listing pages (default 1) |
| `--delay S` | Seconds between requests (default 1) |
| `--threshold P` | Alert if a price drops below P |
| `--drop-pct X` | Alert if a price drops by at least X percent |

The global option `--db FILE` (before the command) sets the SQLite file, default `prices.db`.

## Configuration

Alerts use one environment variable (see `.env.example`):

| Variable | Description |
|---|---|
| `ALERT_WEBHOOK_URL` | Slack or Discord incoming-webhook URL. If unset, alerts are skipped silently. |

```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."
python -m tracker scrape --pages 3 --drop-pct 10
```

The payload carries both `text` (Slack) and `content` (Discord).

## Running the tests

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

Tests need no network access: they parse saved HTML in `tests/fixtures` and use a temporary database.

## Tech stack

Python 3.11+, requests, BeautifulSoup 4, SQLite (standard library), argparse, pytest, GitHub Actions.

## License

MIT

---

Need something similar? Contact me on Upwork: Aleksa Djorovic, Python automation.
