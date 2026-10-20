"""Project-wide paths, default dates and secret loading.

Every other module imports paths from here so there is exactly one place
that knows where data lives (README NFR2: one config, not scattered constants).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# --- Paths ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # cached downloads, git-ignored
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SOURCES_MD = DATA_DIR / "SOURCES.md"

# --- Default simulation window (2022 Fed hiking cycle) --------------------
# These are user choices, not market data, so they need no source.
DEFAULT_START = "2022-01-03"
DEFAULT_END = "2022-12-30"


def ensure_dirs() -> None:
    """Create the data/raw and outputs folders if they are missing.

    Intuition: code should never crash just because a fresh clone has no
    cache folder yet; creating folders is safe and idempotent.
    """
    for d in (RAW_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_fred_api_key() -> str:
    """Read FRED_API_KEY from the .env file (never from source code).

    Intuition: keys in code end up on GitHub. python-dotenv copies the
    lines of .env into environment variables, and we read them from there.
    Raises a clear error instead of failing later inside fredapi.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    key = (os.getenv("FRED_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError(
            "FRED_API_KEY missing. Add a line FRED_API_KEY=your_key to .env "
            "(get a free key at https://fredaccount.stlouisfed.org/apikeys)."
        )
    return key


if __name__ == "__main__":
    ensure_dirs()
    print("Project root :", PROJECT_ROOT)
    print("Raw cache    :", RAW_DIR, "exists =", RAW_DIR.exists())
    print("Outputs      :", OUTPUT_DIR, "exists =", OUTPUT_DIR.exists())
    print("Default dates:", DEFAULT_START, "->", DEFAULT_END)
    key = get_fred_api_key()
    # Never print the key itself, only enough to confirm it loaded.
    looks_ok = len(key) == 32 and key.isalnum() and key == key.lower()
    print(f"FRED_API_KEY : loaded ({len(key)} chars), "
          f"standard 32-char lowercase format = {looks_ok}")
