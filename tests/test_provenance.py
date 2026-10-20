"""Fails if any number that feeds a calculation lacks a recorded source."""
import re
from pathlib import Path

import pandas as pd

from config.settings import PROJECT_ROOT, SOURCES_MD
from margins import MARGINS_CSV, RULES_CSV

SPECS = PROJECT_ROOT / "data" / "contract_specs.csv"


def _sources_text():
    return SOURCES_MD.read_text(encoding="utf-8")


def test_spec_and_rule_rows_have_source_and_date_and_are_listed():
    text = _sources_text()
    for path in (SPECS, RULES_CSV):
        t = pd.read_csv(path)
        assert t["source_url"].str.startswith("https://").all()
        assert t["as_of"].notna().all()
        for p in t["parameter"]:
            assert p in text, f"{p} missing from SOURCES.md"


def test_every_verified_margin_row_is_sourced_and_listed():
    text = _sources_text()
    m = pd.read_csv(MARGINS_CSV, dtype=str)
    used = m[m["verified"].str.lower() == "true"]
    assert used["source_url"].str.startswith("https://").all()
    assert used["maintenance"].notna().all()
    for _, r in used.iterrows():
        assert r["effective_date"] in text, f"margin row {r['effective_date']} not in SOURCES.md"


def test_no_hard_coded_duration_or_dv01_in_code():
    # DV01/duration must come from the regression, never a literal.
    pat = re.compile(r"(dv01|duration)\s*=\s*[0-9]", re.I)
    for f in PROJECT_ROOT.glob("*.py"):
        assert not pat.search(f.read_text(encoding="utf-8")), f"literal DV01 in {f.name}"


def test_downloaded_datasets_are_listed():
    text = _sources_text()
    for series in ("ZN=F", "DGS10", "DFEDTARU"):
        assert series in text
