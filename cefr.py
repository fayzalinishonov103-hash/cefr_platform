"""CEFR helpers.

NOTE: thresholds below come from public (unofficial) sources for the
Uzbekistan national CEFR exam: 75-point scale, C1 65-75, B2 51-64, B1 38-50.
Verify against the official specification before production use.
The raw->scaled step is a PLACEHOLDER (linear); replace later with a
difficulty-weighted (Rasch-style) conversion.
"""
LEVEL_BANDS = [(65, "C1"), (51, "B2"), (38, "B1")]


def raw_to_scaled(raw: int, max_raw: int) -> float:
    """Provisional linear conversion of a raw score to the 0-75 scale."""
    return round(75 * raw / max_raw, 1) if max_raw else 0.0


def scaled_to_level(scaled: float) -> str:
    """Map a 0-75 scaled score to a CEFR label."""
    for minimum, level in LEVEL_BANDS:
        if scaled >= minimum:
            return level
    return "B1 dan past"
