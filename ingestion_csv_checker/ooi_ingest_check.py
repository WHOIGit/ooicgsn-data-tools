#!/usr/bin/env python3
"""
Sanity-check and diff OOI ingestion CSV files.

Two modes:

1. Single-file validation (always run, on every file given):
   - header matches the expected column set
   - reference_designator matches the standard OOI format
   - data_source / status use recognized values
   - no duplicate (parser, reference_designator, data_source) rows
   - every filename_mask path references the data folder implied by the
     file's own name (e.g. CP10CNSM_R00003_ingest.csv rows should point at
     .../CP10CNSM/R00003/...). Mobile assets (gliders/profilers) use a
     hyphenated "<array><MOAS-class>-<platform ID>" site code instead of
     a plain site code, e.g. GP05MOAS-PG380_R00001_ingest.csv, since all
     gliders share the same 05MOAS array-and-class code.

2. Two-file comparison (when two files are given):
   - matches rows between the old and new file by
     (parser, reference_designator, data_source), ignoring the data-folder
     number itself (R00002 vs R00003), which is expected to change
   - reports rows that are new, rows that were removed, rows whose
     status/notes changed, and rows whose filename_mask changed in some
     way *other* than the folder number (e.g. a different dcl/port)
   - tries to pair up "removed" + "added" rows that share the same
     reference_designator/data_source but a different parser, and reports
     them as "likely modified" (e.g. a driver was renamed) instead of as
     an unrelated add + remove

Usage
-----
python3 ooi_ingest_check.py NEW.csv                  # validate only
python3 ooi_ingest_check.py OLD.csv NEW.csv          # validate + diff

Exit status is non-zero if any errors (not just warnings) were found, so
this can be dropped into a pre-ingest CI check.
"""

import argparse
import csv
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

EXPECTED_COLUMNS = [
    "parser",
    "filename_mask",
    "reference_designator",
    "data_source",
    "status",
    "notes",
]

VALID_STATUSES = {"Available", "Expected", "Not Available"}
VALID_DATA_SOURCES = {"recovered_host", "recovered_inst", "telemetered"}

# e.g. CP10CNSM-MFC31-00-CPMENG000
REFDES_RE = re.compile(r"^[A-Z0-9]{8}-[A-Z0-9]{5}-[0-9]{2}-[A-Z0-9]{9}$")

# e.g. R00002, R00003 ...
FOLDER_RE = re.compile(r"\bR\d{5}\b")

# e.g. CP10CNSM_R00003_ingest.csv (fixed asset) or
# GP05MOAS-PG380_R00001_ingest.csv (mobile asset -- gliders/profilers all
# share the "05MOAS" array-and-class code, so the "site" is really
# "<array><MOAS-class>-<platform ID>", e.g. GP05MOAS-PG380).
FILENAME_RE = re.compile(r"^([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)_(R\d{5})_ingest\.csv$")


class IngestRow:
    """
    One data row from an ingest CSV, 1-indexed to match the file on disk.

    Parameters
    ----------
    lineno : int
        Line number of this row in the source file (the header is line 1,
        so the first data row is line 2).
    data : dict of {str : str}
        Mapping of column name (from :data:`EXPECTED_COLUMNS`) to the raw
        string value found in that column.
    n_fields_in_source : int
        Number of comma-separated fields actually present in the source
        line, before any padding to match the expected column count. Used
        to detect malformed rows (too few/many commas).

    Attributes
    ----------
    lineno : int
        See parameters.
    data : dict of {str : str}
        See parameters.
    n_fields_in_source : int
        See parameters.

    Examples
    --------
    >>> row = IngestRow(2, {"parser": "p", "reference_designator": "CP10CNSM-MFC31-00-CPMENG000",
    ...                      "data_source": "recovered_host"}, n_fields_in_source=6)
    >>> row["data_source"]
    'recovered_host'
    """

    def __init__(self, lineno, data, n_fields_in_source):
        self.lineno = lineno
        self.data = data
        self.n_fields_in_source = n_fields_in_source

    def __getitem__(self, field):
        """
        Look up a column value by name.

        Parameters
        ----------
        field : str
            Column name, e.g. ``"status"`` or ``"filename_mask"``.

        Returns
        -------
        str
            The value in that column, or ``""`` if the column is missing.
        """
        return self.data.get(field, "")

    @property
    def key(self):
        """
        tuple of (str, str, str) : Identity of a row that should be stable
        across a folder-number bump.

        Built from ``(parser, reference_designator, data_source)``. Two
        rows from different ingest CSVs with the same key are assumed to
        describe the same logical data stream.
        """
        return (self["parser"], self["reference_designator"], self["data_source"])

    @property
    def loose_key(self):
        """
        tuple of (str, str) : Identity ignoring parser.

        Built from ``(reference_designator, data_source)``. Used to spot
        "the driver for this stream changed" when matching removed rows
        against added rows during a diff.
        """
        return (self["reference_designator"], self["data_source"])


