"""
SeaBird CTD Calibration PDF Parser

Parses SeaBird calibration certificate PDFs and returns sensor metadata
and calibration coefficients as a dict or single-row pandas DataFrame,
ready for comparison with XMLCON files parsed by XMLCONParser.
"""

import re
import pdfplumber
import pandas as pd
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Sensor type map: title-string fragment -> canonical sensor_type name
# (matches the sensor_type values used in XMLCONParser)
# ---------------------------------------------------------------------------
# Longer/more-specific keys MUST appear before any key that is a prefix of
# another (e.g. "SBE 43" before "SBE 4", "SBE 38" before "SBE 3")
SENSOR_TYPE_MAP = {
    "SBE 43":  "OxygenSensor",
    "SBE 38":  "OxygenSensor",
    "SBE 63":  "OxygenSensor",
    "SBE 18":  "OxygenSensor",
    "SBE 4C":  "ConductivitySensor",   # some certs use "SBE 4C"
    "SBE 4":   "ConductivitySensor",
    "SBE 3":   "TemperatureSensor",
    "SBE 9":   "PressureSensor",
    "ECO AFL": "FluoroWetlabECO_AFL_FL_Sensor",
    "FLNTU":   "FLNTU",          # characterisation sheet covers CHL + NTU together
    "CDOM":    "FluoroWetlabCDOM_Sensor",
    "CSTAR":   "WET_LabsCStar",
    "CDOM":    "FluoroWetlabCDOM_Sensor",
    "PAR":     "PAR_BiosphericalLicorChelseaSensor",
}

# Regex patterns for coefficient lines: "g = -1.01643901e+001"
# Non-anchored so it catches mid-line coefficients (e.g. AD590M, Slope, CPcor)
# that share a line with the left-column coefficient on pressure/conductivity sheets.
# Negative lookbehind prevents matching digits inside numeric values.
_COEFF_RE = re.compile(
    r"(?<![.\d])([A-Za-z][A-Za-z0-9_]*)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)",
)

# Nominal markers – values flagged as "(nominal)" in the certificate.
# We still store the number, but record which names are nominal.
_NOMINAL_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9_]*)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\(nominal\)",
    re.IGNORECASE,
)


def _extract_text(filepath: str) -> str:
    """Return the full text of a PDF using pdfplumber."""
    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def _detect_sensor_type(text: str) -> str:
    """Return the canonical sensor_type string, or the raw title fragment."""
    upper = text.upper()
    for fragment, canonical in SENSOR_TYPE_MAP.items():
        if fragment.upper() in upper:
            return canonical
    # Fall back to the raw title line if nothing matched
    for line in text.splitlines():
        if "CALIBRATION DATA" in line.upper():
            # e.g. "SBE 4 CONDUCTIVITY CALIBRATION DATA"
            return line.strip().replace("CALIBRATION DATA", "").strip()
    return "Unknown"


