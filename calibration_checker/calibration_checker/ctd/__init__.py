"""
cruise_tools.ctd — SeaBird SBE 9/11 CTD frame: XMLCON parser and
calibration-certificate PDF parser (temperature/conductivity/pressure/
oxygen sensors).

FLNTU/FLORT (fluorometer + turbidity) and CDOM sensors are bolted onto the
same physical frame and also land in its XMLCON, but each is tracked as its
own instrument and lives in its own module — see cruise_tools.flort and
cruise_tools.cdom. Other instrument families (CTDMO, DOSTA, ...) live in
their own top-level cruise_tools.<family> packages — see
cruise_tools.cal_tool for the combined GUI.
"""

from .xmlcon_parser_enhanced import XMLCONParser
from .cal_pdf_parser import (
    parse_cal_pdf,
    parse_cal_pdf_to_df,
    compare_cal_to_xmlcon,
    print_comparison,
)

__all__ = [
    "XMLCONParser",
    "parse_cal_pdf",
    "parse_cal_pdf_to_df",
    "compare_cal_to_xmlcon",
    "print_comparison",
]
