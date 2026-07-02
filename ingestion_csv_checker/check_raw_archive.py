#!/usr/bin/env python3
"""
Confirm that files matching each ingest CSV's filename_mask actually
exist (and aren't zero-byte) in OOI's raw data archive at
https://rawdata.oceanobservatories.org/files/.

This does NOT download or parse the data files themselves — it only
walks the archive's directory listings and checks reported file sizes
(falling back to a HEAD request only when a listing doesn't show a size).

IMPORTANT: rawdata.oceanobservatories.org's robots.txt disallows
automated crawling. OOI's own documentation tells users to override this
for legitimate archive access (e.g. `wget -r -np -e robots=off ...`) —
see https://oceanobservatories.org/knowledgebase/how-do-i-download-an-entire-raw-data-directory/
This script does the equivalent via `requests`, which (like wget with
that flag) does not consult robots.txt on its own. Please don't hammer
the archive — the script caches each directory listing so it's fetched
only once even if many CSV rows share a folder.

Usage
-----
python3 check_raw_archive.py INGEST.csv
python3 check_raw_archive.py INGEST.csv --base-url https://rawdata.oceanobservatories.org/files
python3 check_raw_archive.py INGEST.csv --include-commented --timeout 20

Exit status is non-zero if any row with status "Available" is missing
files or has only zero-byte files.
"""

import argparse
import fnmatch
import re
import sys
import time
from pathlib import Path

import requests

from ooi_ingest_check import load_csv, check_header, parse_ingest_filename, Issues

MASK_PREFIX = "/omc_data/whoi/OMC/"
DEFAULT_BASE_URL = "https://rawdata.oceanobservatories.org/files"
USER_AGENT = ("ooi-ingest-csv-checker/1.0 (archive presence check; see script "
              "header)")

ANCHOR_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                       re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
TRAILER_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2})\s*([\d.]+[KMGTkmgt]?|-)?"
)
SIZE_RE = re.compile(r"^([\d.]+)\s*([KMGT]?)$", re.IGNORECASE)
SIZE_MULT = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

SKIP_LINK_TEXT = {"parent directory", "name", "last modified", "size",
                  "description"}


def parse_size(size_str):
    """
    Convert an Apache-style directory-listing size string to bytes.

    Parameters
    ----------
    size_str : str or None
        Size token as shown in a directory listing, e.g. ``"4.5K"``,
        ``"323"``, ``"-"`` (used by Apache for directories), or ``None``
        if no size token was found at all.

    Returns
    -------
    int or None
        Size in bytes, or ``None`` if `size_str` is ``None``, empty,
        ``"-"``, or doesn't match a recognized ``<number><suffix>``
        pattern (`suffix` being one of ``K``/``M``/``G``/``T`` or empty
        for plain bytes).

    Examples
    --------
    >>> parse_size("4.5K")
    4608
    >>> parse_size("0")
    0
    >>> parse_size("-")
    >>> parse_size(None)
    """
    if size_str is None:
        return None
    size_str = size_str.strip()
    if size_str in ("", "-"):
        return None
    m = SIZE_RE.match(size_str)
    if not m:
        return None
    num, suffix = m.groups()
    try:
        return int(float(num) * SIZE_MULT[suffix.upper()])
    except (ValueError, KeyError):
        return None


