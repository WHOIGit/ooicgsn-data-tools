# Cruise Tools — Calibration Verification

A Python toolkit for parsing instrument calibration files and checking them
against independently generated records (typically the CSV used to load
calibration coefficients into OOI's Calibration Information / asset
management system) — to catch transcription errors before they go into the
CI system.

Each instrument family (CTD, CTDMO, FLORT, ...) is its own module with its
own parser, because they use different file formats and different
coefficient-naming conventions. A shared comparator (`cruise_tools.common`)
does the actual "does this match the CI CSV" check, so adding a new
instrument only means writing one small parser, not a whole new comparison
pipeline.

## Contents

```
cruise_tools/
├── ctd/                        # SBE 9/11 CTD frame (deck-box CTD): temp/cond/pressure/oxygen
│   ├── __init__.py              # public API re-exports
│   ├── xmlcon_parser_enhanced.py   # XMLCON → pandas DataFrame
│   └── cal_pdf_parser.py           # SBE cal cert PDF → coefficient dict
├── flort/                       # WET Labs ECO FLNTU / ECO Triplet (fluorometer + turbidity + backscatter)
│   ├── __init__.py
│   ├── flort_pdf_parser.py     # FLNTU characterisation sheet → XMLCON-shaped dicts (CTD-frame comparison)
│   └── dev_parser.py           # ECO Triplet .dev file → CI-CSV-shaped DataFrame (CGINS-FLORTD)
├── cdom/                        # standalone WET Labs ECO CDOM fluorometer (single channel)
│   ├── __init__.py
│   └── cdom_pdf_parser.py      # scanned characterisation sheet (OCR) → coefficient dict
├── ctdmo/                       # SBE 37-IM/IMP "inductive modem" CTD
│   ├── __init__.py
│   └── cal_parser.py           # .cal file → CI-CSV-shaped DataFrame
├── dosta/                       # Aanderaa Optode 4831/4330 (oxygen)
│   ├── __init__.py
│   └── aanderaa_pdf_parser.py  # cal certificate PDF (tables) → CI-CSV-shaped DataFrame
├── optaa/                       # WET Labs AC-S spectral absorption/attenuation meter
│   ├── __init__.py
│   └── dev_parser.py           # .dev file → CI-CSV-shaped DataFrame (incl. wavelength arrays + matrices)
├── dofstk/                      # SBE 43F fast-response dissolved oxygen sensor
│   ├── __init__.py
│   ├── cal_parser.py           # .cal file → most CC_ coefficients
│   ├── soc_pdf_parser.py       # Soc-adjusted cal certificate PDF → CC_oxygen_signal_slope
│   └── combined.py             # merges both into one source DataFrame
├── parad/                        # Biospherical QSP-2200 PAR sensor
│   ├── __init__.py
│   └── pdf_parser.py           # cal certificate PDF → CC_dark_offset, CC_scale_wet
├── nutnr/                        # Satlantic/Sea-Bird SUNA V2 submersible UV nitrate analyzer
│   ├── __init__.py
│   └── cal_parser.py           # .CAL file → CC_cal_temp + per-wavelength arrays
├── common/                       # shared helpers, used across instrument modules
│   ├── __init__.py
│   ├── pdf_text.py             # shared PDF text extraction
│   ├── ocr.py                  # shared OCR fallback for scanned (no-text-layer) PDFs
│   ├── dates.py                # shared calibration-date normalisation
│   └── ci_compare.py           # generic (source vs CI csv) comparator — incl. SheetRef .ext resolution
└── cal_tool.py                  # Desktop GUI (tkinter), all instruments
environment.yml                  # conda environment (recommended)
requirements.txt                 # pip-only alternative
pyproject.toml                   # package metadata / console script
```