class Issues:
    """
    Collects errors (must-fix) and warnings (worth a look) for one run.

    Attributes
    ----------
    errors : list of str
        Problems serious enough to fail validation (e.g. a malformed
        reference_designator, a wrong data folder).
    warnings : list of str
        Problems worth a human's attention but not fatal (e.g. an
        unrecognized but plausible status value).

    Examples
    --------
    >>> issues = Issues()
    >>> issues.warn("looks a little odd")
    >>> issues.ok
    True
    >>> issues.error("this is broken")
    >>> issues.ok
    False
    """

    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        """
        Record an error-level issue.

        Parameters
        ----------
        msg : str
            Human-readable description of the problem, typically already
            prefixed with a ``"[path:lineno]"`` location tag.

        Returns
        -------
        None
        """
        self.errors.append(msg)

    def warn(self, msg):
        """
        Record a warning-level issue.

        Parameters
        ----------
        msg : str
            Human-readable description of the problem, typically already
            prefixed with a ``"[path:lineno]"`` location tag.

        Returns
        -------
        None
        """
        self.warnings.append(msg)

    @property
    def ok(self):
        """
        bool : Whether this run is free of error-level issues.

        ``True`` even if there are warnings — only :attr:`errors` affects
        this flag.
        """
        return not self.errors


def parse_ingest_filename(path):
    """
    Parse the site and data folder out of a standard ingest CSV filename.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to an ingest CSV, expected to be named like
        ``'<SITE>_<Rxxxxx>_ingest.csv'`` (e.g. ``CP10CNSM_R00003_ingest.csv``)
        for fixed assets, or ``'<SITE>-<PLATFORM>_<Rxxxxx>_ingest.csv'``
        (e.g. ``GP05MOAS-PG380_R00001_ingest.csv``) for mobile assets
        (gliders/profilers), whose "site" is really
        ``<array><MOAS-class>-<platform ID>`` since all of them share the
        same ``05MOAS`` array-and-class code. Only the filename component
        is inspected; any directory part of `path` is ignored.

    Returns
    -------
    site : str or None
        Upper-cased site code, including any hyphenated platform suffix
        for mobile assets (e.g. ``"CP10CNSM"`` or ``"GP05MOAS-PG380"``),
        or ``None`` if the filename doesn't follow the expected convention.
    folder : str or None
        Upper-cased data folder token (e.g. ``"R00003"``), or ``None`` if
        the filename doesn't follow the expected convention.

    Examples
    --------
    >>> parse_ingest_filename("CP10CNSM_R00003_ingest.csv")
    ('CP10CNSM', 'R00003')
    >>> parse_ingest_filename("GP05MOAS-PG380_R00001_ingest.csv")
    ('GP05MOAS-PG380', 'R00001')
    >>> parse_ingest_filename("not_a_match.csv")
    (None, None)
    """
    m = FILENAME_RE.match(Path(path).name)
    if not m:
        return None, None
    return m.group(1).upper(), m.group(2).upper()


