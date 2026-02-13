"""
SeaBird CTD Calibration Tool — GUI
====================================
Tabs:
  1. XMLCON Files   — load / inspect individual XMLCON files
  2. Cast Diff      — compare coefficients across casts (consecutive N-1 vs N)
  3. Cal PDF        — load calibration PDFs and compare against XMLCON values

Place this file in the same directory as xmlcon_parser_enhanced.py and
cal_pdf_parser.py (or add that directory to sys.path).

Run:  python ctd_cal_tool.py
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from xmlcon_parser_enhanced import XMLCONParser
    import cal_pdf_parser
    from cal_pdf_parser import (
        parse_cal_pdf, parse_flntu_pdf, parse_cdom_pdf,
        compare_cal_to_xmlcon,
    )
    import pandas as pd
except ImportError as e:
    print(f"Import error: {e}\n"
          "Ensure xmlcon_parser_enhanced.py and cal_pdf_parser.py are in "
          "the same directory as this script.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Constants & theme
# ─────────────────────────────────────────────────────────────────────────────

C = {
    "bg":       "#0f1117",
    "panel":    "#1a1d27",
    "border":   "#2a2d3e",
    "accent":   "#4f9cf9",
    "green":    "#3dd68c",
    "orange":   "#f97b4f",
    "text":     "#e2e8f0",
    "muted":    "#6b7280",
    "hdr_bg":   "#141720",
    "sel":      "#1e3a5f",
    "row_ok":   "#162a1f",
    "row_bad":  "#2a1810",
    "row_dim":  "#16181f",
}

FB = ("Segoe UI", 10)
FB_BOLD = ("Segoe UI", 10, "bold")
FM = ("Consolas", 10)

_FLNTU_TYPES = {"FluoroWetlabECO_AFL_FL_Sensor", "TurbidityMeter"}

SENSOR_LABELS = {
    "TemperatureSensor":                  "Temperature (SBE 3)",
    "ConductivitySensor":                 "Conductivity (SBE 4)",
    "PressureSensor":                     "Pressure (SBE 9)",
    "OxygenSensor":                       "Oxygen (SBE 43/63)",
    "FluoroWetlabECO_AFL_FL_Sensor":      "Fluorometer CHL (FLNTU)",
    "TurbidityMeter":                     "Turbidity (FLNTU)",
    "FluoroWetlabCDOM_Sensor":            "CDOM Fluorometer",
    "WET_LabsCStar":                      "C-Star Transmissometer",
    "PAR_BiosphericalLicorChelseaSensor": "PAR Sensor",
    "AltimeterSensor":                    "Altimeter",
    "SPAR_Sensor":                        "SPAR Sensor",
    "NotInUse":                           "Not In Use",
}

# Two representative coefficients shown in the XMLCON file list
KEY_COEFFS = {
    "TemperatureSensor":             ("g",            "h"),
    "ConductivitySensor":            ("eq1_g",        "eq1_h"),
    "PressureSensor":                ("c1",           "slope"),
    "OxygenSensor":                  ("eq1_soc",      "eq1_e"),
    "FluoroWetlabECO_AFL_FL_Sensor": ("scale_factor", "vblank"),
    "TurbidityMeter":                ("scale_factor", "dark_voltage"),
    "FluoroWetlabCDOM_Sensor":       ("scale_factor", "vblank"),
    "WET_LabsCStar":                 ("m",            "b"),
}

META_COLS = {"sensor_index", "sensor_type", "sensor_id",
             "serial_number", "calibration_date"}


def slabel(t: str) -> str:
    return SENSOR_LABELS.get(t, t)


def fmtv(v) -> str:
    """Format a coefficient value for display."""
    if v is None:
        return "—"
    try:
        if pd.isna(v):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(v, float):
        return f"{v:.8g}"
    return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# Notebook logic  (direct port of cells 1–4)
# ─────────────────────────────────────────────────────────────────────────────

def extract_cast_num(filepath: str) -> str:
    """
    Port of the notebook's cast-number extraction:
        cast_num = f.split('_')[-1].split('.')[0]
    Returns the last underscore-delimited token before the extension.
    Falls back to the full stem if that token is not all-digits.
    """
    stem = Path(filepath).stem          # 'AR98A_013'
    last = stem.split("_")[-1]          # '013'
    return last if last.isdigit() else stem


def build_sensor_calibrations(xmlcons: dict) -> dict:
    """
    Port of Cell 2.
    Returns:  sensor_type -> cast_num -> [records]
    where records are dicts of all non-null columns from get_sensors_by_type().
    Cast keys are sorted numerically so consecutive comparison is correct.
    """
    sensor_calibrations: dict = defaultdict(dict)

    # Sort by cast number (numeric) exactly as the notebook does
    try:
        ordered = sorted(xmlcons.items(),
                         key=lambda kv: int(extract_cast_num(kv[0])))
    except ValueError:
        ordered = sorted(xmlcons.items(),
                         key=lambda kv: extract_cast_num(kv[0]))

    # Collect all sensor types first (notebook gathers them before looping)
    all_sensor_types: set = set()
    for _, parser in ordered:
        all_sensor_types.update(parser.df["sensor_type"].unique())
    all_sensor_types.discard("NotInUse")

    for path, parser in ordered:
        cast_num = extract_cast_num(path)
        for sensor_type in all_sensor_types:
            sensor_data = parser.get_sensors_by_type(sensor_type).dropna(axis=1)
            if len(sensor_data) > 0:
                sensor_calibrations[sensor_type][cast_num] = \
                    sensor_data.to_dict("records")

    return dict(sensor_calibrations)


def compute_changes_summary(sensor_calibrations: dict) -> list[dict]:
    """
    Port of Cell 3.
    Compares consecutive casts for each sensor type and returns a list of
    change-event dicts, one per (sensor_type, from_cast, to_cast) transition
    that has at least one changed column.
    """
    summary = []

    for sensor_type in sorted(sensor_calibrations):
        cast_data = sensor_calibrations[sensor_type]

        try:
            casts = sorted(cast_data.keys(), key=lambda x: int(x))
        except ValueError:
            casts = sorted(cast_data.keys())

        if len(casts) < 2:
            continue

        for i in range(1, len(casts)):
            prev_cast = casts[i - 1]
            curr_cast = casts[i]
            prev_data = cast_data[prev_cast]
            curr_data = cast_data[curr_cast]

            if prev_data == curr_data:
                continue

            prev_df = pd.DataFrame(prev_data)
            curr_df = pd.DataFrame(curr_data)

            changed_cols = []
            if len(curr_df) == len(prev_df):
                for col in curr_df.columns:
                    if col in prev_df.columns:
                        if not curr_df[col].equals(prev_df[col]):
                            changed_cols.append(col)

            summary.append({
                "sensor_type":    sensor_type,
                "from_cast":      prev_cast,
                "to_cast":        curr_cast,
                "changed_cols":   changed_cols if changed_cols else ["(structure changed)"],
                "prev_data":      prev_data,
                "curr_data":      curr_data,
            })

    return summary


def compare_calibrations_detailed(sensor_calibrations: dict,
                                   sensor_type: str,
                                   cast1: str,
                                   cast2: str) -> list[dict]:
    """
    Port of Cell 4 (compare_calibrations_detailed).
    Returns a list of per-parameter rows: {param, prev_val, curr_val, changed}.
    """
    data1 = sensor_calibrations.get(sensor_type, {}).get(cast1)
    data2 = sensor_calibrations.get(sensor_type, {}).get(cast2)
    if not data1 or not data2:
        return []

    prev_df = pd.DataFrame(data1)
    curr_df = pd.DataFrame(data2)

    all_cols = sorted(set(prev_df.columns) | set(curr_df.columns))
    rows = []
    for col in all_cols:
        if col in META_COLS:
            continue
        pv = prev_df[col].iloc[0] if (col in prev_df.columns and len(prev_df) > 0) else None
        cv = curr_df[col].iloc[0] if (col in curr_df.columns and len(curr_df) > 0) else None
        rows.append({"param": col, "prev_val": pv, "curr_val": cv,
                     "changed": (pv != cv)})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Widget helpers
# ─────────────────────────────────────────────────────────────────────────────

_style_counter = 0


def dark_treeview(parent, cols: list[tuple], height=12):
    """
    Returns (container_frame, ttk.Treeview).
    cols: list of (col_id, heading_text, pixel_width)
    """
    global _style_counter
    _style_counter += 1
    sname = f"DT{_style_counter}.Treeview"
    s = ttk.Style()
    s.configure(sname,
                background=C["panel"], foreground=C["text"],
                fieldbackground=C["panel"],
                rowheight=24, font=FB, borderwidth=0)
    s.configure(f"{sname}.Heading",
                background=C["hdr_bg"], foreground=C["accent"],
                font=FB_BOLD, relief="flat")
    s.map(sname,
          background=[("selected", C["sel"])],
          foreground=[("selected", C["text"])])

    frame = tk.Frame(parent, bg=C["panel"])
    col_ids = [c[0] for c in cols]
    tree = ttk.Treeview(frame, columns=col_ids, show="headings",
                        height=height, style=sname)
    for cid, heading, width in cols:
        tree.heading(cid, text=heading)
        tree.column(cid, width=width, minwidth=30, anchor="w")

    vsb = ttk.Scrollbar(frame, orient="vertical",   command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


def make_log(parent, height=5):
    frame = tk.Frame(parent, bg=C["bg"])
    txt = tk.Text(frame, bg=C["bg"], fg=C["text"], font=FM,
                  relief="flat", bd=0, state="disabled",
                  wrap="none", height=height)
    vsb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=vsb.set)
    txt.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, txt


def dark_btn(parent, text, cmd, accent=False, warn=False, **kw):
    bg = C["orange"] if warn else (C["accent"] if accent else C["border"])
    fg = C["bg"] if (accent or warn) else C["text"]
    return tk.Button(parent, text=text, command=cmd,
                     bg=bg, fg=fg,
                     activebackground=C["green"], activeforeground=C["bg"],
                     relief="flat", bd=0, padx=12, pady=5,
                     font=FB_BOLD, cursor="hand2", **kw)


def lbl(parent, text="", bold=False, muted=False, bg=None, fg=None, **kw):
    resolved_fg = fg if fg is not None else (C["muted"] if muted else C["text"])
    return tk.Label(parent, text=text,
                    bg=bg if bg else C["panel"],
                    fg=resolved_fg,
                    font=FB_BOLD if bold else FB, **kw)


def frm(parent, bg=None, **kw):
    return tk.Frame(parent, bg=bg if bg else C["panel"], bd=0, **kw)


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

class CalTool(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("SeaBird CTD Calibration Tool")
        self.geometry("1380x920")
        self.configure(bg=C["bg"])
        self.minsize(980, 660)

        # ── state ──
        self.xmlcons: dict[str, XMLCONParser] = {}   # path -> parser
        self._selected_path: str | None = None
        self._sensor_cals: dict = {}                 # sensor_type -> cast -> [recs]
        self._changes: list[dict] = []               # output of compute_changes_summary
        self._cmp_sensor_row = None                  # pd.Series for Tab 3
        self._cal_dicts: list[dict] = []             # parsed PDFs for Tab 3

        self._build_ui()

    # =========================================================================
    # UI skeleton
    # =========================================================================

    def _build_ui(self):
        # ── title bar ──────────────────────────────────────────────────────
        tbar = frm(self, bg=C["bg"])
        tbar.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(tbar, text="SeaBird CTD", bg=C["bg"],
                 fg=C["muted"], font=("Segoe UI", 11)).pack(side="left")
        tk.Label(tbar, text=" Calibration Tool", bg=C["bg"],
                 fg=C["text"], font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(tbar, text="XMLCON · Cast Diff · Cal PDF",
                 bg=C["bg"], fg=C["muted"],
                 font=("Segoe UI", 10)).pack(side="right")
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", pady=(10, 0))

        # ── notebook ───────────────────────────────────────────────────────
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("D.TNotebook", background=C["bg"], borderwidth=0)
        st.configure("D.TNotebook.Tab", background=C["panel"],
                      foreground=C["muted"], padding=[18, 8], font=FB_BOLD)
        st.map("D.TNotebook.Tab",
               background=[("selected", C["bg"])],
               foreground=[("selected", C["accent"])])

        self.nb = ttk.Notebook(self, style="D.TNotebook")
        self.nb.pack(fill="both", expand=True)

        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        # ── log strip ──────────────────────────────────────────────────────
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        lf, self.log_txt = make_log(self, height=5)
        lf.pack(fill="x")
        self.log("Ready — load XMLCON files to begin.")

    # =========================================================================
    # Tab 1 · XMLCON Files
    # =========================================================================

    def _build_tab1(self):
        tab = frm(self.nb, bg=C["bg"])
        self.nb.add(tab, text="  XMLCON Files  ")

        # ── left panel: file list ──────────────────────────────────────────
        left = frm(tab, bg=C["bg"], width=320)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        lbl(left, "Loaded Files", bold=True, bg=C["bg"]).pack(anchor="w", pady=(0, 6))

        brow = frm(left, bg=C["bg"])
        brow.pack(fill="x", pady=(0, 6))
        dark_btn(brow, "＋ Files",  self._add_files,   accent=True).pack(side="left", padx=(0, 5))
        dark_btn(brow, "＋ Folder", self._add_folder              ).pack(side="left", padx=(0, 5))
        dark_btn(brow, "✕ Remove",  self._remove_file, warn=True  ).pack(side="left")

        ff, self.file_tree = dark_treeview(left, [
            ("cast", "Cast",  54),
            ("file", "File", 185),
            ("n",    "#",     30),
        ], height=26)
        ff.pack(fill="both", expand=True)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_file_select)

        # ── right panel: sensor detail ─────────────────────────────────────
        right = frm(tab, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        self._det_hdr = lbl(right, "Select a file to inspect",
                             bold=True, bg=C["bg"], fg=C["muted"])
        self._det_hdr.pack(anchor="w", pady=(0, 6))

        sf2, self.sensor_tree = dark_treeview(right, [
            ("idx",  "#",            38),
            ("type", "Sensor Type", 235),
            ("sn",   "Serial No.",  130),
            ("cal",  "Cal Date",    110),
            ("c1",   "Key Coeff 1", 175),
            ("c2",   "Key Coeff 2", 175),
        ], height=26)
        sf2.pack(fill="both", expand=True)

    # ── Tab 1 callbacks ───────────────────────────────────────────────────────

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select XMLCON files",
            filetypes=[("XMLCON", "*.XMLCON *.xmlcon"), ("All", "*.*")])
        for p in paths:
            self._load_one(p)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select folder of XMLCON files")
        if not folder:
            return
        found = sorted(Path(folder).glob("*.XMLCON")) + \
                sorted(Path(folder).glob("*.xmlcon"))
        if not found:
            messagebox.showinfo("None found",
                                "No .XMLCON files found in that folder.")
            return
        for p in found:
            # Mirror notebook filter: skip deck-test files
            if "deck_test" in str(p).lower():
                self.log(f"Skipped (deck_test): {p.name}")
                continue
            self._load_one(str(p))

    def _load_one(self, path: str):
        if path in self.xmlcons:
            self.log(f"Already loaded: {Path(path).name}")
            return
        try:
            parser = XMLCONParser(path)
            self.xmlcons[path] = parser
            cast = extract_cast_num(path)
            n = len(parser.df[parser.df["sensor_type"] != "NotInUse"])
            self.file_tree.insert("", "end", iid=path,
                                  values=(cast, Path(path).name, n))
            self.log(f"Loaded cast {cast}  ·  {Path(path).name}  ({n} active sensors)")
            self._rebuild()
        except Exception as e:
            self.log(f"ERROR loading {Path(path).name}: {e}", error=True)

    def _remove_file(self):
        for iid in self.file_tree.selection():
            self.xmlcons.pop(iid, None)
            self.file_tree.delete(iid)
        self._selected_path = None
        self._clear_sensor_detail()
        self._rebuild()
        self.log("File(s) removed.")

    def _on_file_select(self, _=None):
        sel = self.file_tree.selection()
        if not sel:
            return
        self._selected_path = sel[0]
        self._show_sensor_detail(sel[0])
        self._refresh_tab3_sensors()

    def _show_sensor_detail(self, path: str):
        parser = self.xmlcons.get(path)
        if not parser:
            return
        cast = extract_cast_num(path)
        self._det_hdr.config(
            text=f"Cast {cast}  ·  {Path(path).name}", fg=C["text"])
        self._clear_sensor_detail()

        for _, row in parser.df.iterrows():
            st = row["sensor_type"]
            if st == "NotInUse":
                continue
            sn  = fmtv(row.get("serial_number"))
            cal = fmtv(row.get("calibration_date"))
            c1k, c2k = KEY_COEFFS.get(st, ("—", "—"))

            def _ks(k, row=row):
                if k == "—" or k not in row.index:
                    return "—"
                v = row.get(k)
                return f"{k}={fmtv(v)}" if pd.notna(v) else "—"

            self.sensor_tree.insert("", "end", values=(
                row["sensor_index"], slabel(st), sn, cal,
                _ks(c1k), _ks(c2k),
            ))

    def _clear_sensor_detail(self):
        for item in self.sensor_tree.get_children():
            self.sensor_tree.delete(item)

    # =========================================================================
    # Tab 2 · Cast Coefficient Diff
    # =========================================================================

    def _build_tab2(self):
        tab = frm(self.nb, bg=C["bg"])
        self.nb.add(tab, text="  Cast Coefficient Diff  ")

        # ── toolbar ────────────────────────────────────────────────────────
        tbar = frm(tab, bg=C["bg"])
        tbar.pack(fill="x", padx=14, pady=(14, 4))
        lbl(tbar, "Calibration Changes — Consecutive Cast Comparison",
            bold=True, bg=C["bg"]).pack(side="left")
        dark_btn(tbar, "↻ Refresh", self._refresh_tab2).pack(side="right")

        lbl(tab,
            "Each row is a (sensor type, sensor serial) transition where at least "
            "one coefficient changed between cast N-1 and cast N.  "
            "Click a row to see the full parameter breakdown below.",
            muted=True, bg=C["bg"]
            ).pack(anchor="w", padx=14, pady=(0, 8))

        # ── vertical paned: summary top / detail bottom ────────────────────
        pane = tk.PanedWindow(tab, orient="vertical",
                              bg=C["bg"], sashwidth=7,
                              sashrelief="flat", bd=0)
        pane.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # Summary tree
        sum_outer = frm(tab, bg=C["bg"])
        sf3, self.sum_tree = dark_treeview(sum_outer, [
            ("stype",   "Sensor Type",         210),
            ("sn",      "Serial No.",           110),
            ("from_c",  "From Cast",             80),
            ("to_c",    "To Cast",               80),
            ("changed", "Changed Parameters",   420),
        ], height=10)
        sf3.pack(fill="both", expand=True)
        self.sum_tree.tag_configure("chg", background=C["row_bad"])
        self.sum_tree.bind("<<TreeviewSelect>>", self._on_sum_select)
        pane.add(sum_outer, minsize=100)

        # Detail tree
        det_outer = frm(tab, bg=C["bg"])
        self._det2_hdr = lbl(det_outer,
                              "Select a row above for the full parameter breakdown.",
                              bold=True, bg=C["bg"], fg=C["muted"])
        self._det2_hdr.pack(anchor="w", pady=(8, 4))
        sf4, self.det_tree = dark_treeview(det_outer, [
            ("flag",  "",             26),
            ("param", "Parameter",  200),
            ("prev",  "Cast N-1",   210),
            ("curr",  "Cast N",     210),
            ("delta", "Δ %",        120),
        ], height=12)
        sf4.pack(fill="both", expand=True)
        self.det_tree.tag_configure("chg",   background=C["row_bad"],
                                             foreground=C["orange"])
        self.det_tree.tag_configure("same",  foreground=C["muted"])
        pane.add(det_outer, minsize=100)

    # ── Tab 2 callbacks ───────────────────────────────────────────────────────

    def _rebuild(self):
        """
        Recompute sensor_calibrations and changes_summary from all loaded
        parsers, then refresh both diff and comparison tabs.
        """
        self._sensor_cals = build_sensor_calibrations(self.xmlcons)
        self._changes     = compute_changes_summary(self._sensor_cals)
        self._refresh_tab2()
        self._refresh_tab3_sensors()

    def _refresh_tab2(self):
        for item in self.sum_tree.get_children():
            self.sum_tree.delete(item)
        for item in self.det_tree.get_children():
            self.det_tree.delete(item)
        self._det2_hdr.config(
            text="Select a row above for the full parameter breakdown.",
            fg=C["muted"])

        if len(self.xmlcons) < 2:
            self.sum_tree.insert("", "end",
                values=("Load 2+ XMLCON files to compare.", "", "", "", ""))
            return

        if not self._changes:
            self.sum_tree.insert("", "end",
                values=("No coefficient changes detected across all casts.", "", "", "", ""))
            return

        for ch in self._changes:
            # One summary row per (sensor_type, serial, from→to) transition.
            # A single transition can involve multiple sensors (e.g. two CTDs)
            # so we group by serial_number within the change entry.
            prev_df = pd.DataFrame(ch["prev_data"])
            curr_df = pd.DataFrame(ch["curr_data"])

            # Collect unique serial numbers involved
            sns = []
            if "serial_number" in curr_df.columns:
                sns = curr_df["serial_number"].dropna().astype(str).unique().tolist()
            sn_str = ", ".join(sns) if sns else "?"

            iid = f"{ch['sensor_type']}||{sn_str}||{ch['from_cast']}||{ch['to_cast']}"
            self.sum_tree.insert("", "end", iid=iid, tags=("chg",),
                values=(
                    slabel(ch["sensor_type"]),
                    sn_str,
                    ch["from_cast"],
                    ch["to_cast"],
                    ", ".join(ch["changed_cols"]),
                ))

        self.log(f"Cast diff: {len(self._changes)} change event(s) found.")

    def _on_sum_select(self, _=None):
        """Populate the detail tree from the selected summary row."""
        for item in self.det_tree.get_children():
            self.det_tree.delete(item)

        sel = self.sum_tree.selection()
        if not sel:
            return
        try:
            sensor_type, sn_str, cast1, cast2 = sel[0].split("||")
        except ValueError:
            return

        self._det2_hdr.config(
            text=f"{slabel(sensor_type)}  ·  SN {sn_str}  ·  "
                 f"Cast {cast1} → Cast {cast2}",
            fg=C["text"])

        rows = compare_calibrations_detailed(
            self._sensor_cals, sensor_type, cast1, cast2)

        if not rows:
            self.det_tree.insert("", "end",
                values=("", "No detail available.", "", "", ""))
            return

        for r in rows:
            pv, cv = fmtv(r["prev_val"]), fmtv(r["curr_val"])
            if r["changed"]:
                try:
                    delta = (abs(float(r["prev_val"]) - float(r["curr_val"]))
                             / (abs(float(r["prev_val"])) or 1) * 100)
                    delta_str = f"{delta:.6g}%"
                except Exception:
                    delta_str = "—"
                self.det_tree.insert("", "end", tags=("chg",),
                    values=("⚠", r["param"], pv, cv, delta_str))
            else:
                self.det_tree.insert("", "end", tags=("same",),
                    values=("", r["param"], pv, cv, ""))

    # =========================================================================
    # Tab 3 · Cal PDF Comparison
    # =========================================================================

    def _build_tab3(self):
        tab = frm(self.nb, bg=C["bg"])
        self.nb.add(tab, text="  Cal PDF Comparison  ")

        # ── left: sensor list ──────────────────────────────────────────────
        left = frm(tab, bg=C["bg"], width=280)
        left.pack(side="left", fill="y", padx=(14, 0), pady=14)
        left.pack_propagate(False)

        lbl(left, "Sensors  (selected XMLCON)",
            bold=True, bg=C["bg"]).pack(anchor="w", pady=(0, 4))
        lbl(left, "Select a file in the XMLCON tab first.",
            muted=True, bg=C["bg"]).pack(anchor="w", pady=(0, 6))

        sfl, self.cmp_tree = dark_treeview(left, [
            ("type", "Sensor",  162),
            ("sn",   "S/N",      86),
        ], height=26)
        sfl.pack(fill="both", expand=True)
        self.cmp_tree.bind("<<TreeviewSelect>>", self._on_cmp_sensor_select)

        # ── right: controls + results ──────────────────────────────────────
        right = frm(tab, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=14, pady=14)

        hdr_row = frm(right, bg=C["bg"])
        hdr_row.pack(fill="x", pady=(0, 6))
        self._cmp_hdr = lbl(hdr_row,
                             "Select a sensor to load its calibration PDF",
                             bold=True, bg=C["bg"], fg=C["muted"])
        self._cmp_hdr.pack(side="left")

        act = frm(right, bg=C["bg"])
        act.pack(fill="x", pady=(0, 8))
        dark_btn(act, "＋ Load Cal PDF",     self._load_cal_pdf,
                  accent=True).pack(side="left", padx=(0, 8))
        dark_btn(act, "↻ Re-run Comparison", self._run_comparison
                  ).pack(side="left", padx=(0, 20))
        lbl(act, "Tesseract path (Windows):",
            muted=True, bg=C["bg"]).pack(side="left", padx=(0, 4))
        self._tess_var = tk.StringVar()
        tk.Entry(act, textvariable=self._tess_var,
                 bg=C["border"], fg=C["text"],
                 insertbackground=C["text"],
                 relief="flat", font=FB, width=38).pack(side="left")

        self._pdf_info_var = tk.StringVar(value="No PDF loaded.")
        lbl(right, textvariable=self._pdf_info_var,
            muted=True, bg=C["bg"]).pack(anchor="w", pady=(0, 6))

        lbl(right, "Comparison Results",
            bold=True, bg=C["bg"]).pack(anchor="w", pady=(0, 4))

        rfl, self.res_tree = dark_treeview(right, [
            ("st",    "",            28),
            ("param", "Parameter",  165),
            ("cal",   "Cal PDF",    178),
            ("xml",   "XMLCON",     178),
            ("note",  "Note",       210),
        ], height=22)
        rfl.pack(fill="both", expand=True)
        self.res_tree.tag_configure("ok",     background=C["row_ok"],
                                              foreground=C["green"])
        self.res_tree.tag_configure("bad",    background=C["row_bad"],
                                              foreground=C["orange"])
        self.res_tree.tag_configure("xmlonly", foreground=C["muted"])

    # ── Tab 3 callbacks ───────────────────────────────────────────────────────

    def _refresh_tab3_sensors(self):
        for item in self.cmp_tree.get_children():
            self.cmp_tree.delete(item)
        self._cmp_sensor_row = None
        self._cal_dicts = []
        self._pdf_info_var.set("No PDF loaded.")
        self._clear_results()

        path = self._selected_path
        if not path or path not in self.xmlcons:
            return

        for _, row in self.xmlcons[path].df.iterrows():
            if row["sensor_type"] == "NotInUse":
                continue
            self.cmp_tree.insert("", "end",
                iid=str(row["sensor_index"]),
                values=(slabel(row["sensor_type"]),
                        fmtv(row.get("serial_number"))))

    def _on_cmp_sensor_select(self, _=None):
        sel = self.cmp_tree.selection()
        if not sel or not self._selected_path:
            return
        parser = self.xmlcons[self._selected_path]
        row = parser.get_sensor(int(sel[0]))
        self._cmp_sensor_row = row
        self._cal_dicts = []
        self._pdf_info_var.set("No PDF loaded — click '＋ Load Cal PDF'.")
        self._clear_results()
        self._cmp_hdr.config(
            text=(f"{slabel(row['sensor_type'])}   "
                  f"SN: {fmtv(row.get('serial_number'))}   "
                  f"Cal: {fmtv(row.get('calibration_date'))}"),
            fg=C["text"])

    def _load_cal_pdf(self):
        if self._cmp_sensor_row is None:
            messagebox.showwarning("No sensor selected",
                                   "Select a sensor from the list first.")
            return

        paths = filedialog.askopenfilenames(
            title="Select calibration PDF(s)",
            filetypes=[("PDF files", "*.pdf *.PDF"), ("All files", "*.*")])
        if not paths:
            return

        tess = self._tess_var.get().strip()
        if tess:
            cal_pdf_parser.TESSERACT_CMD = tess

        self._pdf_info_var.set("Parsing PDF(s)…")
        self.update_idletasks()

        stype = self._cmp_sensor_row["sensor_type"]

        def _work():
            dicts, errors = [], []
            for p in paths:
                try:
                    if stype == "FluoroWetlabCDOM_Sensor":
                        dicts.append(parse_cdom_pdf(p))
                    elif stype in _FLNTU_TYPES:
                        for rec in parse_flntu_pdf(p):
                            if rec["sensor_type"] == stype:
                                dicts.append(rec)
                    else:
                        dicts.append(parse_cal_pdf(p))
                except Exception as e:
                    errors.append(f"{Path(p).name}: {e}")
            self.after(0, lambda: self._on_parsed(dicts, errors))

        threading.Thread(target=_work, daemon=True).start()

    def _on_parsed(self, dicts, errors):
        for e in errors:
            self.log(f"Parse error — {e}", error=True)
        if not dicts:
            self._pdf_info_var.set("No valid PDFs parsed.")
            return
        self._cal_dicts = dicts
        names = ", ".join(d.get("source_file", "?") for d in dicts)
        self._pdf_info_var.set(f"Loaded: {names}")
        self.log(f"Parsed {len(dicts)} cal PDF(s): {names}")
        self._run_comparison()

    def _run_comparison(self):
        if not self._cal_dicts:
            messagebox.showinfo("No PDFs loaded",
                                "Load a calibration PDF first.")
            return
        if self._cmp_sensor_row is None:
            messagebox.showinfo("No sensor", "Select a sensor from the list.")
            return
        self._clear_results()
        for cal in self._cal_dicts:
            self._show_comparison(cal, self._cmp_sensor_row)

    def _show_comparison(self, cal: dict, xmlcon_row):
        result = compare_cal_to_xmlcon(cal, xmlcon_row)
        src = cal.get("source_file", "")

        # ── serial / date ──────────────────────────────────────────────────
        for field, cal_v, xml_v, ok in [
            ("serial_number",
             cal.get("serial_number"),
             xmlcon_row.get("serial_number"),
             result["serial_match"]),
            ("calibration_date",
             cal.get("calibration_date"),
             xmlcon_row.get("calibration_date"),
             result["date_match"]),
        ]:
            self.res_tree.insert("", "end",
                tags=("ok" if ok else "bad",),
                values=("✓" if ok else "✗", field,
                        fmtv(cal_v), fmtv(xml_v), src))

        # ── matched coefficients ───────────────────────────────────────────
        for param, val in sorted(result["coeff_matches"].items()):
            self.res_tree.insert("", "end", tags=("ok",),
                values=("✓", param, fmtv(val), fmtv(val), ""))

        # ── mismatched coefficients ────────────────────────────────────────
        for param, vals in sorted(result["coeff_mismatches"].items()):
            cv, xv = vals["cal"], vals["xmlcon"]
            try:
                pct  = abs(float(cv) - float(xv)) / (abs(float(xv)) or 1) * 100
                note = f"Δ {pct:.4f}%"
            except Exception:
                note = "type mismatch"
            self.res_tree.insert("", "end", tags=("bad",),
                values=("✗", param, fmtv(cv), fmtv(xv), note))

        # ── XMLCON-only (firmware constants / config flags) ────────────────
        for param in sorted(result["coeff_only_in_xmlcon"]):
            self.res_tree.insert("", "end", tags=("xmlonly",),
                values=("·", param, "—",
                        fmtv(xmlcon_row.get(param)), "XMLCON only"))

        # ── status log ─────────────────────────────────────────────────────
        nm = len(result["coeff_matches"])
        nf = len(result["coeff_mismatches"])
        if nf:
            self.log(f"{src}: {nm} match  |  {nf} MISMATCH — "
                     f"{', '.join(result['coeff_mismatches'])}", error=True)
        else:
            self.log(f"{src}: all {nm} coefficients match ✓")

    def _clear_results(self):
        for item in self.res_tree.get_children():
            self.res_tree.delete(item)

    # =========================================================================
    # Status log
    # =========================================================================

    def log(self, msg: str, error: bool = False):
        self.log_txt.config(state="normal")
        col = C["orange"] if error else C["green"]
        tag = f"t{self.log_txt.index('end')}"
        self.log_txt.tag_configure(tag, foreground=col)
        self.log_txt.insert("end", f"{'✗' if error else ' '} {msg}\n", tag)
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Entry point for the ``ctd-cal-tool`` console script."""
    app = CalTool()
    app.mainloop()


if __name__ == "__main__":
    main()
