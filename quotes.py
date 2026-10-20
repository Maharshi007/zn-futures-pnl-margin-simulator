"""Convert ZN prices between decimals and the market's '110-16+' notation.

Notation: <points>-<32nds>[+]. '+' adds half a 32nd.
    110-16+  = 110 + 16.5/32 = 110.515625
"""
import math
import re

_PATTERN = re.compile(r"^\s*(\d+)-(\d{1,2})(\+?)\s*$")


def to_32nds(price: float) -> str:
    """Decimal price -> '110-16+' string, rounded to the nearest half-32nd.

    Intuition: ZN's minimum tick is half a 32nd (0.015625), so every real
    settlement price lies on that grid. We count half-32nds as an integer
    first (price * 64) so floating-point noise cannot produce '110-31++'.
    """
    if price < 0:
        raise ValueError("ZN prices are positive")
    halves = round(price * 64)               # number of half-32nds
    whole, rem = divmod(halves, 64)           # rem in [0, 63]
    thirty_seconds, half = divmod(rem, 2)
    return f"{whole}-{thirty_seconds:02d}{'+' if half else ''}"


def from_32nds(text: str) -> float:
    """'110-16+' -> 110.515625.

    Intuition: split into whole points and 32nds, add 0.5 for '+', divide
    the 32nds by 32. Rejects 32nds >= 32 because '110-32' would really be 111.
    """
    m = _PATTERN.match(text)
    if not m:
        raise ValueError(f"Not a 32nds quote: {text!r}")
    whole, n32, plus = int(m.group(1)), int(m.group(2)), m.group(3)
    if n32 >= 32:
        raise ValueError(f"32nds part must be 0-31, got {n32}")
    return whole + (n32 + (0.5 if plus else 0.0)) / 32


def is_on_tick(price: float, tick: float) -> bool:
    """True if price is a whole number of ticks (within float tolerance)."""
    n = price / tick
    return math.isclose(n, round(n), abs_tol=1e-6)
