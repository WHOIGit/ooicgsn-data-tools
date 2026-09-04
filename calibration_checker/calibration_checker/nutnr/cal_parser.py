"""
NUTNR-B (Satlantic/Sea-Bird SUNA V2 submersible UV nitrate analyzer)
`.CAL` file parser.

Unlike the other `.cal`-style files in this toolkit, this one is a
line-tagged format: header lines start with ``H,`` (some free-text
comments, some ``KEY value`` metadata), and per-wavelength calibration
rows start with ``E,`` — one row per wavelength, with columns
``Wavelength, NO3, SWA, TSWA, Reference`` (column order given explicitly
by the ``H,Wavelength,NO3,SWA,TSWA,Reference`` header line, rather than
assumed).

Mapping to the CI calibration CSV:

    T_CAL header value      -> CC_cal_temp           (scalar)
    Wavelength column       -> CC_wl                 (list, one per row)
    NO3 column              -> CC_eno3               (list)
    SWA column              -> CC_eswa               (list)
    Reference column        -> CC_di                 (list — this is the
                                                        reference spectrum
                                                        measured in DI water)

The ``TSWA`` column is on the certificate but not part of this CI CSV, so
it's intentionally left out — same pattern as other instruments' unused
certificate fields. ``T_CAL_SWA`` (a different header value from
``T_CAL``, coincidentally often equal to it) is also not used for
``CC_cal_temp`` — the two are genuinely different fields, so this parser
is careful not to conflate them.

Two coefficients in the CI CSV, ``CC_lower_wavelength_limit_for_spectra_fit``
and ``CC_upper_wavelength_limit_for_spectra_fit``, aren't in the `.CAL`
file at all — they're fixed processing-algorithm parameters (which
wavelength range OOI's fitting routine uses), not per-unit calibration
values, so this parser doesn't invent them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

_SUNA_SERIAL_RE = re.compile(r"SUNA\s+(\d+)", re.IGNORECASE)
_FILENAME_SERIAL_RE = re.compile(r"(\d+)")

# "H,T_CAL 20.00" — matches T_CAL but NOT T_CAL_SWA (the required
# whitespace right after T_CAL rules that out, since T_CAL_SWA continues
# with '_SWA' instead of whitespace there).
_T_CAL_RE = re.compile(r"^H,T_CAL[ \t]+([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)

# The real column-order line is "H,Wavelength,NO3,SWA,TSWA,Reference" (4
# fields after 'Wavelength'). There's ALSO an earlier, unrelated
# "H,Wavelength,nm" line (just a units annotation, 1 field) that would
# otherwise match a naive "^H,Wavelength,(.+)$" pattern first — requiring
# at least 3 comma-separated fields rules that one out.
_HEADER_COLUMNS_RE = re.compile(r"^H,Wavelength,([^,]+(?:,[^,]+){2,})$", re.IGNORECASE)


def _build_serial(filepath: str, text: str) -> str | None:
    """
    'H,SUNA 1063 Cal M ...' -> 'NTR-1063' (NUTNR's CI serial prefix).
    Falls back to digits in the filename ('SNA1063N.CAL') if the header
    line isn't found or doesn't parse.
    """
    m = _SUNA_SERIAL_RE.search(text)
    if m is None:
        m = _FILENAME_SERIAL_RE.search(Path(filepath).stem)
    return f"NTR-{m.group(1)}" if m else None


def parse_cal_file(filepath: str) -> pd.DataFrame:
    """
    Parse a NUTNR-B (SUNA) `.CAL` file into a long-format DataFrame ready
    for comparison against a CI calibration CSV.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file.
        CC_cal_temp is a scalar; CC_wl, CC_eno3, CC_eswa, CC_di are lists,
        one entry per calibrated wavelength.
    """
    with open(filepath, "r") as f:
        lines = f.readlines()

    text = "".join(lines)
    serial = _build_serial(filepath, text)
    source_file = Path(filepath).name

    t_cal: float | None = None
    columns: list[str] | None = None
    col_data: dict[str, list[float]] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if t_cal is None:
            m = _T_CAL_RE.match(line)
            if m:
                t_cal = float(m.group(1))
                continue

        if columns is None:
            m = _HEADER_COLUMNS_RE.match(line)
            if m:
                columns = ["Wavelength"] + [c.strip() for c in m.group(1).split(",")]
                col_data = {c: [] for c in columns}
                continue

        if line.startswith("E,"):
            if columns is None:
                raise ValueError(
                    "Encountered a data row ('E,...') before the "
                    "'H,Wavelength,...' column-header line — is this a "
                    "valid SUNA .CAL file?"
                )
            values = line.split(",")[1:]
            for col, val in zip(columns, values):
                col_data[col].append(float(val))

    rows: list[dict[str, Any]] = [
        {"serial": serial, "name": "CC_cal_temp", "value": t_cal, "source_file": source_file},
        {"serial": serial, "name": "CC_wl",       "value": col_data.get("Wavelength", []), "source_file": source_file},
        {"serial": serial, "name": "CC_eno3",     "value": col_data.get("NO3", []),        "source_file": source_file},
        {"serial": serial, "name": "CC_eswa",     "value": col_data.get("SWA", []),        "source_file": source_file},
        {"serial": serial, "name": "CC_di",       "value": col_data.get("Reference", []),  "source_file": source_file},
    ]

    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, T_CAL_SWA, path length, integration period."""
    with open(filepath, "r") as f:
        text = f.read()

    def _find(pattern: str) -> str | None:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    return {
        "serial":            _build_serial(filepath, text),
        "t_cal_swa":         _find(r"^H,T_CAL_SWA[ \t]+([+-]?\d+(?:\.\d+)?)"),
        "path_length_mm":    _find(r"^H,PATH_LENGTH[ \t]+(\d+)"),
        "integration_period": _find(r"^H,INT_PERIOD[ \t]+(\d+)"),
        "creation_time":     _find(r"^H,File creation time[ \t]+(.+)$"),
    }
