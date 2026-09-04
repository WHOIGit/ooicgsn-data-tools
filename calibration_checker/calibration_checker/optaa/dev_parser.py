"""
OPTAA (WET Labs AC-S — spectral absorption/attenuation meter) `.dev`
calibration file parser.

This is the most structurally complex instrument in this toolkit: instead
of a handful of scalar coefficients, the AC-S carries per-wavelength
calibration data across ~85 wavelengths, plus a temperature-correction
*matrix* for each of the two channels (absorption and attenuation) —
85 wavelengths x 36 temperature bins each. Those two matrices are large
enough that the CI calibration CSV doesn't inline them as JSON arrays like
it does for everything else; instead the CSV row's value is a pointer —
``SheetRef:CC_tcarray`` — to a companion file
(``<csv_basename>__CC_tcarray.ext``) sitting next to the main CSV, holding
the matrix as plain comma-separated rows. Resolving ``SheetRef:`` pointers
is handled generically in ``calibration_checker.common.ci_compare`` (not here),
since it's a property of the CI CSV format, not of this instrument.

`.dev` file layout (tab-delimited, relevant lines only):

    <electronics serial>       ; NOT the same as the OOI unit serial —
                                  see note in parse_dev_file()
    Tcal: <T>C Ical: <I>C. ...  -> CC_tcal (only Tcal is used downstream)
    <n_wavelengths>             ; output wavelengths
    <n_tbins>                   ; number of temperature bins
    <n_tbins numbers>           ; temperature bins row          -> CC_tbins
    C<cwl>  A<awl>  <idx>  <ccwo>  <acwo>  <n_tbins tc values>  <n_tbins ta values>
        ... one such row per wavelength ...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

_SERIAL_FROM_FILENAME_RE = re.compile(r"ACS0*(\d+)", re.IGNORECASE)
_TCAL_RE = re.compile(r"Tcal:\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)
_WAVELENGTH_ROW_RE = re.compile(r"^C\d")


def _strip_comment(line: str) -> str:
    """Drop the trailing '; comment' portion of a .dev line."""
    return line.split(";", 1)[0]


def _tokens(line: str) -> list[str]:
    """Tab-split a .dev line, dropping empty column-separator tokens."""
    return [t for t in _strip_comment(line).split("\t") if t.strip() != ""]


def _serial_from_filename(filepath: str) -> str | None:
    """
    'ACS152.dev' -> 'ACS-152'.

    Note: the `.dev` file's own "Serial number" header field (e.g.
    53000098) is the meter's internal electronics ID, NOT the OOI asset
    serial used in the CI CSV (e.g. 'ACS-152') — those two numbers are
    unrelated, so the unit serial has to come from the filename instead.
    """
    m = _SERIAL_FROM_FILENAME_RE.search(Path(filepath).stem)
    return f"ACS-{m.group(1)}" if m else None


def parse_dev_file(filepath: str) -> pd.DataFrame:
    """
    Parse an AC-S `.dev` calibration file into a long-format DataFrame
    ready for comparison against a CI calibration CSV (and its companion
    ``__CC_tcarray.ext`` / ``__CC_taarray.ext`` matrix files).

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file.
        `name` values use the CC_ naming convention. `value` is a scalar
        (CC_tcal), a flat list (CC_awlngth, CC_acwo, CC_cwlngth, CC_ccwo,
        CC_tbins), or a list-of-lists / matrix (CC_tcarray, CC_taarray —
        one row per wavelength, one column per temperature bin).
    """
    with open(filepath, "r") as f:
        lines = f.readlines()

    serial = _serial_from_filename(filepath)
    source_file = Path(filepath).name

    tcal: float | None = None
    n_tbins: int | None = None
    tbins: list[float] = []

    cwlngth: list[float] = []
    awlngth: list[float] = []
    ccwo: list[float] = []
    acwo: list[float] = []
    tcarray: list[list[float]] = []
    taarray: list[list[float]] = []

    for line in lines:
        lower = line.lower()

        if tcal is None:
            m = _TCAL_RE.search(line)
            if m:
                tcal = float(m.group(1))
                continue

        if n_tbins is None and "number of temperature bins" in lower:
            n_tbins = int(_tokens(line)[0])
            continue

        if n_tbins is not None and not tbins and "temperature bins" in lower:
            tbins = [float(x) for x in _tokens(line)]
            continue

        if _WAVELENGTH_ROW_RE.match(line.strip()):
            if n_tbins is None:
                raise ValueError(
                    "Encountered a wavelength row before the 'number of "
                    "temperature bins' line — is this a valid AC-S .dev file?"
                )
            tok = _tokens(line)
            # tok = [C<wl>, A<wl>, <idx>, <ccwo>, <acwo>,
            #        <n_tbins tc values>, <n_tbins ta values>]
            cwlngth.append(float(tok[0][1:]))
            awlngth.append(float(tok[1][1:]))
            ccwo.append(float(tok[3]))
            acwo.append(float(tok[4]))
            tc_start = 5
            ta_start = tc_start + n_tbins
            tcarray.append([float(x) for x in tok[tc_start:ta_start]])
            taarray.append([float(x) for x in tok[ta_start:ta_start + n_tbins]])

    rows: list[dict[str, Any]] = [
        {"serial": serial, "name": "CC_tcal",     "value": tcal,     "source_file": source_file},
        {"serial": serial, "name": "CC_cwlngth",  "value": cwlngth,  "source_file": source_file},
        {"serial": serial, "name": "CC_ccwo",     "value": ccwo,     "source_file": source_file},
        {"serial": serial, "name": "CC_awlngth",  "value": awlngth,  "source_file": source_file},
        {"serial": serial, "name": "CC_acwo",     "value": acwo,     "source_file": source_file},
        {"serial": serial, "name": "CC_tbins",    "value": tbins,    "source_file": source_file},
        {"serial": serial, "name": "CC_tcarray",  "value": tcarray,  "source_file": source_file},
        {"serial": serial, "name": "CC_taarray",  "value": taarray,  "source_file": source_file},
    ]

    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, electronics ID, wavelength/tbin counts."""
    with open(filepath, "r") as f:
        lines = f.readlines()

    electronics_id = None
    n_wavelengths = None
    n_tbins = None
    for line in lines:
        lower = line.lower()
        if electronics_id is None and "serial number" in lower:
            electronics_id = _tokens(line)[0]
        elif n_wavelengths is None and "output wavelengths" in lower:
            n_wavelengths = int(_tokens(line)[0])
        elif n_tbins is None and "number of temperature bins" in lower:
            n_tbins = int(_tokens(line)[0])

    return {
        "serial":            _serial_from_filename(filepath),
        "electronics_id":     electronics_id,
        "n_wavelengths":      n_wavelengths,
        "n_temperature_bins": n_tbins,
    }
