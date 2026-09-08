"""
Scraper for Smart India Hackathon 2026 problem statements.

Source: https://sih.gov.in/sih2026PS
The page renders an HTML table (id="dataTablePS") with one row per problem
statement. Column order (0-indexed <td>s within each row):

    0  S.No.
    1  Organization
    2  Title (contains a hidden modal with description/department/etc.)
    3  Category (Software / Hardware)
    4  PS Number (e.g. SIH26083)
    5  Submitted idea count
    6  Theme
    7  Deadline for idea submission

If sih.gov.in changes its markup, parse() will raise ScrapeError with a
clear message rather than silently returning nothing.
"""
import re
import time

import requests
from bs4 import BeautifulSoup

URL = "https://sih.gov.in/sih2026PS"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# The site's HTML is UTF-8 that got double-encoded through CP1252 in a few
# places (mojibake) - fix the common sequences so titles/descriptions read
# cleanly.
MOJIBAKE_FIX = {
    "\u00e2\u20ac\u201c": "\u2013",  # en dash
    "\u00e2\u20ac\u201d": "\u2014",  # em dash
    "\u00e2\u20ac\u2122": "\u2019",  # right single quote
    "\u00e2\u20ac\u02dc": "\u2018",  # left single quote
    "\u00e2\u20ac\u0153": "\u201c",  # left double quote
    "\u00e2\u20ac\u0152": "\u201d",  # right double quote
    "\u00e2\u20ac\u00a6": "\u2026",  # ellipsis
    "\u00c2\u00b0": "\u00b0",        # degree sign
}

MIN_RECORDS = 50  # sanity floor - if a scrape returns fewer, treat as broken


class ScrapeError(Exception):
    """Raised when the page can't be fetched or parsed as expected."""


def _fix_text(text: str) -> str:
    for bad, good in MOJIBAKE_FIX.items():
        text = text.replace(bad, good)
    return text.strip()


def fetch_html(attempts: int = 3, timeout: int = 30) -> str:
    """GET the SIH portal page, retrying with backoff on failure."""
    last_err = None
    for i in range(attempts):
        try:
            resp = requests.get(URL, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:  # noqa: BLE001 - want to retry on anything
            last_err = e
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
    raise ScrapeError(
        f"Could not reach {URL} after {attempts} attempts ({last_err}). "
        "If this keeps happening, the site may be rate-limiting or "
        "blocking automated requests - try again in a few minutes, or "
        "lower the refresh frequency."
    )


def parse(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table", id="dataTablePS")
    if not table:
        raise ScrapeError(
            "Could not find the problem statement table (#dataTablePS) in "
            "the page. sih.gov.in may have changed its layout - the "
            "scraper needs updating."
        )
    body = table.find("tbody")
    rows = body.find_all("tr") if body else []

    records = []
    for tr in rows:
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 8:
            continue

        title_cell = tds[2]
        link = title_cell.find("a")
        title = _fix_text(link.get_text(strip=True) if link else title_cell.get_text(strip=True))

        ideas_raw = _fix_text(tds[5].get_text(strip=True))
        submitted_match = re.match(r"^\s*([\d,]+)\s*/", ideas_raw)
        if submitted_match:
            ideas = int(submitted_match.group(1).replace(",", ""))
        else:
            digits = re.sub(r"[^\d]", "", ideas_raw)
            ideas = int(digits) if digits else None

        records.append({
            "ps_number": _fix_text(tds[4].get_text(strip=True)),
            "title": title,
            "org": _fix_text(tds[1].get_text(strip=True)),
            "category": _fix_text(tds[3].get_text(strip=True)),
            "theme": _fix_text(tds[6].get_text(strip=True)),
            "deadline": _fix_text(tds[7].get_text(strip=True)),
            "ideas": ideas,
            "ideas_raw": ideas_raw,
        })

    if len(records) < MIN_RECORDS:
        raise ScrapeError(
            f"Only parsed {len(records)} problem statements (expected at "
            f"least {MIN_RECORDS}). The page may not have loaded fully."
        )
    return records


def fetch_problem_statements() -> list[dict]:
    """Fetch and parse the current problem statement list in one call."""
    return parse(fetch_html())


if __name__ == "__main__":
    # Quick manual test: python3 scraper.py
    recs = fetch_problem_statements()
    print(f"Parsed {len(recs)} problem statements. First few:")
    for r in recs[:5]:
        print(f"  {r['ps_number']:>10}  ideas={r['ideas']!s:>5}  {r['title'][:60]}")