def load_csv(path):
    """
    Parse an ingest CSV into a header and a list of rows.

    Blank lines are silently skipped. Rows with too few or too many
    fields are padded/kept as-is (with the discrepancy recorded on the
    resulting :class:`IngestRow` via ``n_fields_in_source``) rather than
    raising, so that :func:`validate_single_file` can report the problem
    in context.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the ingest CSV to read.

    Returns
    -------
    header : list of str or None
        The raw header row, or ``None`` if the file is empty.
    rows : list of IngestRow
        One entry per non-blank data row, in file order.

    See Also
    --------
    IngestRow : The per-row container returned in `rows`.
    check_header : Validates `header` against the expected columns.
    """
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return None, []

        rows = []
        for lineno, raw in enumerate(reader, start=2):  # header occupies line 1
            if not raw or all(not cell.strip() for cell in raw):
                continue  # skip blank lines
            padded = raw + [""] * (len(EXPECTED_COLUMNS) - len(raw))
            data = dict(zip(EXPECTED_COLUMNS, padded))
            rows.append(IngestRow(lineno, data, n_fields_in_source=len(raw)))
        return header, rows


def check_header(path, header, issues):
    """
    Validate that a CSV's header matches the expected ingest columns.

    Parameters
    ----------
    path : str
        Path of the file being checked, used only for error messages.
    header : list of str or None
        The header row as returned by :func:`load_csv`. ``None`` is
        treated as "file is empty".
    issues : Issues
        Collector that any problems found are recorded into, in place.

    Returns
    -------
    None
        Problems are reported via `issues`, not the return value.
    """
    if header is None:
        issues.error(f"[{path}] file is empty — no header row found.")
        return
    cleaned = [h.strip() for h in header]
    if cleaned != EXPECTED_COLUMNS:
        issues.error(
            f"[{path}] header does not match the expected columns.\n"
            f"    expected: {EXPECTED_COLUMNS}\n"
            f"    found:    {cleaned}"
        )


def validate_single_file(path, rows, expected_folder, issues):
    """
    Run all checks that only require looking at one file at a time.

    For every row, this checks: the field count matches the header,
    the (parser, reference_designator, data_source) key is unique within
    the file, `reference_designator` matches the standard OOI format,
    `data_source` and `status` are recognized values, and every
    `filename_mask` references `expected_folder` (and only that folder).

    Parameters
    ----------
    path : str
        Path of the file being checked, used only for error messages.
    rows : list of IngestRow
        Rows to validate, as returned by :func:`load_csv`.
    expected_folder : str or None
        Data folder token (e.g. ``"R00003"``) that every `filename_mask`
        in this file should reference. If ``None``, the folder-consistency
        checks are skipped (the caller is expected to have already warned
        about this).
    issues : Issues
        Collector that any problems found are recorded into, in place.

    Returns
    -------
    None
        Problems are reported via `issues`, not the return value.
    """
    seen = {}
    for r in rows:
        loc = f"{path}:{r.lineno}"

        if r.n_fields_in_source != len(EXPECTED_COLUMNS):
            issues.error(
                f"[{loc}] row has {r.n_fields_in_source} fields, expected "
                f"{len(EXPECTED_COLUMNS)} (check for a stray/missing comma)."
            )

        if r.key in seen:
            issues.error(
                f"[{loc}] duplicate row — same parser/reference_designator/data_source "
                f"as line {seen[r.key]}: {r.key}"
            )
        else:
            seen[r.key] = r.lineno

        refdes = r["reference_designator"]
        if not REFDES_RE.match(refdes):
            issues.error(
                f"[{loc}] reference_designator '{refdes}' doesn't match the expected "
                f"OOI format (e.g. CP10CNSM-MFC31-00-CPMENG000)."
            )

        if r["data_source"] not in VALID_DATA_SOURCES:
            issues.warn(f"[{loc}] unrecognized data_source '{r['data_source']}'.")

        if r["status"] not in VALID_STATUSES:
            issues.warn(f"[{loc}] unrecognized status '{r['status']}'.")

        mask = r["filename_mask"]
        if mask:
            folders_found = set(FOLDER_RE.findall(mask))
            if expected_folder and expected_folder not in folders_found:
                issues.error(
                    f"[{loc}] filename_mask does not reference the expected data "
                    f"folder '{expected_folder}': {mask}"
                )
            if len(folders_found) > 1:
                issues.warn(
                    f"[{loc}] filename_mask references more than one data folder "
                    f"{sorted(folders_found)}: {mask}"
                )
        elif not r["parser"].startswith("#"):
            issues.warn(f"[{loc}] filename_mask is empty.")


