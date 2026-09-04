"""
FLORT (WET Labs / Sea-Bird ECO FLNTU — combined fluorometer + turbidity
sensor) characterisation-sheet parser.

Split out from the CTD module: FLNTU is bolted onto the CTD frame and its
coefficients also land in the frame's XMLCON, but it's calibrated and
tracked as its own instrument, so it gets its own parser module here.

Layout is completely different from SBE cal sheets — tabular rows with
labelled rows rather than "key = value" coefficient blocks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..common.pdf_text import extract_text
from ..common.dates import normalise_date

# Serial number on FLNTU sheets: "S/N: FLNTURTD-7730"
_FLNTU_SN_RE = re.compile(r"S/N[:\s]+(\S+)", re.IGNORECASE)

# Calibration date on FLNTU sheets: "Date: August 2, 2022"
_FLNTU_DATE_RE = re.compile(
    r"Date[:\s]+([A-Za-z]+ \d+,\s*\d{4}|\d{1,2}[/-][A-Za-z0-9]+[/-]\d{2,4})",
    re.IGNORECASE,
)

# Row pattern: "Dark Counts 0.057 V 49 counts"
# pdfplumber collapses multi-space column gaps to single spaces, so we just
# match: label (greedy text), then the first numeric token (= analog value).
_FLNTU_ROW_RE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 ()/.-]+?)\s+(?P<analog>[+-]?\d+(?:\.\d+)?)\s+\S+",
    re.MULTILINE,
)


def _parse_flntu_section(section_text: str) -> dict[str, float]:
    """
    Extract Dark Counts (analog) and Scale Factor (analog) from one
    FLNTU section block (Chlorophyll or Turbidity).
    """
    result = {}
    for m in _FLNTU_ROW_RE.finditer(section_text):
        label = m.group("label").strip().lower()
        analog_val = float(m.group("analog"))
        if "dark" in label:
            result["dark_counts_analog"] = analog_val
        elif "scale factor" in label or label.startswith("sf"):
            result["scale_factor_analog"] = analog_val
    return result


def parse_flort_pdf(filepath: str) -> list[dict[str, Any]]:
    """
    Parse a FLORT/FLNTU characterisation sheet and return a list of two
    dicts, one for the fluorometer (CHL) and one for the turbidity meter
    (NTU).

    Each dict uses the same schema as ``calibration_checker.ctd.parse_cal_pdf()``:
        source_file, sensor_type, serial_number, calibration_date,
        scale_factor, dark_counts (analog values), _nominal (empty set)
    """
    text = extract_text(filepath)

    sn_m = _FLNTU_SN_RE.search(text)
    serial_number = sn_m.group(1).strip() if sn_m else None

    date_m = _FLNTU_DATE_RE.search(text)
    raw_date = date_m.group(1).strip() if date_m else None
    calibration_date = normalise_date(raw_date) if raw_date else None

    source_file = Path(filepath).name

    # Split on the turbidity section header to isolate each block
    chl_split = re.split(r"Nephelometric Turbidity", text, flags=re.IGNORECASE)
    chl_text = chl_split[0]
    ntu_text = chl_split[1] if len(chl_split) > 1 else ""

    chl_vals = _parse_flntu_section(chl_text)
    ntu_vals = _parse_flntu_section(ntu_text)

    chl_record = {
        "source_file":      source_file,
        "sensor_type":      "FluoroWetlabECO_AFL_FL_Sensor",
        "serial_number":    serial_number,
        "calibration_date": calibration_date,
        # XMLCON column names
        "scale_factor":     chl_vals.get("scale_factor_analog"),
        "vblank":           chl_vals.get("dark_counts_analog"),
        "_nominal":         set(),
    }

    ntu_record = {
        "source_file":      source_file,
        "sensor_type":      "TurbidityMeter",
        "serial_number":    serial_number,
        "calibration_date": calibration_date,
        # XMLCON column names
        "scale_factor":     ntu_vals.get("scale_factor_analog"),
        "dark_voltage":     ntu_vals.get("dark_counts_analog"),
        "_nominal":         set(),
    }

    return [chl_record, ntu_record]


# Backwards-compatible alias (this used to live in calibration_checker.ctd as
# parse_flntu_pdf before FLORT was split into its own module).
parse_flntu_pdf = parse_flort_pdf
