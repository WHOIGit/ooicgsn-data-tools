"""
CTDMO (Sea-Bird SBE 37-IM / SBE 37-IMP, "inductive modem" CTD) calibration
parser.

Parses the vendor ``.cal`` file (plain ``KEY=value`` lines, as produced by
Sea-Bird's SEATERM / SEASOFT export) and maps its coefficient names onto the
``CC_*`` naming convention used by the OOI CI calibration CSV for the
CTDMOS/CTDMOG asset class (``CGINS-CTDMOS-xxxxx__<date>.csv`` /
``CGINS-CTDMOG-xxxxx__<date>.csv``), so the two can be compared directly.

Note: the CI CSV includes one coefficient, ``CC_p_range``, that is not
present anywhere in the ``.cal`` file — it's the pressure sensor's rated
full-scale range (e.g. 160, 350, 1000, 7000 dbar), which comes from the
pressure sensor's nameplate / spec sheet, not the coefficient dump. This
parser does not invent that value; ``compare_source_to_ci`` will correctly
report it as ``missing_in_source`` so a human can verify it against the
calibration certificate header or the sensor's rated range.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# .cal file key -> CI CC_ coefficient name.
# INSTRUMENT_TYPE, SERIALNO, and the *CALDATE keys are metadata, not
# coefficients, and are handled separately (see parse_cal_file).
_CAL_TO_CC: dict[str, str] = {
    # Temperature
    "TA0":       "CC_a0",
    "TA1":       "CC_a1",
    "TA2":       "CC_a2",
    "TA3":       "CC_a3",
    # Conductivity
    "CG":        "CC_g",
    "CH":        "CC_h",
    "CI":        "CC_i",
    "CJ":        "CC_j",
    "CTCOR":     "CC_ctcor",
    "CPCOR":     "CC_cpcor",
    "WBOTC":     "CC_wbotc",
    # Pressure (strain gauge)
    "PA0":       "CC_pa0",
    "PA1":       "CC_pa1",
    "PA2":       "CC_pa2",
    "PTCA0":     "CC_ptca0",
    "PTCA1":     "CC_ptca1",
    "PTCA2":     "CC_ptca2",
    "PTCB0":     "CC_ptcb0",
    "PTCB1":     "CC_ptcb1",
    "PTCB2":     "CC_ptcb2",
    "PTEMPA0":   "CC_ptempa0",
    "PTEMPA1":   "CC_ptempa1",
    "PTEMPA2":   "CC_ptempa2",
}

# Metadata keys present in the .cal file that are NOT calibration
# coefficients (calibration dates, serial number, instrument type).
_METADATA_KEYS = {"INSTRUMENT_TYPE", "SERIALNO",
                   "TCALDATE", "CCALDATE", "PCALDATE"}


def _parse_kv_lines(filepath: str) -> dict[str, str]:
    """Read a `.cal` file's KEY=value lines into a dict (keys upper-cased)."""
    data: dict[str, str] = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, val = line.partition("=")
            data[key.strip().upper()] = val.strip()
    return data


def _build_serial(raw: dict[str, str]) -> str | None:
    """
    Build the CI-style serial ('37-12584') from INSTRUMENT_TYPE (e.g.
    'SBE37', 'SBE37SM', 'SBE37SMP-ODO', 'SBE 37 SI') + SERIALNO ('12584').

    The model number always immediately follows 'SBE' in this field, but
    is very often followed by suffix letters (SM/SI/IM/SMP-ODO/...) rather
    than sitting at the end of the string, so we anchor the search on
    'SBE' rather than on the end of the string.
    """
    serialno = raw.get("SERIALNO")
    instrument_type = raw.get("INSTRUMENT_TYPE", "")
    m = re.search(r"SBE\s*0*(\d+)", instrument_type, re.IGNORECASE)
    model = m.group(1) if m else None
    if serialno and model:
        return f"{model}-{serialno}"
    return serialno


def parse_cal_file(filepath: str) -> pd.DataFrame:
    """
    Parse a CTDMO (SBE 37-IM/IMP) `.cal` file into a long-format DataFrame
    ready for comparison against a CI calibration CSV.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file.
        `name` values use the CC_ naming convention (CC_a0, CC_g, ...).
        Unrecognised keys in the .cal file (other than the known metadata
        keys) are passed through unchanged with a warning-free best effort,
        so nothing is silently dropped.
    """
    raw = _parse_kv_lines(filepath)
    serial = _build_serial(raw)
    source_file = Path(filepath).name

    rows: list[dict[str, Any]] = []
    unmapped: list[str] = []

    for key, val in raw.items():
        if key in _METADATA_KEYS:
            continue
        name = _CAL_TO_CC.get(key)
        if name is None:
            unmapped.append(key)
            name = f"CC_{key.lower()}"  # best-effort passthrough
        try:
            value: Any = float(val)
        except ValueError:
            value = val
        rows.append({
            "serial": serial,
            "name": name,
            "value": value,
            "source_file": source_file,
        })

    df = pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])
    if unmapped:
        df.attrs["unmapped_keys"] = unmapped
    return df


def get_metadata(filepath: str) -> dict[str, str]:
    """
    Return the non-coefficient metadata from a `.cal` file: instrument
    type, serial number, and the three (temperature/conductivity/pressure)
    calibration dates.
    """
    raw = _parse_kv_lines(filepath)
    return {
        "instrument_type":  raw.get("INSTRUMENT_TYPE"),
        "serial":           _build_serial(raw),
        "t_cal_date":       raw.get("TCALDATE"),
        "c_cal_date":       raw.get("CCALDATE"),
        "p_cal_date":       raw.get("PCALDATE"),
    }