def normalize_mask(mask, folder):
    """
    Blank out the data-folder token in a filename_mask.

    This lets two versions of the same stream (differing only by the
    expected R##### folder bump) compare as equal.

    Parameters
    ----------
    mask : str
        A `filename_mask` value, e.g.
        ``"/omc_data/whoi/OMC/CP10CNSM/R00003/cg_data/cpm3/syslog/cpm_status*.txt"``.
    folder : str or None
        The data folder token to blank out (e.g. ``"R00003"``). If
        ``None``, `mask` is returned unchanged.

    Returns
    -------
    str
        `mask` with every occurrence of `folder` replaced by the literal
        placeholder ``"<FOLDER>"``.

    Examples
    --------
    >>> normalize_mask("/a/R00003/b/*.log", "R00003")
    '/a/<FOLDER>/b/*.log'
    """
    if folder:
        return mask.replace(folder, "<FOLDER>")
    return mask


class DiffResult:
    """
    Container for the outcome of :func:`compare_files`.

    Instances are built up by :func:`compare_files` and consumed by
    :func:`print_diff_report`; there is no constructor logic beyond the
    attributes documented below, which are set directly on the instance.

    Attributes
    ----------
    n_common : int
        Number of rows present (by key) in both files.
    n_clean : int
        Number of common rows that are identical apart from the expected
        data-folder swap — i.e. rows needing no attention.
    field_changes : list of tuple
        Each element is ``(old_row, new_row, diffs)`` where `diffs` is a
        list of ``(field_name, old_value, new_value)`` for the
        ``status``/``notes`` fields that changed.
    path_changes : list of tuple
        Each element is ``(old_row, new_row)`` for rows whose
        `filename_mask` changed in some way other than the folder number.
    likely_modified : list of tuple
        Each element is ``(old_row, new_row)`` for a removed/added pair
        that shares `reference_designator` and `data_source` but has a
        different `parser` — probably a renamed/retired driver rather
        than an unrelated add and remove.
    pure_removed : list of IngestRow
        Rows present only in the old file (and not claimed by
        `likely_modified`).
    pure_added : list of IngestRow
        Rows present only in the new file (and not claimed by
        `likely_modified`).
    """

    pass


def compare_files(old_rows, old_folder, new_rows, new_folder):
    """
    Diff two ingest CSVs' rows, treating the data-folder bump as a non-change.

    Rows are matched between the two files by :attr:`IngestRow.key`
    (``parser``, ``reference_designator``, ``data_source``). Matched rows
    are further compared for ``status``/``notes`` changes and for
    `filename_mask` changes beyond the expected folder swap. Unmatched
    rows are checked against each other via :attr:`IngestRow.loose_key`
    to spot likely renames before being reported as pure adds/removes.

    Parameters
    ----------
    old_rows : list of IngestRow
        Rows from the earlier ingest CSV.
    old_folder : str or None
        Data folder token for `old_rows` (e.g. ``"R00002"``), used to
        normalize `filename_mask` for comparison.
    new_rows : list of IngestRow
        Rows from the newer ingest CSV.
    new_folder : str or None
        Data folder token for `new_rows` (e.g. ``"R00003"``), used to
        normalize `filename_mask` for comparison.

    Returns
    -------
    DiffResult
        Structured summary of everything that changed (or didn't) between
        `old_rows` and `new_rows`.

    See Also
    --------
    normalize_mask : Used internally to ignore the folder-number swap.
    print_diff_report : Renders a `DiffResult` as a human-readable report.
    """
    old_by_key = OrderedDict((r.key, r) for r in old_rows)
    new_by_key = OrderedDict((r.key, r) for r in new_rows)

    old_keys, new_keys = set(old_by_key), set(new_by_key)
    common = old_keys & new_keys
    removed = old_keys - new_keys
    added = new_keys - old_keys

    # Pair up removed/added rows that share reference_designator + data_source,
    # i.e. probably the same logical stream but the parser/driver name changed.
    removed_by_loose = defaultdict(list)
    for k in removed:
        removed_by_loose[old_by_key[k].loose_key].append(k)
    added_by_loose = defaultdict(list)
    for k in added:
        added_by_loose[new_by_key[k].loose_key].append(k)

    pure_removed, pure_added = set(removed), set(added)
    likely_modified = []
    for loose_key in set(removed_by_loose) & set(added_by_loose):
        for ok in removed_by_loose[loose_key]:
            for nk in added_by_loose[loose_key]:
                if ok in pure_removed and nk in pure_added:
                    likely_modified.append((old_by_key[ok], new_by_key[nk]))
                    pure_removed.discard(ok)
                    pure_added.discard(nk)
                    break

    field_changes = []   # rows matched by key, but status/notes differ
    path_changes = []    # rows matched by key, but filename_mask differs beyond the folder
    n_clean = 0

    for k in sorted(common):
        old_r, new_r = old_by_key[k], new_by_key[k]

        diffs = [
            (field, old_r[field], new_r[field])
            for field in ("status", "notes")
            if old_r[field] != new_r[field]
        ]
        if diffs:
            field_changes.append((old_r, new_r, diffs))

        old_norm = normalize_mask(old_r["filename_mask"], old_folder)
        new_norm = normalize_mask(new_r["filename_mask"], new_folder)
        if old_norm != new_norm:
            path_changes.append((old_r, new_r))

        if not diffs and old_norm == new_norm:
            n_clean += 1

    result = DiffResult()
    result.n_common = len(common)
    result.n_clean = n_clean
    result.field_changes = field_changes
    result.path_changes = path_changes
    result.likely_modified = likely_modified
    result.pure_removed = [old_by_key[k] for k in sorted(pure_removed)]
    result.pure_added = [new_by_key[k] for k in sorted(pure_added)]
    return result


