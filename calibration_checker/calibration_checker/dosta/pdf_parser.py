"""
DOSTA (Aanderaa Optode 4831 / 4330 oxygen sensor) calibration certificate
parser.

Unlike the SeaBird cal certs and the CTDMO `.cal` file, the Aanderaa
certificate has no "key = value" lines at all — every coefficient lives in
a table. This parser reads the certificate's tables directly (via
pdfplumber) rather than regex-matching lines of text.

Only two of the certificate's coefficient blocks make it into the CI
calibration CSV for this asset class (`CGINS-DOSTAD-xxxxx__<date>.csv`):

  * ``SVUFoilCoef`` (7 values)  -> ``CC_csv``        (Stern-Volmer-Uchida
    foil coefficients used by OOI's oxygen concentration algorithm)
  * ``ConcCoef``    (2 values)  -> ``CC_conc_coef``  ([offset, slope])

``TempCoef`` and ``PhaseCoef`` are on the certificate but are NOT part of
the CI CSV for this asset class (OOI's processing doesn't consume them
directly), so this parser doesn't extract them — extracting values the CI
CSV was never meant to contain would just generate noisy false
"missing_in_ci" rows on every comparison.
"""

from __future__ import annotations

import re
import datetime
from pathlib import Path
from typing import Any, Optional

import pdfplumber
import pandas as pd

# Row labels (first cell of a table row) this parser looks for, and the CI
# CSV coefficient name each one maps to.
_ROW_TO_CC = {
    "svufoilcoef": "CC_csv",
    "conccoef":    "CC_conc_coef",
}

_SERIAL_RE   = re.compile(r"Serial no[:\s]+(\S+)", re.IGNORECASE)
_CALDATE_RE  = re.compile(r"Calibration date[:\s]+([\d./-]+)", re.IGNORECASE)
_PRODUCT_RE  = re.compile(r"Product[:\s]+(\S+)", re.IGNORECASE)
_FIRMWARE_RE = re.compile(r"Firmware Version\s*[:\s]*\s*([\d.]+)", re.IGNORECASE)

_DATE_FORMATS = ["%d.%m.%Y", "%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d"]


def _normalise_date(date_str: str) -> str:
    cleaned = (date_str or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return cleaned


def _extract_all(filepath: str) -> tuple[str, list[list[list[str]]]]:
    """Return (full_text, tables_per_page) for the whole PDF."""
    text_parts = []
    tables: list[list[list[str]]] = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
            tables.extend(page.extract_tables())
    return "\n".join(text_parts), tables


def _find_coef_row(tables: list[list[list[str]]], label: str) -> Optional[list[float]]:
    """
    Scan every extracted table for a row whose first cell matches `label`
    (case-insensitive), and return the remaining non-empty cells as floats,
    in order.
    """
    target = label.strip().lower()
    for table in tables:
        for row in table:
            if not row or row[0] is None:
                continue
            if row[0].strip().lower() != target:
                continue
            values = []
            for cell in row[1:]:
                if cell is None or str(cell).strip() == "":
                    continue
                try:
                    values.append(float(cell))
                except ValueError:
                    continue
            return values
    return None


def parse_dosta_pdf(filepath: str) -> pd.DataFrame:
    """
    Parse an Aanderaa Optode (DOSTA) multipoint calibration certificate PDF.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file.
        `name` is `CC_csv` (7-element list — SVU foil coefficients) or
        `CC_conc_coef` (2-element list — [offset, slope]), matching the CI
        calibration CSV naming for the DOSTAD asset class. `value` is a
        Python list of floats in each case.
    """
    text, tables = _extract_all(filepath)
    source_file = Path(filepath).name

    sn_m = _SERIAL_RE.search(text)
    serial = sn_m.group(1).strip() if sn_m else None

    rows: list[dict[str, Any]] = []
    for label, cc_name in _ROW_TO_CC.items():
        values = _find_coef_row(tables, label)
        if values is None:
            continue
        rows.append({
            "serial": serial,
            "name": cc_name,
            "value": values,
            "source_file": source_file,
        })

    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, product, cal date, firmware."""
    text, _ = _extract_all(filepath)

    sn_m = _SERIAL_RE.search(text)
    date_m = _CALDATE_RE.search(text)
    prod_m = _PRODUCT_RE.search(text)
    fw_m = _FIRMWARE_RE.search(text)

    return {
        "serial":           sn_m.group(1).strip() if sn_m else None,
        "product":          prod_m.group(1).strip() if prod_m else None,
        "calibration_date": _normalise_date(date_m.group(1)) if date_m else None,
        "firmware_version": fw_m.group(1).strip() if fw_m else None,
    }
