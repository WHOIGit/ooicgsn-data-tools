# cruise_tools

A Python monorepo of field data processing tools for oceanographic research
cruises, maintained by WHOI CGSN.

All sub-packages share the `cruise_tools` Python namespace and are installed
independently, so you can use only the tools you need.

## Sub-packages

| Directory | PyPI name | Description |
|-----------|-----------|-------------|
| [`ctd/`](ctd/README.md) | `cruise-tools-ctd` | SeaBird CTD XMLCON parsing, calibration PDF comparison, and cast-diff GUI |
| [`anchor_survey/`](anchor_survey/README.md) | `cruise-tools-anchor-survey` | Anchor survey data processing |
| [`common/`](common/README.md) | `cruise-tools-common` | Shared utilities (date handling, file discovery, etc.) |

## Quick start

### 1 — Clone

```bash
git clone https://github.com/WHOIGit/cruise_tools.git
cd cruise_tools
```

### 2 — Create the environment

The conda environment installs all Python dependencies **and** the required
system binaries (Tesseract OCR, poppler) in one step:

```bash
conda env create -f environment.yml
conda activate cruise-tools
```

This also installs all sub-packages in editable (`pip install -e`) mode, so
changes to source files take effect immediately without reinstalling.

### 3 — pip-only alternative

If you prefer pip, first install system binaries manually:

| OS | Commands |
|----|----------|
| **Windows** | Download [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and [poppler](https://github.com/oschwartz10612/poppler-windows/releases); add both to PATH |
| **macOS** | `brew install tesseract poppler` |
| **Linux** | `sudo apt install tesseract-ocr poppler-utils` |

Then:

```bash
pip install -e ctd/ -e anchor_survey/ -e common/
```

## Importing sub-packages

```python
# CTD tools
from cruise_tools.ctd import XMLCONParser, parse_cal_pdf

# Anchor survey tools
from cruise_tools.anchor_survey import ...

# Shared utilities
from cruise_tools.common import ...
```

All three share the `cruise_tools` namespace because each `cruise_tools/`
directory inside the sub-package folders is a
[namespace package](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/)
(no `__init__.py` at that level). Python merges them automatically when all
sub-packages are installed.

## Launch the CTD calibration GUI

```bash
ctd-cal-tool
```

See [`ctd/README.md`](ctd/README.md) for full CTD tool documentation.

## Repository layout

```
cruise_tools/                         ← git repo root
│
├── environment.yml                   ← conda env (all sub-packages)
├── .gitignore
├── README.md                         ← this file
│
├── ctd/                              ← pip install -e ctd/
│   ├── pyproject.toml
│   ├── README.md
│   └── cruise_tools/ctd/             ← NO __init__.py here (namespace pkg)
│       ├── __init__.py
│       ├── xmlcon_parser_enhanced.py
│       ├── cal_pdf_parser.py
│       └── ctd_cal_tool.py
│
├── anchor_survey/                    ← pip install -e anchor_survey/
│   ├── pyproject.toml
│   ├── README.md
│   └── cruise_tools/anchor_survey/   ← NO __init__.py here (namespace pkg)
│       └── __init__.py
│
└── common/                           ← pip install -e common/
    ├── pyproject.toml
    ├── README.md
    └── cruise_tools/common/          ← NO __init__.py here (namespace pkg)
        └── __init__.py
```

> **The key rule:** the intermediate `cruise_tools/` directories inside each
> sub-package folder must **not** have an `__init__.py`. This is what allows
> Python to merge `cruise_tools.ctd`, `cruise_tools.anchor_survey`, and
> `cruise_tools.common` into a single namespace even though they come from
> separate installed packages.

## Adding a new tool

1. Create a new directory at the repo root, e.g. `my_tool/`
2. Mirror the layout of an existing sub-package:
   ```
   my_tool/
   ├── pyproject.toml          # name = "cruise-tools-my-tool"
   ├── README.md
   └── cruise_tools/my_tool/   # NO __init__.py at cruise_tools/ level
       └── __init__.py
   ```
3. Add `- "-e my_tool/"` to the pip section of `environment.yml`
4. Add a row to the sub-packages table in this README

## License

MIT