def fmt_row(r):
    """
    Format an :class:`IngestRow` for display in a report line.

    Parameters
    ----------
    r : IngestRow
        Row to format.

    Returns
    -------
    str
        A one-line human-readable summary, e.g.
        ``"CP10CNSM-MFC31-00-CPMENG000 / recovered_host  (parser: ...)"``.
    """
    return f"{r['reference_designator']} / {r['data_source']}  (parser: {r['parser']})"


def hr(char="-", width=72):
    """
    Build a horizontal rule for console output.

    Parameters
    ----------
    char : str, default '-'
        Character to repeat.
    width : int, default 72
        Number of characters in the returned rule.

    Returns
    -------
    str
        `char` repeated `width` times.
    """
    return char * width


def print_single_file_report(path, issues):
    """
    Print a human-readable validation report for one file.

    Parameters
    ----------
    path : str
        Path of the file that was validated, used in the report header.
    issues : Issues
        Errors and warnings collected by :func:`validate_single_file` and
        :func:`check_header` for this file.

    Returns
    -------
    None
        Writes directly to stdout.
    """
    print(hr("="))
    print(f"Validating: {path}")
    print(hr("="))
    if not issues.errors and not issues.warnings:
        print("  No issues found.")
    for e in issues.errors:
        print(f"  ERROR: {e}")
    for w in issues.warnings:
        print(f"  WARN:  {w}")
    print()


def print_diff_report(old_path, new_path, old_folder, new_folder, result):
    """
    Print a human-readable diff report comparing two ingest CSVs.

    Parameters
    ----------
    old_path : str
        Path of the older file, used in the report header.
    new_path : str
        Path of the newer file, used in the report header.
    old_folder : str or None
        Data folder token for the older file (display only).
    new_folder : str or None
        Data folder token for the newer file (display only).
    result : DiffResult
        Diff output from :func:`compare_files` to render.

    Returns
    -------
    None
        Writes directly to stdout.
    """
    print(hr("="))
    print(f"Comparing:\n  old: {old_path}  (folder: {old_folder or 'unknown'})\n"
          f"  new: {new_path}  (folder: {new_folder or 'unknown'})")
    print(hr("="))

    print(f"  {result.n_clean} row(s) match exactly (aside from the data-folder number). Good.")

    if result.field_changes:
        print(f"\n  {len(result.field_changes)} row(s) changed status/notes:")
        for old_r, new_r, diffs in result.field_changes:
            print(f"    - {fmt_row(new_r)}")
            for field, old_v, new_v in diffs:
                print(f"        {field}: {old_v!r} -> {new_v!r}")

    if result.path_changes:
        print(f"\n  {len(result.path_changes)} row(s) have a filename_mask change beyond "
              f"just the folder number (double-check these):")
        for old_r, new_r in result.path_changes:
            print(f"    - {fmt_row(new_r)}")
            print(f"        old: {old_r['filename_mask']}")
            print(f"        new: {new_r['filename_mask']}")

    if result.likely_modified:
        print(f"\n  {len(result.likely_modified)} row(s) look like the same stream with a "
              f"changed parser (verify this was intentional):")
        for old_r, new_r in result.likely_modified:
            print(f"    - {old_r['reference_designator']} / {old_r['data_source']}")
            print(f"        old parser: {old_r['parser']}")
            print(f"        new parser: {new_r['parser']}")

    if result.pure_removed:
        print(f"\n  {len(result.pure_removed)} row(s) present in the OLD file but missing "
              f"from the NEW file:")
        for r in result.pure_removed:
            print(f"    - {fmt_row(r)}  [old line {r.lineno}]")

    if result.pure_added:
        print(f"\n  {len(result.pure_added)} row(s) are new in the NEW file:")
        for r in result.pure_added:
            print(f"    - {fmt_row(r)}  [new line {r.lineno}]")

    if not (result.field_changes or result.path_changes or result.likely_modified
            or result.pure_removed or result.pure_added):
        print("\n  No differences found beyond the data-folder number.")
    print()


