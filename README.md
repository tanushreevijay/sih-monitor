# SIH 2026 Problem Statement Monitor

A small desktop app that scrapes [sih.gov.in/sih2026PS](https://sih.gov.in/sih2026PS)
for problem statements and their submitted-idea counts, lets you pick which
ones to watch, and refreshes them on a timer.

## Setup

```bash
cd sih_monitor
pip install -r requirements.txt
python3 app.py
```

Requires Python 3.9+ with `tkinter` available:
- **Windows / macOS:** bundled with the standard python.org installer, nothing extra to do.
- **Linux:** if `python3 -c "import tkinter"` errors, install it separately, e.g.
  `sudo apt install python3-tk` (Debian/Ubuntu) or the equivalent for your distro.

## How it works

- **All problem statements** (left pane): the full list scraped from the
  portal. Type in the search box to filter by title, organization, or PS
  number. Select one or more rows and click **Add Selected to Monitor →**
  (or double-click a row).
- **Monitoring** (right pane): your watchlist, with the current idea count
  and the change (Δ) since the last refresh, highlighted green when it goes
  up. Select rows and click **← Remove Selected** to stop watching them.
- **Auto-refresh**: on by default, every 10 minutes (adjustable in the top
  bar). **Refresh Now** triggers an immediate fetch. The status bar shows
  when the last refresh happened and a countdown to the next one.
- Your watchlist, the last full scrape, and idea-count history are saved to
  `~/.sih_monitor/` (`watchlist.json`, `ps_cache.json`, `history.json`), so
  reopening the app restores everything, including your selections.

## Notes on scraping sih.gov.in

- The scraper (`scraper.py`) parses the `#dataTablePS` table on the live
  page with `requests` + `BeautifulSoup`, using a normal browser User-Agent
  and a short retry-with-backoff loop.
- If `sih.gov.in` changes its page layout, `scraper.py` will raise a clear
  `ScrapeError` naming the problem (e.g. table not found) rather than
  silently returning nothing — check the terminal / status bar for that
  message and update the column indices in `parse()` if needed. You can
  run `python3 scraper.py` on its own to test the scraper in isolation.
- Government portals sometimes rate-limit or temporarily block automated
  traffic. If refreshes start failing repeatedly, try increasing the
  refresh interval, or check that you can load the page normally in a
  browser from the same network.
- Please keep the refresh interval reasonable (10+ minutes) — hitting a
  government server every few seconds isn't good etiquette and is more
  likely to get you rate-limited anyway.

## Project layout

```
sih_monitor/
  app.py           # Tkinter GUI + auto-refresh loop
  scraper.py        # requests + BeautifulSoup scraper for sih.gov.in
  storage.py        # JSON persistence (watchlist, cache, history)
  requirements.txt
```
