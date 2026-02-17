# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/) per sub-package,
tagged as `<sub-package>-v<semver>` (e.g. `ctd-v0.1.0`).

---

## [Unreleased]

---

## cruise-tools-ctd

### [0.1.0] — 2025-02-17
#### Added
- `XMLCONParser` — parse SeaBird `.XMLCON` files into pandas DataFrames
- `cal_pdf_parser` — parse SBE calibration certificate PDFs (temperature,
  conductivity, pressure, oxygen) and characterisation sheets (FLNTU, CDOM)
- `ctd_cal_tool` — tkinter desktop GUI with three tabs:
  - XMLCON Files: load and inspect one or more XMLCON files
  - Cast Coefficient Diff: detect coefficient changes between consecutive casts
  - Cal PDF Comparison: validate XMLCON coefficients against calibration PDFs
- OCR pipeline for scanned CDOM characterisation sheets (Tesseract at 500 DPI)
- Coefficient name remapping between PDF and XMLCON conventions

---

## cruise-tools-anchor-survey

### [0.1.0] — 2025-02-17
#### Added
- `survey.py` — iterative least-squares anchor position solver, coordinate
  conversion utilities (DMS → DD, lat/lon ↔ local metres), fallback calculation
- `survey_gui.py` — Panel-based web GUI for interactive survey computation
- Example data files (`data/example_data.dat`, `data/drop_points.dat`)
- Pytest suite covering core geometry functions

---

## cruise-tools-common

### [0.1.0] — 2025-02-17
#### Added
- Package scaffold; no utilities yet