def run_single(path, issues_out):
    """
    Load, validate, and report on one ingest CSV.

    Parameters
    ----------
    path : str
        Path to the ingest CSV to process.
    issues_out : list of Issues
        List that the :class:`Issues` collector for this file is appended
        to, in place, so the caller can tally errors/warnings across
        multiple files.

    Returns
    -------
    header : list of str or None
        The file's header row, as returned by :func:`load_csv`.
    rows : list of IngestRow
        The file's data rows, as returned by :func:`load_csv`.
    site : str or None
        Site code parsed from the filename, as returned by
        :func:`parse_ingest_filename`.
    folder : str or None
        Data folder token parsed from the filename, as returned by
        :func:`parse_ingest_filename`.
    """
    issues = Issues()
    header, rows = load_csv(path)
    check_header(path, header, issues)
    site, folder = parse_ingest_filename(path)
    if folder is None:
        issues.warn(
            f"[{path}] filename doesn't match the expected "
            f"'<SITE>_R#####_ingest.csv' pattern — skipping folder-consistency checks."
        )
    if header is not None:
        validate_single_file(path, rows, folder, issues)
    print_single_file_report(path, issues)
    issues_out.append(issues)
    return header, rows, site, folder


def main():
    """
    Command-line entry point.

    Parses ``sys.argv`` for one or two ingest CSV paths, runs
    single-file validation on each (via :func:`run_single`), runs
    :func:`compare_files` / :func:`print_diff_report` when two files are
    given, prints a final summary, and exits with status 1 if any
    error-level issues were found (0 otherwise).

    Returns
    -------
    None
        Terminates the process via :func:`sys.exit` rather than
        returning.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_files", nargs="+", help="One CSV to validate, or two ('old' then 'new') to also diff.")
    args = ap.parse_args()

    if len(args.csv_files) not in (1, 2):
        ap.error("Provide either one CSV (validate only) or two CSVs (old, new — validate + diff).")

    all_issues = []
    parsed = [run_single(p, all_issues) for p in args.csv_files]

    if len(args.csv_files) == 2:
        (old_path, new_path) = args.csv_files
        (_, old_rows, old_site, old_folder), (_, new_rows, new_site, new_folder) = parsed

        if old_site and new_site and old_site != new_site:
            print(f"WARN: the two files appear to be for different sites "
                  f"({old_site} vs {new_site}) — comparison may not be meaningful.\n")
        if old_folder and new_folder and old_folder == new_folder:
            print(f"WARN: both files reference the same data folder ({old_folder}) — "
                  f"expected them to differ.\n")

        result = compare_files(old_rows, old_folder, new_rows, new_folder)
        print_diff_report(old_path, new_path, old_folder, new_folder, result)

    n_errors = sum(len(i.errors) for i in all_issues)
    n_warnings = sum(len(i.warnings) for i in all_issues)
    print(hr("="))
    print(f"SUMMARY: {n_errors} error(s), {n_warnings} warning(s).")
    print(hr("="))

    sys.exit(1 if n_errors else 0)


if __name__ == "__main__":
    main()
