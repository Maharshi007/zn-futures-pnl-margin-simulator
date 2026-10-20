import pytest

from config.contract_specs import load_spec, load_spec_table
from quotes import from_32nds, is_on_tick, to_32nds


def test_tick_value_identity():
    s = load_spec()
    assert s["tick_size"] * s["multiplier"] == pytest.approx(s["tick_value"])


def test_multiplier_derived_from_face_value():
    s = load_spec()
    assert s["multiplier"] == s["face_value"] / 100


def test_every_spec_row_is_sourced_and_verified():
    t = load_spec_table()
    assert t["source_url"].str.startswith("https://www.cmegroup.com").all()
    assert t["as_of"].notna().all()
    assert (t["verified"].astype(str).str.lower() == "true").all()


@pytest.mark.parametrize("text,dec", [
    ("110-16+", 110.515625),
    ("110-16", 110.5),
    ("110-00", 110.0),
    ("110-00+", 110.015625),
    ("119-31+", 119.984375),
    ("99-08", 99.25),
])
def test_32nds_round_trip(text, dec):
    assert from_32nds(text) == dec
    assert to_32nds(dec) == text


def test_to_32nds_rounds_to_nearest_half_32nd_and_carries():
    assert to_32nds(119.9999) == "120-00"      # carries into the next point
    assert to_32nds(110.51) == "110-16+"       # nearest half-32nd


@pytest.mark.parametrize("bad", ["110-32", "110.5", "abc", "110-"])
def test_from_32nds_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        from_32nds(bad)


def test_is_on_tick():
    assert is_on_tick(110.515625, 0.015625)
    assert not is_on_tick(110.51, 0.015625)