def parse_directory_listing(html_text):
    """
    Parse an Apache-style autoindex page into a list of entries.

    Handles both the classic ``<pre>``-based "FancyIndexing" layout and
    ``<table>``-based layouts, since both simply place a modification
    date and a size token as plain text somewhere after each ``<a>``
    tag. "Parent Directory" links, sort-order links (``href`` starting
    with ``?``), and column-header links are skipped.

    Parameters
    ----------
    html_text : str
        Raw HTML of a directory listing page, as returned in
        ``response.text`` from a GET request to a directory URL.

    Returns
    -------
    list of dict
        One dict per listed entry (file or subdirectory), each with
        keys:

        - ``name`` : str — the entry's filename or directory name
          (without any leading path or trailing slash).
        - ``is_dir`` : bool — whether the entry's ``href`` ended in
          ``"/"``.
        - ``size_bytes`` : int or None — parsed via :func:`parse_size`;
          ``None`` for directories or when no size could be determined.

    See Also
    --------
    parse_size : Used to convert the raw size text for each entry.
    """
    anchors = list(ANCHOR_RE.finditer(html_text))
    entries = []
    for i, m in enumerate(anchors):
        href = m.group(1)
        link_text = re.sub(TAG_RE, "", m.group(2)).strip()

        if href.startswith("?") or href.startswith("#"):
            continue
        if link_text.lower() in SKIP_LINK_TEXT:
            continue
        if href.startswith("/") and href.rstrip("/").split("/")[-1] == "":
            continue

        end = anchors[i + 1].start() if i + 1 < len(anchors) else min(len(html_text), m.end() + 300)
        trailer = re.sub(TAG_RE, " ", html_text[m.end():end])
        tm = TRAILER_RE.search(trailer)
        size_str = tm.group(2) if tm else None

        name = href.rstrip("/").rsplit("/", 1)[-1]
        if not name:
            continue
        entries.append({
            "name": name,
            "is_dir": href.endswith("/"),
            "size_bytes": parse_size(size_str),
        })
    return entries


def has_wildcard(segment):
    """
    Check whether a path segment contains shell-glob wildcard characters.

    Parameters
    ----------
    segment : str
        A single path component, e.g. ``"PHSEN_*"`` or ``"dcl36"``.

    Returns
    -------
    bool
        ``True`` if `segment` contains any of ``*``, ``?``, or ``[``.

    Examples
    --------
    >>> has_wildcard("PHSEN_*")
    True
    >>> has_wildcard("dcl36")
    False
    """
    return any(c in segment for c in "*?[")


