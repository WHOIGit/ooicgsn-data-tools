"""
cruise_tools.ctd
================
SeaBird CTD calibration utilities.

Public API
----------
XMLCONParser          -- parse .XMLCON configuration files into DataFrames
parse_cal_pdf         -- parse SBE calibration certificate PDFs (text-based)
parse_flntu_pdf       -- parse FLNTU characterisation sheets (CHL + NTU)
parse_cdom_pdf        -- parse CDOM characterisation sheets (scanned / OCR)
compare_cal_to_xmlcon -- compare a parsed cal dict against an XMLCON sensor row
print_comparison      -- pretty-print comparison results to stdout
"""

from .xmlcon_parser_enhanced import XMLCONParser
from .cal_pdf_parser import (
    parse_cal_pdf,
    parse_cal_pdf_to_df,
    parse_flntu_pdf,
    parse_cdom_pdf,
    compare_cal_to_xmlcon,
    print_comparison,
    SENSOR_TYPE_MAP,
    TESSERACT_CMD,
)

__all__ = [
    "XMLCONParser",
    "parse_cal_pdf",
    "parse_cal_pdf_to_df",
    "parse_flntu_pdf",
    "parse_cdom_pdf",
    "compare_cal_to_xmlcon",
    "print_comparison",
    "SENSOR_TYPE_MAP",
    "TESSERACT_CMD",
]
