# cruise-tools-ctd

SeaBird CTD calibration utilities — part of the
[cruise_tools](https://github.com/WHOIGit/cruise_tools) monorepo.

## Summary
This tool allows for checking if the CTD XMLCON files change throughout the cruise and simplifies comparison against the provided calibration pdfs.

## What's included

| Module | Purpose |
|--------|---------|
| `xmlcon_parser_enhanced.py` | Parse SeaBird `.XMLCON` configuration files into pandas DataFrames |
| `cal_pdf_parser.py` | Parse SeaBird calibration certificate PDFs and characterisation sheets |
| `ctd_cal_tool.py` | Desktop GUI for loading XMLCONs, comparing casts, and validating against cal PDFs |

## Install (from repo root)

```bash
# Recommended — installs Tesseract OCR binary automatically
conda env create -f environment.yml
conda activate cruise-tools

# Then install just this sub-package in editable mode
pip install -e ctd/

# Or install everything at once
pip install -e ctd/ -e anchor_survey/ -e common/
```

## Launch the GUI

```bash
ctd-cal-tool
# or
python ctd/cruise_tools/ctd/ctd_cal_tool.py
```

## Python API

```python
from cruise_tools.ctd import XMLCONParser, parse_cal_pdf, compare_cal_to_xmlcon

# Parse an XMLCON file
parser = XMLCONParser("AR98A_013.XMLCON")
print(parser.get_summary())

# Parse a calibration certificate PDF
cal = parse_cal_pdf("SBE_43_O0264_12Nov24.pdf")

# Compare
from cruise_tools.ctd import print_comparison
print_comparison(cal, parser.get_sensor(6))
```

For the full API reference, notebook-style cast comparison functions, and
supported document types, see the top-level [README](../README.md).
