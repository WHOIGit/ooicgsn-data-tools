"""
CDOM (WET Labs ECO CDOM fluorometer) characterisation-sheet parser.

Split out from the CTD module: like FLORT, the CDOM sensor is bolted onto
the CTD frame and its coefficients also land in the frame's XMLCON, but
it's calibrated and tracked as its own instrument, so it gets its own
parser module here. It's also the only sensor in this toolkit whose
characterisation sheet is a scanned image (no embedded text layer), so it's
the only one that needs OCR.

Layout is similar to FLORT/FLNTU but with three Analog Range columns; the
XMLCON uses Analog Range 1 values (scale_factor and vblank).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..common.dates import normalise_date
from ..common.ocr import ocr_pdf_text

# S/N pattern for CDOM sheets: "S/N: FLCDRTD-1963"
_CDOM_SN_RE = re.compile(r"S/N[:\s]+([A-Z0-9-]+)", re.IGNORECASE)

# Date pattern for CDOM sheets: "Date: 4/21/2022"
_CDOM_DATE_RE = re.compile(
    r"Date[:\s]+(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-[A-Za-z]+-\d{2,4}|[A-Za-z]+ \d+,\s*\d{4})",
    re.IGNORECASE,
)

# Match data rows: label followed by 3+ numeric columns
# "Dark Counts  0.054  0.025  0.090 V  46 counts"
# "Scale Factor (SF)  23  47  111 ppb/V  0.0284 ppb/count"
# Captures: label, first numeric (Range 1), second (Range 2), third (Range 4)
_CDOM_ROW_RE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 ()/.-]+?)\s+"
    r"(?P<r1>[+-]?\d+(?:[.,]\d+)?)\s+"    # Analog Range 1
    r"(?P<r2>[+-]?\d+(?:[.,]\d+)?)\s+"    # Analog Range 2
    r"(?P<r4>[+-]?\d+(?:[.,]\d+)?)",       # Analog Range 4 (default)
    re.MULTILINE,
)

# Optional: set this to the full path of the tesseract executable if it is
# not on your system PATH (common on Windows).
# e.g. TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD: str | None = None


def _ocr_pdf(filepath: str, dpi: int = 500) -> str:
    """Rasterise a PDF with pdf2image and return OCR text via pytesseract.

    If Tesseract is not on your PATH, set cdom_pdf_parser.TESSERACT_CMD to
    the full path of the tesseract executable before calling this function,
    e.g.:

        from cruise_tools.cdom import cdom_pdf_parser
        cdom_pdf_parser.TESSERACT_CMD = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    """
    return ocr_pdf_text(filepath, dpi=dpi, tesseract_cmd=TESSERACT_CMD)


# Targeted extractor for Scale Factor row — OCR noise makes the generic row
# regex unreliable for this value.  After the "Scale Factor" label, skip any
# punctuation/spaces, then grab the first integer (= Analog Range 1).
_CDOM_SF_RE = re.compile(
    r"Scale\s+Factor\s*\(?SF\)?\s*[.\s-]*(\d+)",
    re.IGNORECASE,
)


def _clean_ocr_number(s: str) -> float:
    """Normalise OCR artefacts in a numeric string and return a float."""
    # Replace commas used as decimal separators
    s = s.replace(",", ".")
    # Strip any trailing non-numeric characters
    s = re.sub(r"[^0-9.]", "", s)
    return float(s)


def _parse_cdom(text: str, filepath: str) -> dict[str, Any]:
    """
    Parse an ECO CDOM Fluorometer Characterisation Sheet (scanned PDF).

    Returns a single dict with:
        scale_factor  — Analog Range 1 value  (matches XMLCON scale_factor)
        vblank        — Analog Range 1 dark counts  (matches XMLCON vblank)
    """
    sn_m = _CDOM_SN_RE.search(text)
    serial_number = sn_m.group(1).strip() if sn_m else None

    date_m = _CDOM_DATE_RE.search(text)
    raw_date = date_m.group(1).strip() if date_m else None
    calibration_date = normalise_date(raw_date) if raw_date else None

    # Dark Counts: use the generic row regex — this row is reliable
    vblank = None
    for m in _CDOM_ROW_RE.finditer(text):
        label = m.group("label").strip().lower()
        if "dark" in label:
            vblank = _clean_ocr_number(m.group("r1"))
            break

    # Scale Factor: use the targeted regex to skip OCR noise after the label
    scale_factor = None
    sf_m = _CDOM_SF_RE.search(text)
    if sf_m:
        scale_factor = float(sf_m.group(1))

    return {
        "source_file":      Path(filepath).name,
        "sensor_type":      "FluoroWetlabCDOM_Sensor",
        "serial_number":    serial_number,
        "calibration_date": calibration_date,
        "scale_factor":     scale_factor,
        "vblank":           vblank,
        "_nominal":         set(),
    }


def parse_cdom_pdf(filepath: str, tesseract_cmd: str | None = None) -> dict[str, Any]:
    """
    Parse an ECO CDOM Fluorometer Characterisation Sheet PDF.

    This document type is typically a scanned image, so OCR is used
    automatically. Returns a single dict with the same schema as
    ``cruise_tools.ctd.parse_cal_pdf()``, containing scale_factor and
    vblank (both Analog Range 1 values, matching the XMLCON convention).

    Parameters
    ----------
    filepath : str
        Path to the CDOM characterisation sheet PDF.
    tesseract_cmd : str, optional
        Full path to the tesseract executable. Only needed if tesseract is
        not on your system PATH (common on Windows). Can also be set once
        at module level via ``cdom_pdf_parser.TESSERACT_CMD`` instead of
        passing it on every call.
        Example: r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

    Returns
    -------
    dict
    """
    global TESSERACT_CMD
    if tesseract_cmd:
        TESSERACT_CMD = tesseract_cmd
    text = _ocr_pdf(filepath)
    return _parse_cdom(text, filepath)
