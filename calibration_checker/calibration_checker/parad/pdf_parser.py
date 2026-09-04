"""
PARAD-K (Biospherical Instruments QSP-2200 PAR sensor) calibration
certificate PDF parser.

The certificate reports dry and wet calibration factors, dark voltage,
supply current, immersion coefficient, and a NIST-traceable lamp
irradiance figure — but the CI calibration CSV for this asset class only
wants two of those:

  * the sensor's dark voltage           -> CC_dark_offset
  * the *wet* calibration factor         -> CC_scale_wet
    (the dry factor is not used — this sensor is deployed submerged, so
    the wet-immersion calibration is what matters operationally)

Everything else on the certificate (dry factor, immersion coefficient,
lamp irradiance, standard lamp ID, operator, ...) is left out on purpose,
the same way DOSTA's TempCoef/PhaseCoef and FLORT's fixed sensor constants
are left out — pulling values the CI CSV doesn't use would just generate
noisy "missing_in_ci" rows on every comparison.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.pdf_text import extract_text
from ..common.dates import normalise_date
from ..common.ocr import ocr_pdf_text

_SERIAL_RE = re.compile(r"Serial Number[:\s]+(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"Calibration Date[:\s]+(\S+)", re.IGNORECASE)
_MODEL_RE = re.compile(r"Model Number[:\s]+(\S+)", re.IGNORECASE)

_DARK_VOLTAGE_RE = re.compile(
    r"Sensor Dark Voltage[:\s]+([+-]?\d+(?:\.\d+)?)\s*mV", re.IGNORECASE
)
_WET_FACTOR_RE = re.compile(
    r"Wet Calibration Factor[:\s]+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"\s*Volts\s*/\s*\(quanta",
    re.IGNORECASE,
)

# Optional: set this to the full path of the tesseract executable if it is
# not on your system PATH (common on Windows). Only used if a given
# certificate turns out to be a scanned image rather than a text-based PDF.
# e.g. TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD: str | None = None


def _get_text(filepath: str) -> str:
    """
    Return the certificate's text, using the embedded text layer when
    there is one. Some PARAD-K certificates are scanned images with no
    text layer at all (unlike the more common text-based ones), so this
    falls back to OCR automatically rather than failing outright.
    """
    text = extract_text(filepath)
    if text.strip():
        return text
    return ocr_pdf_text(filepath, tesseract_cmd=TESSERACT_CMD)


def parse_parad_pdf(filepath: str, tesseract_cmd: str | None = None) -> pd.DataFrame:
    """
    Parse a PARAD-K (QSP-2200) calibration certificate PDF. Falls back to
    OCR automatically if the certificate turns out to be a scanned image
    with no embedded text layer.

    Parameters
    ----------
    filepath : str
    tesseract_cmd : str, optional
        Full path to the tesseract executable, only needed if a scanned
        certificate is encountered and tesseract isn't on PATH. Can also
        be set once at module level via
        ``cruise_tools.parad.pdf_parser.TESSERACT_CMD``.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file. Two rows:
        CC_dark_offset (mV) and CC_scale_wet
        (Volts / (quanta/(cm^2*s))).
    """
    global TESSERACT_CMD
    if tesseract_cmd:
        TESSERACT_CMD = tesseract_cmd

    text = _get_text(filepath)
    source_file = Path(filepath).name

    sn_m = _SERIAL_RE.search(text)
    serial = sn_m.group(1).strip() if sn_m else None

    dark_m = _DARK_VOLTAGE_RE.search(text)
    if dark_m is None:
        raise ValueError(f"Could not find 'Sensor Dark Voltage' in {source_file}")
    dark_offset = float(dark_m.group(1))

    wet_m = _WET_FACTOR_RE.search(text)
    if wet_m is None:
        raise ValueError(f"Could not find 'Wet Calibration Factor' in {source_file}")
    scale_wet = float(wet_m.group(1))

    rows: list[dict[str, Any]] = [
        {"serial": serial, "name": "CC_dark_offset", "value": dark_offset,
         "source_file": source_file},
        {"serial": serial, "name": "CC_scale_wet", "value": scale_wet,
         "source_file": source_file},
    ]
    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, model, cal date."""
    text = _get_text(filepath)

    sn_m = _SERIAL_RE.search(text)
    date_m = _DATE_RE.search(text)
    model_m = _MODEL_RE.search(text)

    return {
        "serial":           sn_m.group(1).strip() if sn_m else None,
        "model":            model_m.group(1).strip() if model_m else None,
        "calibration_date": normalise_date(date_m.group(1), formats=["%m/%d/%y", "%m/%d/%Y"])
                              if date_m else None,
    }
