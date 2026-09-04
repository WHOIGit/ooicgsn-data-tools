"""
DOFST-K (Sea-Bird SBE 43F fast-response dissolved oxygen sensor) `.cal`
file parser.

Parses the vendor `.cal` file (plain KEY=value lines) and maps its
coefficient names onto the CC_ naming convention used by the OOI CI
calibration CSV for the DOFSTK asset class
(`CGINS-DOFSTK-xxxxx__<date>.csv`).

Important: the CI CSV's `CC_oxygen_signal_slope` (Soc) does NOT come from
this `.cal` file — SBE 43 oxygen sensors often get a post-calibration "Soc
adjustment" documented only in the calibration certificate PDF (marked
"(adj)"), and the CI record is supposed to reflect that adjusted value, not
the factory Soc baked into the `.cal` file. See
``cruise_tools.dofstk.soc_pdf_parser`` for that half, and
``cruise_tools.dofstk.parse_dofstk()`` for the combined result. This
parser deliberately does NOT emit a CC_oxygen_signal_slope row from SOC,
so it can't accidentally shadow the (correct) PDF-derived value.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

# .cal file key -> CI CC_ coefficient name.
_CAL_TO_CC: dict[str, str] = {
    "FOFFSET": "CC_frequency_offset",
    "A":       "CC_residual_temperature_correction_factor_a",
    "B":       "CC_residual_temperature_correction_factor_b",
    "C":       "CC_residual_temperature_correction_factor_c",
    "E":       "CC_residual_temperature_correction_factor_e",
}

# Metadata / non-CI keys: INSTRUMENT_TYPE, SERIALNO, OCALDATE are pure
# metadata; SOC and TAU20 are real calibration values but are NOT emitted
# as coefficient rows here — see module docstring for SOC, and TAU20 isn't
# part of this CI CSV at all (same pattern as DOSTA's TempCoef/PhaseCoef).
_METADATA_KEYS = {"INSTRUMENT_TYPE", "SERIALNO", "OCALDATE", "SOC", "TAU20"}


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
    Build the CI-style serial ('43-2725') from INSTRUMENT_TYPE (e.g.
    'SBE43F') + SERIALNO ('2725'). Same approach as cruise_tools.ctdmo:
    the model number always immediately follows 'SBE', regardless of any
    suffix letters (here, the 'F' for fast-response).
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
    Parse a DOFST-K (SBE 43F) `.cal` file into a long-format DataFrame:
    CC_frequency_offset and the four residual-temperature-correction
    factors (a/b/c/e). Does NOT include CC_oxygen_signal_slope — combine
    with ``cruise_tools.dofstk.parse_soc_pdf()`` (or just use
    ``parse_dofstk()``) to get that.
    """
    raw = _parse_kv_lines(filepath)
    serial = _build_serial(raw)
    source_file = Path(filepath).name

    rows: list[dict[str, Any]] = []
    for key, val in raw.items():
        if key in _METADATA_KEYS:
            continue
        name = _CAL_TO_CC.get(key, f"CC_{key.lower()}")
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

    return pd.DataFrame(rows, columns=["serial", "name", "value", "source_file"])


def get_metadata(filepath: str) -> dict[str, Any]:
    """Return non-coefficient metadata: serial, oxygen cal date, factory Soc, Tau20."""
    raw = _parse_kv_lines(filepath)
    return {
        "serial":            _build_serial(raw),
        "o2_cal_date":       raw.get("OCALDATE"),
        "factory_soc":       float(raw["SOC"]) if "SOC" in raw else None,
        "tau20":             float(raw["TAU20"]) if "TAU20" in raw else None,
    }