class ArchiveWalker:
    """
    Resolves glob-style archive paths by walking directory listings over HTTP.

    Each unique directory URL is fetched (and parsed via
    :func:`parse_directory_listing`) at most once per instance; the
    result is cached in :attr:`listing_cache` so that many
    `filename_mask` rows sharing a folder only cost one request.

    Parameters
    ----------
    session : requests.Session
        Session used for all GET/HEAD requests. Callers are expected to
        have already set any desired headers (e.g. ``User-Agent``) on it.
    timeout : float, default 15
        Per-request timeout, in seconds, passed straight through to
        `requests`.
    delay : float, default 0.0
        Seconds to sleep before each *new* directory listing fetch (i.e.
        not before cache hits), as a courtesy to the archive server.

    Attributes
    ----------
    session : requests.Session
        See parameters.
    timeout : float
        See parameters.
    delay : float
        See parameters.
    listing_cache : dict of {str : tuple}
        Maps a directory URL to ``(entries, error)`` as returned by
        :meth:`get_listing`.
    fetch_count : int
        Number of directory listings actually fetched over the network
        (i.e. excluding cache hits). Useful for reporting/debugging.
    """

    def __init__(self, session, timeout=15, delay=0.0):
        self.session = session
        self.timeout = timeout
        self.delay = delay
        self.listing_cache = {}   # url->(entries / None, error message / None)
        self.fetch_count = 0

    def get_listing(self, url):
        """
        Fetch and parse a directory listing, using the instance cache.

        Parameters
        ----------
        url : str
            Directory URL to list, e.g.
            ``"https://rawdata.oceanobservatories.org/files/CP10CNSM/R00003/cg_data/cpm3/syslog/"``.
            Should end in ``"/"``.

        Returns
        -------
        entries : list of dict or None
            Entries as returned by :func:`parse_directory_listing`, or
            ``None`` if the request failed or didn't return HTTP 200.
        error : str or None
            ``None`` on success, otherwise a short human-readable
            description of what went wrong (e.g. ``"HTTP 404"`` or
          ``"request failed: <exception message>"``).
        """
        if url in self.listing_cache:
            return self.listing_cache[url]
        if self.delay:
            time.sleep(self.delay)
        self.fetch_count += 1
        try:
            resp = self.session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            result = (None, f"request failed: {e}")
            self.listing_cache[url] = result
            return result
        if resp.status_code != 200:
            result = (None, f"HTTP {resp.status_code}")
            self.listing_cache[url] = result
            return result
        entries = parse_directory_listing(resp.text)
        result = (entries, None)
        self.listing_cache[url] = result
        return result

    def head_size(self, url):
        """
        Fetch a file's size via an HTTP HEAD request.

        Used as a fallback when a directory listing doesn't show a size
        for a matched file (e.g. some listing layouts omit it).

        Parameters
        ----------
        url : str
            Direct URL of the file to check.

        Returns
        -------
        int or None
            The value of the response's ``Content-Length`` header as an
            integer, or ``None`` if the request failed, didn't return
            HTTP 200, or lacked that header.
        """
        try:
            resp = self.session.head(url,
                                     timeout=self.timeout,
                                     allow_redirects=True)
            if resp.status_code == 200 and "Content-Length" in resp.headers:
                return int(resp.headers["Content-Length"])
        except (requests.exceptions.RequestException, ValueError):
            pass
        return None

    def resolve(self, base_url, segments):
        """
        Resolve a (possibly multi-level) glob path against the archive.

        Each path segment may itself be a wildcard (e.g. a `filename_mask`
        like ``.../PHSEN_*/SAMI*V.txt`` has wildcards in two segments);
        this walks the archive one directory at a time, only fetching a
        listing when a segment actually needs to be matched against
        real entries, and fanning out across every matching subdirectory
        when a non-final segment is itself a glob.

        Parameters
        ----------
        base_url : str
            Archive root URL, e.g.
            ``"https://rawdata.oceanobservatories.org/files"``.
        segments : list of str
            Path components after `base_url`, e.g.
            ``["CP10CNSM", "R00003", "instruments", "dcl36", "PHSEN_*",
               "SAMI*V.txt"]``.

        Returns
        -------
        matches : list of dict
            One dict per matched file, each with keys ``"url"`` (str,
            full file URL), ``"name"`` (str), and ``"size_bytes"``
            (int or None, from the listing).
        errors : list of str
            One entry per directory along the way that couldn't be
            listed, formatted as ``"<url> -> <reason>"``.
        """
        return self._walk(base_url.rstrip("/") + "/", segments)

    def _walk(self, current_url, segments):
        """
        Recursive helper for :meth:`resolve`.

        Parameters
        ----------
        current_url : str
            Directory URL reached so far (ends in ``"/"``).
        segments : list of str
            Remaining path components still to resolve.

        Returns
        -------
        matches : list of dict
            See :meth:`resolve`.
        errors : list of str
            See :meth:`resolve`.
        """
        seg = segments[0]
        rest = segments[1:]

        if rest and not has_wildcard(seg):
            # literal path component -- descend without needing a listing
            return self._walk(current_url + seg + "/", rest)

        entries, err = self.get_listing(current_url)
        if err is not None:
            return [], [f"{current_url} -> {err}"]

        if rest:
            matches, errors = [], []
            subdirs = [e for e in entries if e["is_dir"] and fnmatch.fnmatchcase(e["name"], seg)]
            for e in subdirs:
                sub_matches, sub_errors = self._walk(current_url + e["name"] +
                                                     "/", rest)
                matches.extend(sub_matches)
                errors.extend(sub_errors)
            return matches, errors
        else:
            matches = [
                {"url": current_url + e["name"], "name": e["name"],
                 "size_bytes": e["size_bytes"]}
                for e in entries if not e["is_dir"] and fnmatch.fnmatchcase(
                    e["name"], seg)
            ]
            return matches, []


