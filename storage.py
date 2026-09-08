"""
Local JSON persistence for the SIH monitor app.

Everything lives under ~/.sih_monitor/ so it survives app restarts:

  watchlist.json  - list of PS numbers the user has chosen to monitor
  ps_cache.json   - last full scrape (so the app has data to show instantly
                     on startup, before the first refresh completes)
  history.json    - last-seen idea count per PS number, used to compute the
                     "change since last refresh" delta shown in the UI
"""
import json
from pathlib import Path

APP_DIR = Path.home() / ".sih_monitor"
APP_DIR.mkdir(exist_ok=True)

WATCHLIST_FILE = APP_DIR / "watchlist.json"
CACHE_FILE = APP_DIR / "ps_cache.json"
HISTORY_FILE = APP_DIR / "history.json"


def _read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_watchlist() -> list[str]:
    return _read_json(WATCHLIST_FILE, [])


def save_watchlist(ps_numbers) -> None:
    _write_json(WATCHLIST_FILE, sorted(set(ps_numbers)))


def load_cache() -> list[dict]:
    return _read_json(CACHE_FILE, [])


def save_cache(records: list[dict]) -> None:
    _write_json(CACHE_FILE, records)


def load_history() -> dict:
    return _read_json(HISTORY_FILE, {})


def save_history(history: dict) -> None:
    _write_json(HISTORY_FILE, history)
