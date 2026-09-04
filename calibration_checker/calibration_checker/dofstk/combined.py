"""
DOFST-K (SBE 43F) combined parser.

This instrument is the first in this toolkit where a single CI calibration
CSV is filled in from TWO independent source documents:

  * the `.cal` file — authoritative for CC_frequency_offset and the four
    residual-temperature-correction factors (a/b/c/e); and
  * the calibration certificate PDF — authoritative for
    CC_oxygen_signal_slope (Soc), since SBE 43 sensors often get a
    post-calibration Soc adjustment that's documented only on the
    certificate, not in the `.cal` file.

``parse_dofstk()`` combines both into the single DataFrame
``compare_source_to_ci()`` expects.
"""

from __future__ import annotations

import warnings

import pandas as pd

from .cal_parser import parse_cal_file
from .soc_pdf_parser import parse_soc_pdf


def parse_dofstk(cal_filepath: str, soc_pdf_filepath: str) -> pd.DataFrame:
    """
    Parse a DOFST-K `.cal` file and its matching Soc-adjusted certificate
    PDF, and combine them into one source DataFrame.

    Parameters
    ----------
    cal_filepath : str
        Path to the `.cal` file (CC_frequency_offset,
        CC_residual_temperature_correction_factor_{a,b,c,e}).
    soc_pdf_filepath : str
        Path to the calibration certificate PDF (CC_oxygen_signal_slope).

    Returns
    -------
    pd.DataFrame
        Columns: serial, name, value, source_file — ready for
        ``cruise_tools.common.compare_source_to_ci()``.
    """
    cal_df = parse_cal_file(cal_filepath)
    soc_df = parse_soc_pdf(soc_pdf_filepath)

    cal_serials = set(cal_df["serial"].dropna().unique())
    soc_serials = set(soc_df["serial"].dropna().unique())
    if cal_serials and soc_serials and cal_serials != soc_serials:
        warnings.warn(
            f"Serial mismatch between .cal file ({cal_serials}) and "
            f"certificate PDF ({soc_serials}) — check you selected the "
            f"right pair of files for this sensor."
        )

    return pd.concat([cal_df, soc_df], ignore_index=True)
