"""
SeaBird CTD Calibration PDF Parser

Parses SeaBird calibration certificate PDFs and returns sensor metadata
and calibration coefficients as a dict or single-row pandas DataFrame,
ready for comparison with XMLCON files parsed by XMLCONParser.
"""

import re
import pandas as pd
from pathlib import Path
from typing import Any

from ..common.pdf_text import extract_text as _extract_text
from ..common.dates import normalise_date as _normalise_date


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
    "CSTAR":   "WET_LabsCStar",
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



def parse_cal_pdf(filepath: str) -> dict[str, Any]:
    """
    Parse a SeaBird calibration PDF and return a flat dictionary of all
    relevant fields.

    For FLNTU/FLORT characterisation sheets (fluorometer + turbidity), use
    ``calibration_checker.flort.parse_flort_pdf()`` instead — it returns a list of
    two dicts, one per sensor. For CDOM characterisation sheets, use
    ``calibration_checker.cdom.parse_cdom_pdf()``.

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
