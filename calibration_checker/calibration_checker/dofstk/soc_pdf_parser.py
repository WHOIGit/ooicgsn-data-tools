"""
DOFST-K (SBE 43F) oxygen calibration certificate PDF parser.

The certificate re-states most of the same coefficients as the `.cal`
file (A, B, C, E, Foffset, Tau20), at lower printed precision — those are
NOT what this parser extracts, since the `.cal` file is the authoritative
source for them (see ``calibration_checker.dofstk.cal_parser``).

What this parser is actually for: SBE 43 sensors sometimes get a
post-calibration "Soc adjustment" — a corrected oxygen-signal-slope value,
fit against reference samples, that supersedes the factory Soc baked into
the `.cal` file. That adjusted value is documented ONLY on the
certificate, printed as e.g. "Soc = 3.0753e-04 (adj)". This is the value
the CI calibration CSV's ``CC_oxygen_signal_slope`` actually wants.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.pdf_text import extract_text
from ..common.dates import normalise_date

_SERIAL_RE = re.compile(
    r"SERIAL\s*NUMBE\S*(.*?)(?:SBE\s*\d|\n)", re.IGNORECASE | re.DOTALL
)
_MODEL_RE = re.compile(r"SBE\s*0*(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"CALIBRATION DATE[:\s]+(\S+)", re.IGNORECASE)

# Matches both "Soc = 3.0753e-04 (adj)" and a plain "Soc = 3.0753e-04"
# with no adjustment marker (uncalibrated-adjustment certificates) —
# either way, the certificate's Soc is what CC_oxygen_signal_slope wants.
_SOC_RE = re.compile(
    r"Soc\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(\(adj\))?",
    re.IGNORECASE,
)


def _extract_serial(text: str) -> str | None:
    """
    Pull the digits out of the 'SENSOR SERIAL NUMBER: nnnn' field.

    On at least some Sea-Bird certificates, pdfplumber's text extraction
    interleaves this field character-by-character with an overlapping
    text run elsewhere on the page (observed: the footer's
    'www.seabird.com', e.g. yielding 'w2.7s2e5abird.com' for serial
    '2725'). Rather than match the field as a clean token, this grabs
    everything between the 'SERIAL NUMBER' label and the next anchor
    ('SBE <model>' or a newline) and strips everything but the digits —
    which reconstructs the real serial even when it's been shuffled in
    with other text.
    """
    m = _SERIAL_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return digits or None


def parse_soc_pdf(filepath: str) -> pd.DataFrame:
    """
    Parse an SBE 43(F) oxygen calibration certificate and return a
    single-row DataFrame with just CC_oxygen_signal_slope (the
    certificate's Soc — adjusted, if the certificate shows an adjustment).

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file. One row:
        name='CC_oxygen_signal_slope', value=<Soc from the certificate>.
    """
    text = extract_text(filepath)
    source_file = Path(filepath).name

    serialno = _extract_serial(text)
    model_m = _MODEL_RE.search(text)
    model = model_m.group(1) if model_m else None
    serial = f"{model}-{serialno}" if (model and serialno) else serialno

    soc_m = _SOC_RE.search(text)
    if soc_m is None:
        raise ValueError(f"Could not find a 'Soc = ...' value in {source_file}")
    soc = float(soc_m.group(1))
    is_adjusted = soc_m.group(2) is not None

    row = {
        "serial": serial,
        "name": "CC_oxygen_signal_slope",
        "value": soc,
        "source_file": source_file,
    }
    df = pd.DataFrame([row], columns=["serial", "name", "value", "source_file"])
    df.attrs["soc_is_adjusted"] = is_adjusted
    return df


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, cal date, and whether Soc was adjusted."""
    text = extract_text(filepath)

    serialno = _extract_serial(text)
    model_m = _MODEL_RE.search(text)
    model = model_m.group(1) if model_m else None
    serial = f"{model}-{serialno}" if (model and serialno) else serialno

    date_m = _DATE_RE.search(text)
    cal_date = normalise_date(date_m.group(1)) if date_m else None

    soc_m = _SOC_RE.search(text)
    soc_is_adjusted = bool(soc_m and soc_m.group(2))

    return {
        "serial":           serial,
        "calibration_date": cal_date,
        "soc_is_adjusted":  soc_is_adjusted,
    }