def mask_to_segments(mask):
    """
    Convert a filename_mask into path segments relative to the archive root.

    Parameters
    ----------
    mask : str
        A `filename_mask` value from an ingest CSV, expected to start
        with :data:`MASK_PREFIX` (``"/omc_data/whoi/OMC/"``), e.g.
        ``"/omc_data/whoi/OMC/CP10CNSM/R00003/cg_data/cpm3/syslog/cpm_status*.txt"``.

    Returns
    -------
    list of str or None
        Non-empty path components after the prefix, e.g.
        ``["CP10CNSM", "R00003", "cg_data", "cpm3", "syslog",
           "cpm_status*.txt"]``,
        or ``None`` if `mask` doesn't start with :data:`MASK_PREFIX`.

    Examples
    --------
    >>> mask_to_segments("/omc_data/whoi/OMC/CP10CNSM/R00003/a/*.log")
    ['CP10CNSM', 'R00003', 'a', '*.log']
    >>> mask_to_segments("/something/else") is None
    True
    """
    if not mask.startswith(MASK_PREFIX):
        return None
    remainder = mask[len(MASK_PREFIX):]
    return [s for s in remainder.split("/") if s]


def classify_row(row, matches, errors, walker, verify_nonzero_via_head):
    """
    Decide the severity and message for one row's archive-check outcome.

    Missing/empty files are reported as errors for rows whose `status`
    is ``"Available"`` (data is claimed to exist), but downgraded to a
    warning or info note for rows marked ``"Expected"`` or
    ``"Not Available"``, since absence is the expected state there. The
    reverse mismatch (files exist for a row not marked ``"Available"``)
    is reported as an informational note.

    Parameters
    ----------
    row : IngestRow
        The ingest CSV row being classified.
    matches : list of dict
        Matched files for this row's `filename_mask`, as returned by
        :meth:`ArchiveWalker.resolve`.
    errors : list of str
        Directory-listing errors for this row's `filename_mask`, as
        returned by :meth:`ArchiveWalker.resolve`.
    walker : ArchiveWalker
        Used to issue a HEAD-request size fallback (via
        :meth:`ArchiveWalker.head_size`) for matches whose listing entry
        didn't include a size, when `verify_nonzero_via_head` is True.
    verify_nonzero_via_head : bool
        Whether to fall back to a HEAD request for matches with unknown
        size (``size_bytes is None``).

    Returns
    -------
    severity : {'ok', 'info', 'warn', 'error'}
        Outcome category for this row.
    message : str
        Human-readable explanation to display alongside the severity.
    """
    status = row["status"]
    is_expected_missing = status in ("Expected", "Not Available")

    if errors:
        sev = "warn" if is_expected_missing else "error"
        return sev, (f"could not list one or more directories: "
                     f"{'; '.join(errors)}")

    if not matches:
        sev = "info" if is_expected_missing else "error"
        return sev, "no files in the archive match this filename_mask"

    zero_byte = []
    unknown = []
    for m in matches:
        size = m["size_bytes"]
        if size is None and verify_nonzero_via_head:
            size = walker.head_size(m["url"])
        if size is None:
            unknown.append(m["name"])
        elif size == 0:
            zero_byte.append(m["name"])

    if zero_byte:
        sev = "warn" if is_expected_missing else "error"
        shown = ", ".join(zero_byte[:5]) + (f", +{len(zero_byte) - 5} more" if len(zero_byte) > 5 else "")
        return sev, f"{len(zero_byte)} matching file(s) are zero-byte: {shown}"

    if unknown and not (len(unknown) < len(matches)):
        # couldn't determine size for *any* matched file
        return "warn", f"found {len(matches)} matching file(s) but couldn't determine size for any of them"

    if is_expected_missing:
        return "info", f"status is '{status}' but {len(matches)} matching file(s) already exist in the archive"

    return "ok", f"{len(matches)} matching file(s) found, all non-empty" if len(matches) > 1 \
        else "1 matching file found, non-empty"