Every physical sensor is its own instrument module — even ones bolted onto
the same CTD frame (FLORT and CDOM live in the frame's XMLCON too, but each
is tracked and calibrated as its own asset, so each gets its own parser).
Instrument families so far: **CTD**, **FLORT**, **CDOM** (all via the CTD
frame's XMLCON/PDF certs), **CTDMO** (`.cal` file), **DOSTA** (cal
certificate PDF), the **FLORT ECO Triplet** (e.g. BBFL2W, `.dev` file —
note: on this instrument the CDOM channel is built into the same puck as
volume-scattering and chlorophyll, so one `.dev` file covers all three),
**OPTAA** (WET Labs AC-S, `.dev` file — per-wavelength arrays plus two
85x36 temperature-correction matrices resolved from companion `.ext`
files), **DOFSTK** (SBE 43F fast-response oxygen — the first instrument
here needing *two* source files: a `.cal` file plus a Soc-adjusted
certificate PDF; the Instrument Compare tab's file-loading panel adapts to
however many source files an instrument declares), **PARAD-K**
(Biospherical QSP-2200 PAR sensor, cal certificate PDF — sometimes a
scanned image, OCR'd automatically), and **NUTNR-B** (Satlantic/Sea-Bird
SUNA V2 nitrate analyzer, `.CAL` file — per-wavelength extinction
coefficient arrays). More instruments can be added the same way — see
[Adding a new instrument family](#adding-a-new-instrument-family) below.

---

## Quick start

### 1 — Create the environment (conda, recommended)

```bash
conda env create -f environment.yml
conda activate ctd-cal
```

This installs **Tesseract OCR** and **poppler** automatically via
conda-forge, which are required for parsing scanned CDOM characterisation
sheets (a CTD-frame sub-sensor).

### 2 — pip-only alternative

If you prefer pip, first install the system binaries manually (only needed
for CDOM OCR parsing — CTDMO `.cal` files and text-based cal PDFs don't need
these):

| OS      | Command |
|---------|---------|
| Windows | Download [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [poppler](https://github.com/oschwartz10612/poppler-windows/releases); add both to PATH |
| macOS   | `brew install tesseract poppler` |
| Linux   | `sudo apt install tesseract-ocr poppler-utils` |

Then install Python packages:

```bash
pip install -r requirements.txt
```

### 3 — Launch the GUI

```bash
# From the repo root after activating the environment:
python -m cruise_tools.cal_tool

# Or, if installed as a package (pip install -e .):
cal-tool
```

---

## GUI walkthrough

### Tab 1 · XMLCON Files *(CTD)*

| Control | Action |
|---------|--------|
| **＋ Files** | Open one or more `.XMLCON` files |
| **＋ Folder** | Load all `.XMLCON` files in a directory (skips `deck_test` files automatically) |
| **✕ Remove** | Remove selected file(s) from the session |

Selecting a file populates the right panel with its sensor table: sensor type,
serial number, calibration date, and two representative coefficients per sensor.

### Tab 2 · Cast Coefficient Diff *(CTD)*

Automatically populated whenever 2+ XMLCON files are loaded.

- Files are sorted by the **cast number** extracted from the filename
  (e.g. `AR98A_013.XMLCON` → cast `013`).
- Each row in the summary table is a *(sensor type, serial number,
  cast N-1 → cast N)* transition where at least one coefficient changed.
- **Click any row** to see the full parameter-by-parameter breakdown in the
  lower pane, with Δ% for numeric changes.

### Tab 3 · Cal PDF Comparison *(CTD)*

1. Select a file in Tab 1, then select a sensor from the left list.
2. Click **＋ Load Cal PDF** and choose the matching calibration certificate.
3. The right panel shows every coefficient: ✓ matches (green), ✗ mismatches
   (orange with Δ%), and XMLCON-only firmware constants (grey).

**Tesseract path (Windows):** if Tesseract is not on your PATH, paste the full
path to `tesseract.exe` in the text field before loading a CDOM PDF.
e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe`

### Tab 4 · Instrument Compare *(any registered instrument)*

The general-purpose "did the CI CSV get transcribed correctly" check.

1. Pick the **instrument family** from the dropdown (e.g. "CTDMO (SBE
   37-IM/IMP) — .cal file"). The **"1 · Source file(s)"** section adapts
   automatically: most instruments show one "＋ Load" button, but an
   instrument that needs more than one input file (like DOFSTK — a `.cal`
   file plus a Soc-adjusted certificate PDF) shows one button per file,
   each labelled with what it expects.
2. Load every source file for the selected instrument.
3. **＋ Load CI CSV** — the independently generated CI calibration CSV
   (`serial, name, value, notes`) for the *same* instrument/serial number.
4. Click **↻ Compare**. Every coefficient is shown as:
   - ✓ green — value matches
   - ✗ orange — value differs (with Δ%) — likely transcription error
   - grey "not in CI CSV" — the native file has a coefficient the CSV
     doesn't
   - grey "not in cal file — verify manually" — the CSV has a value
     (e.g. `CC_p_range`) that isn't derivable from the native file at all,
     and needs checking against the certificate/nameplate by hand
5. **⤓ Export Report CSV** saves the full comparison table.

---

## Supported calibration document types

| Instrument | Source document | Parser |
|--------|--------------|-----------------|
| CTD frame (SBE 9/11) — XMLCON | XMLCON config file | `XMLCONParser` |
| SBE 3 Temperature | Text-based cal cert (PDF) | `parse_cal_pdf()` |
| SBE 4 Conductivity | Text-based cal cert (PDF) | `parse_cal_pdf()` |
| SBE 9 Pressure | Text-based cal cert (PDF) | `parse_cal_pdf()` |
| SBE 43 / 63 Oxygen | Text-based cal cert (PDF) | `parse_cal_pdf()` |
| FLNTU (CHL + NTU) | Characterisation sheet (PDF) | `cruise_tools.flort.parse_flort_pdf()` |
| ECO CDOM | Scanned characterisation sheet (PDF, OCR) | `cruise_tools.cdom.parse_cdom_pdf()` |
| CTDMO (SBE 37-IM/IMP) | `.cal` file | `cruise_tools.ctdmo.parse_cal_file()` |
| DOSTA (Aanderaa Optode 4831/4330) | Multipoint cal certificate (PDF, tables only) | `cruise_tools.dosta.parse_dosta_pdf()` |
| FLORT ECO Triplet (e.g. BBFL2W) | `.dev` calibration file | `cruise_tools.flort.parse_dev_file()` |
| OPTAA (WET Labs AC-S) | `.dev` calibration file + 2 companion `.ext` matrix files | `cruise_tools.optaa.parse_dev_file()` |
| DOFSTK (SBE 43F fast-response oxygen) | `.cal` file + Soc-adjusted cal certificate PDF | `cruise_tools.dofstk.parse_dofstk()` |
| PARAD-K (Biospherical QSP-2200 PAR sensor) | Cal certificate PDF | `cruise_tools.parad.parse_parad_pdf()` |
| NUTNR-B (Satlantic/Sea-Bird SUNA V2 nitrate analyzer) | `.CAL` file | `cruise_tools.nutnr.parse_cal_file()` |

> **Note — CDOM PDFs:** these are typically scanned images with no embedded
> text layer.  The tool automatically applies OCR (Tesseract at 500 DPI with
> contrast enhancement).  Tesseract must be installed; conda users get it
> automatically via `environment.yml`.

---

## Python API

### CTD frame: XMLCON parser

```python
from cruise_tools.ctd import XMLCONParser

parser = XMLCONParser("AR98A_013.XMLCON")
print(parser.df)                       # full sensor table
row = parser.get_sensor(6)             # a single sensor, by index
df = parser.get_sensors_by_type("OxygenSensor")
```

### CTD frame: calibration PDF parser

```python
from cruise_tools.ctd import parse_cal_pdf, compare_cal_to_xmlcon, print_comparison
from cruise_tools.ctd import XMLCONParser

cal = parse_cal_pdf("SBE_43_O0264_12Nov24.pdf")
parser = XMLCONParser("AR98A_013.XMLCON")
result = compare_cal_to_xmlcon(cal, parser.get_sensor(6))
print_comparison(cal, parser.get_sensor(6))
```

### FLORT: characterisation sheet parser

```python
from cruise_tools.flort import parse_flort_pdf

chl, ntu = parse_flort_pdf("FLNTURTD-7730_CharSheet.pdf")
```

### CDOM: characterisation sheet parser (OCR)

```python
from cruise_tools.cdom import parse_cdom_pdf, cdom_pdf_parser

# On Windows, if Tesseract is not on PATH:
cdom_pdf_parser.TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
cdom = parse_cdom_pdf("FLNCDOM-1963_20220421.pdf")
```

### CTDMO: `.cal` file vs. CI calibration CSV

```python
from cruise_tools.ctdmo import parse_cal_file, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_cal_file("12584_1_.cal")
print(get_metadata("12584_1_.cal"))
# {'instrument_type': 'SBE37', 'serial': '37-12584',
#  't_cal_date': '10-Jun-26', 'c_cal_date': '10-Jun-26', 'p_cal_date': '22-May-26'}

result = compare_source_to_ci(source, "CGINS-CTDMOS-12584__20260610.csv")
print(summarize(result))
# {'match': 23, 'missing_in_source': 1}   # CC_p_range isn't in the .cal file —
#                                          # it's the sensor's rated pressure
#                                          # range and must be verified by hand.

result.to_csv("12584_compare_report.csv", index=False)
```

### DOSTA: cal certificate PDF vs. CI calibration CSV

```python
from cruise_tools.dosta import parse_dosta_pdf, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_dosta_pdf("DOSTA-D_Optode-4831_SN_466_Multipoint_Calibration_2025-03-03.pdf")
print(get_metadata("DOSTA-D_Optode-4831_SN_466_Multipoint_Calibration_2025-03-03.pdf"))
# {'serial': '466', 'product': '4831', 'calibration_date': '2025-03-03',
#  'firmware_version': '5.3.1'}

result = compare_source_to_ci(source, "CGINS-DOSTAD-00466__20250303.csv")
print(summarize(result))
# {'match': 2}   # CC_csv (7-element SVU foil coefficients) and
#                # CC_conc_coef ([offset, slope]) both match exactly.
```

The comparator (`cruise_tools.common.compare_source_to_ci`) is
instrument-agnostic: any parser that returns a DataFrame with
`serial, name, value` columns (using the CI CSV's `CC_*` coefficient names)
can be compared the same way. `value` may be a plain scalar, a flat Python
list (e.g. DOSTA's 7-element `CC_csv`), or a nested list / matrix (e.g.
OPTAA's 85x36 `CC_tcarray`) — array and matrix values are compared
element-wise (recursively) and the largest delta is reported. The CI CSV's
`"[...]"`-style cells are parsed automatically, and `"SheetRef:<name>"`
cells are resolved against a companion `<csv_basename>__<name>.ext` file
sitting next to the CSV.

### FLORT (ECO Triplet, e.g. BBFL2W): `.dev` file vs. CI calibration CSV

```python
from cruise_tools.flort import parse_dev_file, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_dev_file("BBFL2W-1116.dev")
print(get_metadata("BBFL2W-1116.dev"))
# {'model': 'BBFL2W', 'serial': '1116', 'created_on': '2/27/25'}

result = compare_source_to_ci(source, "CGINS-FLORTD-01116__20250227.csv")
print(summarize(result))
# {'match': 7, 'missing_in_source': 3}   # CC_angular_resolution,
#   CC_depolarization_ratio, CC_scattering_angle are fixed BBFL2W-model
#   constants, not in the .dev file — verify against the sensor datasheet.
```

### OPTAA (WET Labs AC-S): `.dev` file vs. CI calibration CSV (+ matrices)

The AC-S carries per-wavelength calibration data (~85 wavelengths) plus a
temperature-correction *matrix* for each channel (absorption/attenuation),
85 wavelengths x 36 temperature bins each. Those two matrices are large
enough that the CI CSV doesn't inline them — the row's value is a pointer,
`SheetRef:CC_tcarray`, to a companion file
(`<csv_basename>__CC_tcarray.ext`) next to the main CSV. As long as that
companion file sits alongside the CSV (as it does when both come from the
same CI export), `compare_source_to_ci` resolves it automatically:

```python
from cruise_tools.optaa import parse_dev_file, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_dev_file("ACS152.dev")
print(get_metadata("ACS152.dev"))
# {'serial': 'ACS-152', 'electronics_id': '53000098',
#  'n_wavelengths': 85, 'n_temperature_bins': 36}

# CGINS-OPTAAD-00152__20260629__CC_tcarray.ext and
# CGINS-OPTAAD-00152__20260629__CC_taarray.ext must be in the same folder
# as the CSV below — that's how the CI export bundles them.
result = compare_source_to_ci(source, "CGINS-OPTAAD-00152__20260629.csv")
print(summarize(result))
# {'match': 8}   # includes the two 85x36 matrices, compared element-wise
```

### DOFSTK (SBE 43F fast-response oxygen): `.cal` file + Soc-adjusted PDF

The first instrument here where the CI CSV is filled in from *two*
independent documents. The `.cal` file is authoritative for
`CC_frequency_offset` and the four residual-temperature-correction
factors; the certificate PDF is authoritative for
`CC_oxygen_signal_slope` (Soc), because SBE 43 sensors often get a
post-calibration Soc adjustment — fit against reference samples — that's
documented only on the certificate ("Soc = 3.0753e-04 **(adj)**"), not in
the `.cal` file:

```python
from cruise_tools.dofstk import parse_dofstk, get_cal_metadata, get_soc_pdf_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_dofstk("2725.cal", "SBE_43F_O2725_15May26-Soc-adjusted.pdf")
print(get_cal_metadata("2725.cal"))
# {'serial': '43-2725', 'o2_cal_date': '17-Mar-26',
#  'factory_soc': 0.000293243, 'tau20': 0.98}
print(get_soc_pdf_metadata("SBE_43F_O2725_15May26-Soc-adjusted.pdf"))
# {'serial': '43-2725', 'calibration_date': '2026-03-17', 'soc_is_adjusted': True}

result = compare_source_to_ci(source, "CGINS-DOFSTK-02725__20260317.csv")
print(summarize(result))
# {'match': 6}
# Note: factory Soc (0.000293243, from the .cal file) is intentionally
# NOT used for CC_oxygen_signal_slope — the certificate's adjusted Soc
# (0.00030753) is ~5% different and is what the CI CSV actually contains.
```

### PARAD-K (Biospherical QSP-2200 PAR sensor): cal certificate PDF

```python
from cruise_tools.parad import parse_parad_pdf, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_parad_pdf("PARAD-K_QSP2200_SN_20465_Calibration_2026-05-07.pdf")
print(get_metadata("PARAD-K_QSP2200_SN_20465_Calibration_2026-05-07.pdf"))
# {'serial': '20465', 'model': 'QSP2200', 'calibration_date': '2026-05-07'}

result = compare_source_to_ci(source, "CGINS-PARADK-20465__20260507.csv")
print(summarize(result))
# {'match': 2}   # CC_dark_offset and CC_scale_wet (the *wet* factor —
#                # the dry factor isn't used since this sensor is deployed submerged)
```

Some PARAD-K certificates are scanned images with no embedded text layer
(unlike the more typical text-based ones) — `parse_parad_pdf()` detects
this automatically and falls back to OCR, the same way CDOM's
characterisation sheets always do. On Windows, if Tesseract isn't on
PATH: `cruise_tools.parad.pdf_parser.TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`.

### NUTNR-B (Satlantic/Sea-Bird SUNA V2 nitrate analyzer): `.CAL` file

```python
from cruise_tools.nutnr import parse_cal_file, get_metadata
from cruise_tools.common import compare_source_to_ci, summarize

source = parse_cal_file("SNA1063N.CAL")
print(get_metadata("SNA1063N.CAL"))
# {'serial': 'NTR-1063', 't_cal_swa': '20.00', 'path_length_mm': '10',
#  'integration_period': '175', 'creation_time': '01-Apr-2026 19:03:58'}

result = compare_source_to_ci(source, "CGINS-NUTNRB-01063__20260401.csv")
print(summarize(result))
# {'match': 5, 'missing_in_source': 2}   # CC_lower/upper_wavelength_limit_
#   for_spectra_fit are fixed algorithm parameters, not per-unit
#   calibration values — not in the .CAL file, correctly flagged.
```

---

## Adding a new instrument family

1. Create `cruise_tools/<family>/` with an `__init__.py` and a parser module.
2. Write one function per source file: `parse_<something>(filepath) -> pd.DataFrame`
   with columns `serial`, `name`, `value` (and optionally `source_file`), using
   the **same coefficient names as that instrument's CI CSV** (e.g. `CC_a0`).
   If the vendor file's key names don't already match, map them the way
   `cruise_tools/ctdmo/cal_parser.py` maps `TA0 → CC_a0`, `PA0 → CC_pa0`, etc.
   Most instruments need only one source file; if yours needs more than one
   (like DOFSTK's `.cal` + certificate PDF), write one parser per file plus
   a small combine function that concatenates them (see
   `cruise_tools/dofstk/combined.py`).
3. Register it in `INSTRUMENT_PARSERS` at the top of `cruise_tools/cal_tool.py`:
   a `"sources"` list (one entry per input file, each with a `key`, `label`,
   `parse` function, and `file_types`) and a `"combine"` function that turns
   the loaded per-source DataFrames into one. The Tab 4 "Source file(s)"
   section renders itself from this list automatically — one instrument, one
   button; two instruments, two buttons — no GUI code to write.
4. `cruise_tools.common.compare_source_to_ci` handles the comparison,
   Δ%, and status classification (`match` / `mismatch` / `missing_in_ci` /
   `missing_in_source`) for you.

---

## Coefficient name mapping (cal PDF → XMLCON) — *CTD frame only*

SeaBird certificate PDFs and XMLCON files use different naming conventions.
The parser handles these automatically:

| Sensor | PDF name | XMLCON column |
|--------|----------|---------------|
| Conductivity | `g`, `h`, `i`, `j` | `eq1_g`, `eq1_h`, `eq1_i`, `eq1_j` |
| Conductivity | `cpcor`, `ctcor` | `eq1_c_pcor`, `eq1_c_tcor` |
| Pressure | `ad590m`, `ad590b` | `ad590_m`, `ad590_b` |
| Oxygen | `soc` | `eq1_soc` |
| Oxygen | `voffset` | `eq1_offset` |
| Oxygen | `a`, `b`, `c`, `e` | `eq1_a`, `eq1_b`, `eq1_c`, `eq1_e` |
| Oxygen | `tau20`, `h1`–`h3`, `d1`, `d2` | `eq1_tau20`, `eq1_h1`–`eq1_h3`, `eq1_d1`, `eq1_d2` |
| FLNTU CHL | `scale_factor`, `dark_counts` | `scale_factor`, `vblank` |
| FLNTU NTU | `scale_factor`, `dark_counts` | `scale_factor`, `dark_voltage` |
| CDOM | `scale_factor`, `dark_counts` | `scale_factor`, `vblank` |

> `eq1_d0` (oxygen) is a firmware constant not present in the calibration
> certificate; it will always appear in the *XMLCON only* section.
> `cpcor` and `ctcor` (conductivity) are nominal values; they are stored and
> flagged as nominal in the `_nominal` set of the returned dict.

## Coefficient name mapping (`.cal` → CI CSV) — *CTDMO only*

| `.cal` key | CI CSV `name` |
|---|---|
| `TA0`–`TA3` | `CC_a0`–`CC_a3` |
| `CG`, `CH`, `CI`, `CJ` | `CC_g`, `CC_h`, `CC_i`, `CC_j` |
| `CTCOR`, `CPCOR`, `WBOTC` | `CC_ctcor`, `CC_cpcor`, `CC_wbotc` |
| `PA0`–`PA2` | `CC_pa0`–`CC_pa2` |
| `PTCA0`–`PTCA2` | `CC_ptca0`–`CC_ptca2` |
| `PTCB0`–`PTCB2` | `CC_ptcb0`–`CC_ptcb2` |
| `PTEMPA0`–`PTEMPA2` | `CC_ptempa0`–`CC_ptempa2` |
| *(not in `.cal` file)* | `CC_p_range` — pressure sensor's rated full-scale range; comes from the cal certificate header / nameplate, not the coefficient dump. Always flagged `missing_in_source` for manual verification. |

`INSTRUMENT_TYPE` + `SERIALNO` in the `.cal` file are combined into the CI
serial format (`SBE37` + `12584` → `37-12584`).

## Coefficient name mapping (cal certificate → CI CSV) — *DOSTA only*

| Certificate row | CI CSV `name` | Shape |
|---|---|---|
| `SVUFoilCoef` (7 values) | `CC_csv` | 7-element list |
| `ConcCoef` (`0 (Offset)`, `1 (Slope)`) | `CC_conc_coef` | 2-element list `[offset, slope]` |

`TempCoef` and `PhaseCoef` also appear on the certificate but are **not**
part of the CI CSV for this asset class — OOI's oxygen-concentration
algorithm doesn't consume them directly — so the parser intentionally
leaves them out rather than generating spurious "missing_in_ci" rows.

## Coefficient name mapping (`.dev` → CI CSV) — *FLORT (ECO Triplet) only*

| `.dev` row | CI CSV `name` |
|---|---|
| `lambda=4`, value 1 | `CC_scale_factor_volume_scatter` |
| `lambda=4`, value 2 | `CC_dark_counts_volume_scatter` |
| `lambda=4`, value 3 | `CC_measurement_wavelength` |
| `CHL=6`, value 1 | `CC_scale_factor_chlorophyll_a` |
| `CHL=6`, value 2 | `CC_dark_counts_chlorophyll_a` |
| `CDOM=8`, value 1 | `CC_scale_factor_cdom` |
| `CDOM=8`, value 2 | `CC_dark_counts_cdom` |
| *(not in `.dev` file)* | `CC_angular_resolution`, `CC_depolarization_ratio`, `CC_scattering_angle` — fixed characteristics of the BBFL2W sensor design (same for every unit of this model), not per-unit calibration values. Always flagged `missing_in_source` for manual verification against the datasheet. |

The serial number comes straight from the `.dev` file's header line
(`ECO  BBFL2W-1116` → serial `1116`), no reformatting needed.

## Coefficient name mapping (`.dev` → CI CSV) — *OPTAA (AC-S) only*

| `.dev` source | CI CSV `name` | Shape |
|---|---|---|
| `Tcal:` value in the header comment line | `CC_tcal` | scalar |
| Wavelength row, `C<wl>` token | `CC_cwlngth` | 85-element list |
| Wavelength row, 4th column | `CC_ccwo` | 85-element list |
| Wavelength row, `A<wl>` token | `CC_awlngth` | 85-element list |
| Wavelength row, 5th column | `CC_acwo` | 85-element list |
| "temperature bins" row | `CC_tbins` | 36-element list |
| Wavelength row, C-channel temperature-correction columns | `CC_tcarray` | 85x36 matrix (via `SheetRef:CC_tcarray` → `.ext` file) |
| Wavelength row, A-channel temperature-correction columns | `CC_taarray` | 85x36 matrix (via `SheetRef:CC_taarray` → `.ext` file) |

The `.dev` file's own "Serial number" header field (e.g. `53000098`) is the
meter's internal electronics ID, **not** the OOI unit serial used in the CI
CSV — the serial (`ACS-152`) is derived from the filename (`ACS152.dev`)
instead. `Ical` (also in the header comment) isn't part of this CI CSV and
is left out, the same way `TempCoef`/`PhaseCoef` are left out for DOSTA.

## Coefficient name mapping (`.cal` + PDF → CI CSV) — *DOFSTK only*

| Source | `.cal` key / PDF field | CI CSV `name` |
|---|---|---|
| `.cal` | `FOFFSET` | `CC_frequency_offset` |
| `.cal` | `A` | `CC_residual_temperature_correction_factor_a` |
| `.cal` | `B` | `CC_residual_temperature_correction_factor_b` |
| `.cal` | `C` | `CC_residual_temperature_correction_factor_c` |
| `.cal` | `E` | `CC_residual_temperature_correction_factor_e` |
| PDF | `Soc = ... (adj)` | `CC_oxygen_signal_slope` |

`SOC` and `TAU20` in the `.cal` file are intentionally **not** emitted as
coefficient rows — `SOC` is the pre-adjustment factory value (the PDF's
adjusted Soc is what's actually used), and `TAU20` isn't part of this CI
CSV at all, the same pattern as leaving out DOSTA's `TempCoef`/`PhaseCoef`
or FLORT's fixed sensor constants. Both are still available via
`get_cal_metadata()` for reference. The serial (`43-2725`) is built the
same way as CTDMO's: model number extracted right after `SBE` in
`INSTRUMENT_TYPE` (`SBE43F` → `43`), joined to `SERIALNO` with a dash.

## Coefficient name mapping (cal certificate → CI CSV) — *PARAD-K only*

| Certificate field | CI CSV `name` |
|---|---|
| `Sensor Dark Voltage` (mV) | `CC_dark_offset` |
| `Wet Calibration Factor` (Volts / (quanta/(cm²·s))) | `CC_scale_wet` |

The `Dry Calibration Factor`, `Immersion Coefficient`, `Lamp Integrated PAR
Irradiance`, and other certificate fields aren't part of this CI CSV and
are left out — only the wet-immersion factor is used operationally, since
this sensor is deployed submerged. The serial number (`20465`) is used
as-is, with no model-number prefix (unlike CTDMO/DOFSTK's `37-`/`43-`).

## Coefficient name mapping (`.CAL` → CI CSV) — *NUTNR-B only*

| `.CAL` source | CI CSV `name` | Shape |
|---|---|---|
| `T_CAL` header value | `CC_cal_temp` | scalar |
| `Wavelength` column (`E,` rows) | `CC_wl` | list, one per wavelength |
| `NO3` column | `CC_eno3` | list |
| `SWA` column | `CC_eswa` | list |
| `Reference` column | `CC_di` | list — reference spectrum measured in DI water |
| *(not in `.CAL` file)* | `CC_lower_wavelength_limit_for_spectra_fit`, `CC_upper_wavelength_limit_for_spectra_fit` — fixed processing-algorithm parameters (which wavelength range the fitting routine uses), not per-unit calibration values. Always flagged `missing_in_source`. |

Two gotchas this parser is careful about: the `TSWA` column exists in the
file but isn't part of this CI CSV, so it's left out; and `T_CAL_SWA` is a
genuinely different header field from `T_CAL` (their values just happen
to coincide in the example above) — the parser only reads `T_CAL` for
`CC_cal_temp`, never `T_CAL_SWA`. The serial (`NTR-1063`) comes from the
`SUNA <n>` header line, falling back to digits in the filename
(`SNA1063N.CAL`) if that line isn't found.

---

## Known limitations & notes

- **CDOM scan quality:** OCR accuracy depends on scan resolution.  The tool
  uses 500 DPI with contrast enhancement; very low-quality scans may produce
  incorrect values.  Always verify visually against the source PDF.
- **FLNTU Analog Range:** the XMLCON stores *Analog Range 1* values; the
  parser extracts Analog Range 1 to match.
- **`eq1_soc` discrepancy:** the oxygen cal certificate may show a slightly
  different `Soc` than the XMLCON if the value was manually adjusted after
  the calibration date.  The tool will flag this as a mismatch.
- **Sensor type detection (CTD frame):** the sensor type is detected from
  the PDF title line.  If a certificate has an unusual title, add an entry
  to `SENSOR_TYPE_MAP` in `cal_pdf_parser.py`.
- **CTDMO `CC_p_range`:** intentionally not guessed — always flagged for
  manual check against the certificate/nameplate (see table above).

## License

MIT
