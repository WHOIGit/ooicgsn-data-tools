"""
FLORT (WET Labs ECO Triplet puck, e.g. BBFL2W/BBFL2WB — combined volume
scattering + chlorophyll fluorescence + CDOM fluorescence sensor) `.dev`
calibration file parser.

Note: on this instrument, the CDOM channel is one of the three channels
built into the same physical puck (not a separate sensor) — one `.dev`
file and one CI calibration CSV (`CGINS-FLORTD-xxxxx__<date>.csv`) cover
all three channels. This is a different device from the standalone
single-channel ECO CDOM fluorometer characterisation sheet handled by
``cruise_tools.cdom`` (that one is its own separate sensor, tracked under
a different asset class, and OCR'd from a scanned PDF instead of parsed
from a `.dev` file).

The `.dev` file is tab-delimited with a handful of key rows:

    lambda=4   <scale_factor>  <dark_counts>  <wavelength>  <wavelength>
    CHL=6      <scale_factor>  <dark_counts>
    CDOM=8     <scale_factor>  <dark_counts>

Three CI coefficients — ``CC_angular_resolution``, ``CC_depolarization_ratio``,
and ``CC_scattering_angle`` — are fixed characteristics of the BBFL2W
sensor design (the same for every unit of this model) rather than
per-unit calibration values, and don't appear anywhere in the `.dev` file.
This parser doesn't invent them; the comparator will correctly report them
as ``missing_in_source`` so they can be checked against the sensor's
datasheet instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# Row label -> (scale_factor CC name, dark_counts CC name)
_ROW_TO_CC = {
    "lambda": ("CC_scale_factor_volume_scatter", "CC_dark_counts_volume_scatter"),
    "CHL":    ("CC_scale_factor_chlorophyll_a",  "CC_dark_counts_chlorophyll_a"),
    "CDOM":   ("CC_scale_factor_cdom",            "CC_dark_counts_cdom"),
}

_ROW_RE = re.compile(r"^([A-Za-z/]+)=(\d+)$")
_HEADER_RE = re.compile(r"^ECO\s+(\S+)", re.IGNORECASE)
_DATE_RE = re.compile(r"Created on[:\s]+(\S+)", re.IGNORECASE)


def _read_rows(filepath: str) -> list[tuple[str, list[str]]]:
    """Read every `label=N  value  value  ...` row in the .dev file, in order."""
    rows = []
    with open(filepath, "r") as f:
        for line in f:
            tokens = line.split()
            if not tokens:
                continue
            m = _ROW_RE.match(tokens[0])
            if not m:
                continue
            rows.append((m.group(1), tokens[1:]))
    return rows


def _serial_from_header(filepath: str) -> tuple[str | None, str | None]:
    """('ECO  BBFL2W-1116' -> ('BBFL2W', '1116'))."""
    with open(filepath, "r") as f:
        first_line = f.readline()
    m = _HEADER_RE.match(first_line.strip())
    if not m:
        return None, None
    tag = m.group(1)  # e.g. 'BBFL2W-1116'
    if "-" in tag:
        model, serial = tag.rsplit("-", 1)
        return model, serial
    return tag, None


def parse_dev_file(filepath: str) -> pd.DataFrame:
    """
    Parse a WET Labs ECO Triplet `.dev` calibration file (e.g. BBFL2W) into
    a long-format DataFrame ready for comparison against a CI calibration
    CSV.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file.
        `name` values use the CC_ naming convention
        (CC_scale_factor_cdom, CC_dark_counts_chlorophyll_a, ...).
    """
    _, serial = _serial_from_header(filepath)
    source_file = Path(filepath).name
    rows: list[dict[str, Any]] = []

    for label, values in _read_rows(filepath):
        if label == "lambda":
            scale_cc, dark_cc = _ROW_TO_CC["lambda"]
            if len(values) >= 2:
                rows.append({"serial": serial, "name": scale_cc,
                             "value": float(values[0]), "source_file": source_file})
                rows.append({"serial": serial, "name": dark_cc,
                             "value": float(values[1]), "source_file": source_file})
            if len(values) >= 3:
                rows.append({"serial": serial, "name": "CC_measurement_wavelength",
                             "value": float(values[2]), "source_file": source_file})
        elif label in ("CHL", "CDOM"):
            scale_cc, dark_cc = _ROW_TO_CC[label]
            if len(values) >= 2:
                rows.append({"serial": serial, "name": scale_cc,
                             "value": float(values[0]), "source_file": source_file})
                rows.append({"serial": serial, "name": dark_cc,
                             "value": float(values[1]), "source_file": source_file})
        # "N/U" (not used) and "Columns" rows carry no calibration values.

    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: model, serial, and file creation date."""
    model, serial = _serial_from_header(filepath)
    with open(filepath, "r") as f:
        text = f.read()
    date_m = _DATE_RE.search(text)
    return {
        "model":        model,
        "serial":       serial,
        "created_on":   date_m.group(1).strip() if date_m else None,
    }