def check_archive(path, rows, base_url, timeout, include_commented, verify_nonzero_via_head, delay):
    """
    Check every row's filename_mask against the raw data archive and print a report.

    Parameters
    ----------
    path : str
        Path of the ingest CSV being checked, used in the report header
        and in each row's location tag.
    rows : list of IngestRow
        Rows to check, as returned by :func:`ooi_ingest_check.load_csv`.
    base_url : str
        Archive base URL, e.g.
        ``"https://rawdata.oceanobservatories.org/files"``.
    timeout : float
        Per-request timeout, in seconds, passed to :class:`ArchiveWalker`.
    include_commented : bool
        If ``False`` (the default from the CLI), rows whose `parser`
        starts with ``"#"`` are skipped entirely rather than checked.
    verify_nonzero_via_head : bool
        Passed through to :func:`classify_row` for each row; whether to
        fall back to a HEAD request when a listing doesn't show a
        matched file's size.
    delay : float
        Seconds to sleep before each new directory listing fetch,
        passed to :class:`ArchiveWalker`.

    Returns
    -------
    int
        Number of rows classified as ``"error"`` severity. A non-zero
        return indicates the archive is missing data that the CSV
        claims is ``Available``.
    """
    walker = ArchiveWalker(requests.Session(), timeout=timeout, delay=delay)
    walker.session.headers.update({"User-Agent": USER_AGENT})

    print("=" * 72)
    print(f"Checking raw data archive for: {path}")
    print(f"  base URL: {base_url}")
    print("=" * 72)

    n_ok = n_error = n_warn = n_info = n_skipped = 0

    for r in rows:
        loc = f"{path}:{r.lineno}"
        if r["parser"].startswith("#") and not include_commented:
            n_skipped += 1
            continue

        mask = r["filename_mask"]
        segments = mask_to_segments(mask)
        if segments is None:
            print(f"  WARN  [{loc}] filename_mask doesn't start with {MASK_PREFIX!r}, "
                  f"can't map to archive URL: {mask}")
            n_warn += 1
            continue

        matches, errors = walker.resolve(base_url, segments)
        sev, msg = classify_row(r, matches, errors, walker, verify_nonzero_via_head)

        label = {"ok": "OK   ", "error": "ERROR", "warn": "WARN ", "info": "INFO "}[sev]
        print(f"  {label} [{loc}] {r['reference_designator']} / {r['data_source']} "
              f"(status={r['status']!r}): {msg}")

        if sev == "ok":
            n_ok += 1
        elif sev == "error":
            n_error += 1
        elif sev == "warn":
            n_warn += 1
        else:
            n_info += 1

    print()
    print(f"  Directory listings fetched: {walker.fetch_count}")
    print(f"  {n_ok} ok, {n_error} error(s), {n_warn} warning(s), {n_info} info, "
          f"{n_skipped} skipped (commented-out rows).")
    print("=" * 72)
    return n_error


def main():
    """
    Command-line entry point.

    Parses ``sys.argv`` for a single ingest CSV path and archive-check
    options, validates the CSV's header (bailing out early if it's
    malformed), runs :func:`check_archive`, and exits with status 1 if
    any row was classified as an error (0 otherwise; 2 if the CSV itself
    couldn't be read).

    Returns
    -------
    None
        Terminates the process via :func:`sys.exit` rather than
        returning.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_file", help="Ingest CSV to check against the raw data archive.")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                     help=f"Archive base URL (default: {DEFAULT_BASE_URL})")
    ap.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds.")
    ap.add_argument("--delay", type=float, default=0.0,
                     help="Seconds to sleep before each new directory listing fetch (be polite to the archive).")
    ap.add_argument("--include-commented", action="store_true",
                     help="Also check rows whose parser starts with '#' (default: skipped).")
    ap.add_argument("--no-head-fallback", action="store_true",
                     help="Don't issue a HEAD request when a listing doesn't show a file's size "
                          "(faster, but such files are reported as 'unknown size' instead of verified).")
    args = ap.parse_args()

    issues = Issues()
    header, rows = load_csv(args.csv_file)
    check_header(args.csv_file, header, issues)
    if not issues.ok:
        for e in issues.errors:
            print(f"ERROR: {e}")
        sys.exit(2)

    n_errors = check_archive(
        args.csv_file, rows, args.base_url, args.timeout,
        args.include_commented, not args.no_head_fallback, args.delay,
    )
    sys.exit(1 if n_errors else 0)


if __name__ == "__main__":
    main()
