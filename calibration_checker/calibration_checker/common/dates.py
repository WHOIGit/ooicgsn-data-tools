"""Shared calibration-date normalisation helper."""

import datetime

# Cal sheets across instrument vendors use varied date formats; normalise to
# ISO 8601 (YYYY-MM-DD) so comparisons are format-independent.
DEFAULT_DATE_FORMATS = [
    "%d-%b-%y",    # 12-Nov-24
    "%d-%b-%Y",    # 16-Feb-2024
    "%B %d, %Y",   # August 2, 2022  (long month name)
    "%b %d, %Y",   # Aug 2, 2022
    "%m/%d/%Y",    # 11/2/2016
    "%d.%m.%Y",    # 03.03.2025  (Aanderaa/DOSTA style)
    "%Y-%m-%d",    # already ISO
]


def normalise_date(date_str: str, formats=None) -> str:
    """
    Try to parse date_str with known formats and return YYYY-MM-DD.
    Returns the original string unchanged if no format matches.
    """
    if not date_str:
        return date_str
    cleaned = date_str.strip()
    for fmt in (formats or DEFAULT_DATE_FORMATS):
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned  # give up, return as-is