def _parse_serial_number(text: str) -> str | None:
    """Extract serial number from 'SENSOR SERIAL NUMBER: 3202'."""
    m = re.search(r"SENSOR SERIAL NUMBER[:\s]+(\S+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_calibration_date(text: str) -> str | None:
    """Extract calibration date from 'CALIBRATION DATE: 16-Feb-24'."""
    m = re.search(r"CALIBRATION DATE[:\s]+(\S+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


# Matches "E nominal = 0.036" — E is a calibrated value flagged as nominal
_E_NOMINAL_RE = re.compile(
    r"\bE\s+nominal\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)

# Lines to strip before coefficient parsing: equation/formula lines, table
# header/data rows, and axis label lines that contain single-letter variables
_STRIP_LINE_RE = re.compile(
    r"^.*(?:"
    r"ml/l\s*=|"                # equation lines  e.g. "Oxygen (ml/l) = Soc * ..."
    r"S/m\s*=|"                 # conductivity equation line
    r"Residual|"                 # residual definition line
    r"Oxsol|"                    # oxygen saturation formula line
    r"instrument output|"        # variable-definition line
    r"\bOxygen\b.*\bSoc\b|"  # formula line starting with Oxygen
    r"^\s*[\d.+-]"             # data table rows (start with a digit)
    r").*$",
    re.IGNORECASE | re.MULTILINE,
)

# Strips just the "E nominal = <val>" token from a line, not the whole line,
# so that Tau20 and H3 on the same line are still captured by _COEFF_RE
_E_NOMINAL_TOKEN_RE = re.compile(
    r"\bE\s+nominal\s*=\s*[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?",
    re.IGNORECASE,
)


def _strip_non_coefficient_lines(text: str) -> str:
    """Remove equation/formula/data-table lines, and scrub the E nominal token."""
    text = _STRIP_LINE_RE.sub("", text)
    text = _E_NOMINAL_TOKEN_RE.sub("", text)
    return text


def _parse_coefficients(text: str) -> dict[str, Any]:
    """
    Extract all coefficient key=value pairs from the text.

    Returns a dict mapping lower-case coefficient names to floats.
    Nominal values are included normally; the set of nominal names is
    available in the '_nominal' key of the returned dict.
    """
    # Collect nominal coefficient names for reference
    nominal_names = {m.group(1).lower() for m in _NOMINAL_RE.finditer(text)}

    # Strip equation/formula lines and data table rows before parsing so that
    # single-letter tokens in those lines (T, S, V, K, P, E, etc.) are not
    # mistaken for calibration coefficients
    coeff_text = _strip_non_coefficient_lines(text)

    coeffs: dict[str, Any] = {}
    for m in _COEFF_RE.finditer(coeff_text):
        name = m.group(1).lower()
        # Skip tokens that are clearly formula/axis symbols even after stripping
        if name in {"v", "s", "k"}:
            continue
        # First occurrence wins (coefficient block appears before data table)
        if name not in coeffs:
            try:
                coeffs[name] = float(m.group(2))
            except ValueError:
                coeffs[name] = m.group(2)

    # Handle "E nominal = <val>" (oxygen sheets) — "nominal" is part of the
    # label in the PDF, not a value qualifier, so _NOMINAL_RE won't match it.
    # Must run after coeffs is initialised so we can write into it.
    for m in _E_NOMINAL_RE.finditer(text):
        nominal_names.add("e")
        coeffs["e"] = float(m.group(1))

    coeffs["_nominal"] = nominal_names
    return coeffs


# ---------------------------------------------------------------------------
# Date normalisation
# Cal sheets use varied date formats; normalise to ISO 8601 (YYYY-MM-DD)
# so comparisons with XMLCON dates are format-independent.
# ---------------------------------------------------------------------------
import datetime

_DATE_FORMATS = [
    "%d-%b-%y",    # 12-Nov-24
    "%d-%b-%Y",    # 16-Feb-2024
    "%B %d, %Y",   # August 2, 2022  (long month name)
    "%b %d, %Y",   # Aug 2, 2022
    "%m/%d/%Y",    # 11/2016  (partial — handled separately)
    "%Y-%m-%d",    # already ISO
]


def _normalise_date(date_str: str) -> str:
    """
    Try to parse date_str with known formats and return YYYY-MM-DD.
    Returns the original string unchanged if no format matches.
    """
    if not date_str:
        return date_str
    cleaned = date_str.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned   # give up, return as-is


# ---------------------------------------------------------------------------
# FLNTU Characterisation Sheet parser
# Layout is completely different from SBE cal sheets — tabular rows with
# labelled rows rather than "key = value" coefficient blocks.
# ---------------------------------------------------------------------------

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


def _parse_flntu(text: str, filepath: str) -> list[dict[str, Any]]:
    """
    Parse an FLNTU characterisation sheet and return a list of two dicts,
    one for the fluorometer (CHL) and one for the turbidity meter (NTU).

    Each dict uses the same schema as parse_cal_pdf():
        source_file, sensor_type, serial_number, calibration_date,
        scale_factor, dark_counts (analog values), _nominal (empty set)
    """
    # Serial number and date
    sn_m = _FLNTU_SN_RE.search(text)
    serial_number = sn_m.group(1).strip() if sn_m else None

    date_m = _FLNTU_DATE_RE.search(text)
    raw_date = date_m.group(1).strip() if date_m else None
    calibration_date = _normalise_date(raw_date) if raw_date else None

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


# ---------------------------------------------------------------------------
# CDOM Characterisation Sheet parser (scanned PDF — requires OCR)
# Layout is similar to FLNTU but with three Analog Range columns.
# The XMLCON uses Analog Range 1 values (scale_factor and vblank).
# ---------------------------------------------------------------------------

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

    If Tesseract is not on your PATH, set cal_pdf_parser.TESSERACT_CMD to the
    full path of the tesseract executable before calling this function, e.g.:

        import cal_pdf_parser
        cal_pdf_parser.TESSERACT_CMD = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    """
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import ImageFilter, ImageEnhance

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    images = convert_from_path(filepath, dpi=dpi)
    pages = []
    for img in images:
        img = img.convert("L")
        img = img.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = img.point(lambda x: 0 if x < 150 else 255, "1")
        pages.append(pytesseract.image_to_string(img, config="--psm 6"))
    return "\n".join(pages)


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
    calibration_date = _normalise_date(raw_date) if raw_date else None

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
    parse_cal_pdf(), containing scale_factor and vblank (both Analog
    Range 1 values, matching the XMLCON convention).

    Parameters
    ----------
    filepath : str
        Path to the CDOM characterisation sheet PDF.
    tesseract_cmd : str, optional
        Full path to the tesseract executable. Only needed if tesseract is
        not on your system PATH (common on Windows). Can also be set once
        at module level via ``cal_pdf_parser.TESSERACT_CMD`` instead of passing
        it on every call.
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


def parse_cal_pdf(filepath: str) -> dict[str, Any]:
    """
    Parse a SeaBird calibration PDF and return a flat dictionary of all
    relevant fields.

    For FLNTU characterisation sheets, which contain both a fluorometer and
    a turbidity sensor, use parse_flntu_pdf() instead — it returns a list
    of two dicts, one per sensor.

    Keys returned:
        source_file       - basename of the PDF
        sensor_type       - canonical type string (matches XMLCONParser)
        serial_number     - sensor serial number (string)
        calibration_date  - calibration date (string, normalised to YYYY-MM-DD)
        <coeff_name>      - float value for each coefficient (lower-case)
        _nominal          - set of coefficient names flagged as nominal

    Parameters
    ----------
    filepath : str
        Path to the calibration PDF file.

    Returns
    -------
    dict
    """
    text = _extract_text(filepath)

    result: dict[str, Any] = {
        "source_file":       Path(filepath).name,
        "sensor_type":       _detect_sensor_type(text),
        "serial_number":     _parse_serial_number(text),
        "calibration_date":  _normalise_date(_parse_calibration_date(text) or ""),
    }

    coeffs = _parse_coefficients(text)
    result.update(coeffs)

    return result


def parse_flntu_pdf(filepath: str) -> list[dict[str, Any]]:
    """
    Parse an FLNTU Characterisation Sheet PDF.

    Returns a list of two dicts — index 0 is the fluorometer (CHL /
    FluoroWetlabECO_AFL_FL_Sensor), index 1 is the turbidity meter (NTU /
    TurbidityMeter).  Each dict has the same schema as parse_cal_pdf().

    Parameters
    ----------
    filepath : str
        Path to the FLNTU characterisation sheet PDF.

    Returns
    -------
    list[dict]
    """
    text = _extract_text(filepath)
    return _parse_flntu(text, filepath)


def parse_cal_pdf_to_df(filepath: str) -> pd.DataFrame:
    """
    Parse a SeaBird calibration PDF and return a single-row DataFrame.

    The '_nominal' key is dropped (it's a set and doesn't fit a tabular
    column naturally).  Nominal flags are preserved in the dict form via
    parse_cal_pdf() if needed.

    Parameters
    ----------
    filepath : str
        Path to the calibration PDF file.

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame with one column per field/coefficient.
    """
    data = parse_cal_pdf(filepath)
    data.pop("_nominal", None)
    return pd.DataFrame([data])


# ---------------------------------------------------------------------------
# Sensor-specific coefficient name remapping
# SeaBird cal PDFs use bare names (g, h, i, j, cpcor, ctcor) while the XMLCON
# stores conductivity coefficients under the eq1_ prefix.  Map cal names ->
# XMLCON column names here so comparisons align automatically.
# ---------------------------------------------------------------------------
_CAL_TO_XMLCON_NAMES: dict[str, dict[str, str]] = {
    "ConductivitySensor": {
        "g":     "eq1_g",
        "h":     "eq1_h",
        "i":     "eq1_i",
        "j":     "eq1_j",
        "cpcor": "eq1_c_pcor",
        "ctcor": "eq1_c_tcor",
    },
    "PressureSensor": {
        # These appear mid-line on pressure cal sheets; XMLCON stores them
        # as top-level columns (no eq prefix)
        "ad590m":  "ad590_m",
        "ad590b":  "ad590_b",
        # slope and offset are already correct names in both cal PDF and XMLCON
    },
    "OxygenSensor": {
        # SBE 43 / Sea-Bird 2007 equation coefficients live under eq1_
        # PDF name -> XMLCON column name
        "soc":     "eq1_soc",
        "voffset": "eq1_offset",   # PDF uses Voffset; XMLCON uses offset
        "a":       "eq1_a",
        "b":       "eq1_b",
        "c":       "eq1_c",
        "d1":      "eq1_d1",
        "d2":      "eq1_d2",
        "e":       "eq1_e",
        "tau20":   "eq1_tau20",
        "h1":      "eq1_h1",
        "h2":      "eq1_h2",
        "h3":      "eq1_h3",
        # d0 is a firmware constant, not in the cal PDF — omitted intentionally
    },
}


def _remap_cal_coeffs(
    cal_coeffs: dict[str, Any],
    sensor_type: str,
) -> dict[str, Any]:
    """Rename cal PDF coefficient keys to match XMLCON column names."""
    mapping = _CAL_TO_XMLCON_NAMES.get(sensor_type, {})
    return {mapping.get(k, k): v for k, v in cal_coeffs.items()}


# ---------------------------------------------------------------------------
# Convenience: compare a parsed cal dict to a single XMLCON sensor row
# ---------------------------------------------------------------------------

def compare_cal_to_xmlcon(
    cal: dict[str, Any],
    xmlcon_row: pd.Series,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """
    Compare a parsed calibration certificate against one row of an XMLCON
    DataFrame (from XMLCONParser).

    Parameters
    ----------
    cal : dict
        Output of parse_cal_pdf().
    xmlcon_row : pd.Series
        A single row from XMLCONParser.df (e.g. parser.get_sensor(1)).
    tolerance : float
        Absolute tolerance for floating-point comparisons.

    Returns
    -------
    dict with keys:
        serial_match      - bool: serial numbers agree
        date_match        - bool: calibration dates agree
        coeff_matches     - dict of coefficients that match
        coeff_mismatches  - dict of coefficients that differ
                            {name: {cal: <val>, xmlcon: <val>}}
        coeff_only_in_cal - list of coefficient names in cal but not XMLCON
        coeff_only_in_xmlcon - list of coefficient names in XMLCON but not cal
    """
    skip = {"source_file", "sensor_type", "serial_number",
            "calibration_date", "_nominal"}

    raw_coeffs = {k: v for k, v in cal.items()
                  if k not in skip and not k.startswith("_")}

    # Remap cal PDF coefficient names to match XMLCON column naming conventions
    cal_coeffs = _remap_cal_coeffs(raw_coeffs, cal.get("sensor_type", ""))

    # XMLCON coefficient columns (non-metadata, non-null)
    meta_cols = {"sensor_index", "sensor_type", "sensor_id",
                 "serial_number", "calibration_date"}
    xmlcon_coeffs = {
        col: xmlcon_row[col]
        for col in xmlcon_row.index
        if col not in meta_cols and pd.notna(xmlcon_row[col])
    }

    matches = {}
    mismatches = {}

    for name, cal_val in cal_coeffs.items():
        if name not in xmlcon_coeffs:
            continue
        xmlcon_val = xmlcon_coeffs[name]
        try:
            if abs(float(cal_val) - float(xmlcon_val)) <= tolerance:
                matches[name] = cal_val
            else:
                mismatches[name] = {"cal": cal_val, "xmlcon": xmlcon_val}
        except (TypeError, ValueError):
            if str(cal_val) == str(xmlcon_val):
                matches[name] = cal_val
            else:
                mismatches[name] = {"cal": cal_val, "xmlcon": xmlcon_val}

    only_in_cal = [k for k in cal_coeffs if k not in xmlcon_coeffs]
    only_in_xmlcon = [k for k in xmlcon_coeffs if k not in cal_coeffs]

    # Serial number comparison: strip leading zeros, and also check whether
    # the XMLCON value is a suffix of the cal PDF value (e.g. XMLCON stores
    # "1963" while the PDF serial is "FLCDRTD-1963")
    cal_sn = str(cal.get("serial_number", "")).lstrip("0")
    xmlcon_sn = str(xmlcon_row.get("serial_number", "")).lstrip("0")
    serial_match = (cal_sn == xmlcon_sn) or cal_sn.endswith(xmlcon_sn) or xmlcon_sn.endswith(cal_sn)

    # Date comparison: normalise both sides to ISO before comparing so that
    # "4/21/2022" and "2022-04-21" are treated as equal
    cal_date = _normalise_date(str(cal.get("calibration_date", "")).strip())
    xmlcon_date = _normalise_date(str(xmlcon_row.get("calibration_date", "")).strip())
    date_match = (cal_date.lower() == xmlcon_date.lower())

    return {
        "serial_match":           serial_match,
        "date_match":             date_match,
        "coeff_matches":          matches,
        "coeff_mismatches":       mismatches,
        "coeff_only_in_cal":      only_in_cal,
        "coeff_only_in_xmlcon":   only_in_xmlcon,
    }


def print_comparison(
    cal: dict[str, Any],
    xmlcon_row: pd.Series,
    tolerance: float = 1e-8,
) -> None:
    """Print a human-readable comparison report."""
    result = compare_cal_to_xmlcon(cal, xmlcon_row, tolerance)

    sn_tag  = "✓" if result["serial_match"]  else "✗"
    dt_tag  = "✓" if result["date_match"]    else "✗"

    print(f"\nCalibration certificate : {cal.get('source_file')}")
    print(f"Sensor type             : {cal.get('sensor_type')}")
    print(f"{sn_tag} Serial number  : cal={cal.get('serial_number')}  "
          f"xmlcon={xmlcon_row.get('serial_number')}")
    print(f"{dt_tag} Cal date       : cal={cal.get('calibration_date')}  "
          f"xmlcon={xmlcon_row.get('calibration_date')}")
    print("=" * 70)

    if result["coeff_matches"]:
        print(f"✓ Matching coefficients ({len(result['coeff_matches'])}):")
        for k, v in sorted(result["coeff_matches"].items()):
            print(f"    {k:12s} = {v}")

    if result["coeff_mismatches"]:
        print(f"\n✗ MISMATCHED coefficients ({len(result['coeff_mismatches'])}):")
        for k, vals in sorted(result["coeff_mismatches"].items()):
            print(f"    {k:12s}  cal={vals['cal']}  xmlcon={vals['xmlcon']}")

    if result["coeff_only_in_cal"]:
        print(f"\n⚠ In cal PDF only : {result['coeff_only_in_cal']}")

    if result["coeff_only_in_xmlcon"]:
        print(f"⚠ In XMLCON only  : {result['coeff_only_in_xmlcon']}")


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    pdf_path = "/mnt/user-data/uploads/SBE_4_C3202_16Feb24.pdf"

    print("── Parsed calibration certificate ──────────────────────────────────")
    cal = parse_cal_pdf(pdf_path)
    for k, v in cal.items():
        if k != "_nominal":
            print(f"  {k:20s}: {v}")
    print(f"  {'_nominal':20s}: {cal['_nominal']}")

    print("\n── Single-row DataFrame ─────────────────────────────────────────────")
    df = parse_cal_pdf_to_df(pdf_path)
    print(df.T.to_string(header=False))
