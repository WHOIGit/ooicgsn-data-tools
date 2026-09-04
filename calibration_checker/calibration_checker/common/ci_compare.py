"""
Generic comparison between:

  * a parsed *source* calibration record — long format, one row per
    coefficient: ``serial``, ``name``, ``value`` (plus optional
    ``source_file``) — produced by any of the per-instrument parsers in
    ``calibration_checker.<instrument>``; and

  * an independently generated *CI calibration CSV* — the format used to
    load coefficients into the OOI Calibration Information (asset
    management) system: ``serial, name, value, notes``.

This module is instrument-agnostic. Every per-instrument parser is
responsible for producing a DataFrame with ``serial``/``name``/``value``
columns using the same coefficient-naming convention as the CI CSV (e.g.
``CC_a0``, ``CC_g``, ...); this module just does the join + comparison.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

import pandas as pd

REQUIRED_SOURCE_COLS = ["serial", "name", "value"]
REQUIRED_CI_COLS = ["serial", "name", "value"]

# Some CI CSVs don't inline very large arrays (e.g. OPTAA's 85x36
# temperature-correction matrices) — instead the value cell is a pointer,
# "SheetRef:CC_tcarray", to a companion file sitting next to the main CSV:
# "<main_csv_basename>__CC_tcarray.ext", holding the matrix as plain
# comma-separated rows (one row per line). This is a property of the CI
# CSV export format itself, not of any one instrument, so it's resolved
# here rather than in a per-instrument parser.
_SHEETREF_RE = re.compile(r"^SheetRef:(.+)$", re.IGNORECASE)


def _maybe_parse_list(v):
    """
    If `v` is a string that looks like a Python list literal (e.g. the CI
    CSV's "[0.0, 1.0]" or "[2.56095E-03, ..., 3.61801E+00]"), parse it into
    an actual list of floats. Anything else is returned unchanged.
    """
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                return list(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return v
    return v


def _load_ext_matrix(path: str) -> list[list[float]]:
    """Load a companion '__CC_xxx.ext' file: one comma-separated row per line."""
    rows = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append([float(x) for x in line.split(",")])
    return rows


def _resolve_sheet_refs(df: pd.DataFrame, csv_path: str) -> pd.DataFrame:
    """
    Replace any "SheetRef:<name>" value cells with the matrix loaded from
    the companion "<csv_basename>__<name>.ext" file next to csv_path.
    Cells that aren't SheetRef pointers, or whose companion file can't be
    found, are left unchanged.
    """
    csv_path = Path(csv_path)
    base_dir = csv_path.parent
    stem = csv_path.name
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]

    def resolve(v):
        if isinstance(v, str):
            m = _SHEETREF_RE.match(v.strip())
            if m:
                ext_path = base_dir / f"{stem}__{m.group(1).strip()}.ext"
                if ext_path.exists():
                    return _load_ext_matrix(str(ext_path))
        return v

    df = df.copy()
    df["value"] = df["value"].apply(resolve)
    return df


def load_ci_csv(path_or_df) -> pd.DataFrame:
    """
    Load a CI calibration CSV (``serial,name,value,notes``) and normalise
    dtypes for comparison. Accepts a path or an already-loaded DataFrame.
    Array-valued cells (e.g. ``"[0.0, 1.0]"``) are parsed into Python
    lists. "SheetRef:<name>" cells are resolved against a companion
    ``<csv_basename>__<name>.ext`` matrix file next to the CSV — only
    possible when a path is given, since a bare DataFrame carries no
    directory to look alongside.
    """
    is_path = isinstance(path_or_df, str)
    df = pd.read_csv(path_or_df) if is_path else path_or_df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    missing = [c for c in REQUIRED_CI_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CI CSV is missing required column(s): {missing}. "
            f"Expected at least: serial, name, value."
        )

    df["serial"] = df["serial"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    df["value"] = df["value"].apply(_maybe_parse_list)
    if is_path:
        df = _resolve_sheet_refs(df, path_or_df)
    if "notes" not in df.columns:
        df["notes"] = None
    return df[["serial", "name", "value", "notes"]]


def _values_match_scalar(a, b, tolerance: float) -> tuple[bool, Optional[float]]:
    """Return (match, pct_delta_or_None) for two scalar values."""
    try:
        fa, fb = float(a), float(b)
        if abs(fa - fb) <= tolerance:
            return True, 0.0
        denom = abs(fa) if fa != 0 else 1.0
        return False, abs(fa - fb) / denom * 100
    except (TypeError, ValueError):
        return (str(a).strip().lower() == str(b).strip().lower()), None


def _values_match(a, b, tolerance: float) -> tuple[bool, Optional[float]]:
    """
    Return (match, pct_delta_or_None). Handles plain scalars, flat
    list/array-valued coefficients (e.g. DOSTA's CC_csv, CC_conc_coef),
    and nested list/matrix-valued coefficients (e.g. OPTAA's CC_tcarray,
    85 wavelengths x 36 temperature bins) by recursing element-wise and
    reporting the largest delta found at any depth.
    """
    a = _maybe_parse_list(a)
    b = _maybe_parse_list(b)

    a_is_seq = isinstance(a, (list, tuple))
    b_is_seq = isinstance(b, (list, tuple))

    if a_is_seq or b_is_seq:
        if not (a_is_seq and b_is_seq):
            return False, None  # one side is a list, the other isn't
        if len(a) != len(b):
            return False, None  # different lengths — can't be the "same" coefficient

        deltas = []
        all_ok = True
        for x, y in zip(a, b):
            ok, delta = _values_match(x, y, tolerance)  # recurse — handles matrices too
            all_ok = all_ok and ok
            if delta is not None:
                deltas.append(delta)
        return all_ok, (max(deltas) if deltas else None)

    return _values_match_scalar(a, b, tolerance)


def compare_source_to_ci(
    source_df: pd.DataFrame,
    ci_csv,
    tolerance: float = 1e-6,
) -> pd.DataFrame:
    """
    Compare a parsed source calibration DataFrame against a CI CSV.

    Parameters
    ----------
    source_df : pd.DataFrame
        Columns ``serial``, ``name``, ``value`` (``source_file`` optional).
    ci_csv : str or pd.DataFrame
        Path to the CI calibration CSV, or an already-loaded DataFrame.
    tolerance : float
        Absolute tolerance for numeric comparisons.

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, source_value, ci_value, status, delta_pct,
        notes, source_file.
        status is one of: 'match', 'mismatch',
        'missing_in_ci' (in source but not the CI csv),
        'missing_in_source' (in CI csv but not the parsed source).
    """
    missing = [c for c in REQUIRED_SOURCE_COLS if c not in source_df.columns]
    if missing:
        raise ValueError(f"source_df is missing required column(s): {missing}")

    src = source_df.copy()
    src["serial"] = src["serial"].astype(str).str.strip()
    src["name"] = src["name"].astype(str).str.strip()

    ci = load_ci_csv(ci_csv)

    merged = pd.merge(
        src[["serial", "name", "value"] + (["source_file"] if "source_file" in src.columns else [])],
        ci,
        on=["serial", "name"],
        how="outer",
        suffixes=("_source", "_ci"),
        indicator=True,
    )

    rows = []
    for _, r in merged.iterrows():
        if r["_merge"] == "left_only":
            status, delta = "missing_in_ci", None
        elif r["_merge"] == "right_only":
            status, delta = "missing_in_source", None
        else:
            ok, delta = _values_match(r["value_source"], r["value_ci"], tolerance)
            status = "match" if ok else "mismatch"

        rows.append({
            "serial":        r["serial"],
            "name":          r["name"],
            "source_value":  r.get("value_source"),
            "ci_value":      r.get("value_ci"),
            "status":        status,
            "delta_pct":     delta,
            "notes":         r.get("notes"),
            "source_file":   r.get("source_file"),
        })

    result = pd.DataFrame(rows)
    status_order = {"mismatch": 0, "missing_in_source": 1,
                     "missing_in_ci": 2, "match": 3}
    result["_sort"] = result["status"].map(status_order)
    result = result.sort_values(["_sort", "serial", "name"]) \
                   .drop(columns="_sort").reset_index(drop=True)
    return result


def summarize(result: pd.DataFrame) -> dict[str, int]:
    """Quick counts of each status, for a one-line summary in logs/UI."""
    return result["status"].value_counts().to_dict()
