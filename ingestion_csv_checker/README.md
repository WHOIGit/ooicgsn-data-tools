# OOI Ingest CSV Checker

Two small command-line tools for sanity-checking OOI ingestion CSVs before
they go live:

1. **`ooi_ingest_check.py`** — validates one ingest CSV, and optionally
   diffs it against a previous version (e.g. `R00002` → `R00003`).
2. **`check_raw_archive.py`** — confirms that files matching each row's
   `filename_mask` actually exist (and aren't zero-byte) in OOI's raw
   data archive.

Both expect the standard ingest CSV columns:

```
parser, filename_mask, reference_designator, data_source, status, notes
```

and filenames of the form `<SITE>_<Rxxxxx>_ingest.csv`, e.g.
`CP10CNSM_R00003_ingest.csv`.

Mobile assets (gliders/profilers) are also supported: since all of them
share the same `05MOAS` array-and-class code, their "site" is really
`<array><MOAS-class>-<platform ID>`, e.g. `GP05MOAS-PG380_R00001_ingest.csv`.

## Requirements

- Python 3.8+
- `ooi_ingest_check.py` uses only the standard library.
- `check_raw_archive.py` additionally needs `requests`:
  ```
  pip install requests
  ```

## 1. `ooi_ingest_check.py` — validate & diff

### Validate a single file

```
python3 ooi_ingest_check.py CP10CNSM_R00003_ingest.csv
```

Checks, per row:

- correct number of fields (catches stray/missing commas)
- no duplicate `(parser, reference_designator, data_source)` rows
- `reference_designator` matches the standard OOI format
  (e.g. `CP10CNSM-MFC31-00-CPMENG000`)
- `data_source` and `status` use recognized values
- every `filename_mask` references the data folder implied by the CSV's
  own filename (e.g. rows in `..._R00003_ingest.csv` should point at
  `.../R00003/...`)

### Validate + diff two versions

```
python3 ooi_ingest_check.py CP10CNSM_R00002_ingest.csv CP10CNSM_R00003_ingest.csv
```

Runs the single-file checks on both files, then compares them — ignoring
the expected data-folder swap (`R00002` → `R00003`) — and reports:

- rows that match exactly aside from the folder number (no action needed)
- rows whose `status`/`notes` changed
- rows whose `filename_mask` changed in some way *other* than the folder
  number (e.g. moved to a different DCL/port)
- rows that look like the *same* stream with a renamed/toggled parser
  (matched on `reference_designator` + `data_source`), reported as
  "likely modified" rather than an unrelated add + remove
- rows removed in the new file / rows newly added

### Exit status

`0` if no errors were found (warnings don't count), `1` otherwise — safe
to drop into a CI check.

## 2. `check_raw_archive.py` — confirm files exist in the archive

```
python3 check_raw_archive.py CP10CNSM_R00003_ingest.csv
```

For each row, converts `filename_mask` into the corresponding URL under
`https://rawdata.oceanobservatories.org/files/` (stripping the
`/omc_data/whoi/OMC/` prefix), walks the archive's directory listings —
resolving wildcards even when they appear in more than one path segment,
e.g. `PHSEN_*/SAMI*V.txt` — and checks that at least one matching file
exists and is non-empty. It reads file sizes straight from the listing
page and only falls back to a HEAD request when a listing doesn't show
one; **it never downloads or parses the actual data files.**

Rows are classified as:

| Severity | Meaning |
|---|---|
| `OK` | matching file(s) found, all non-empty |
| `ERROR` | status is `Available` but files are missing, empty, or the directory couldn't be listed |
| `WARN` | same problem, but status is `Expected` / `Not Available` (missing data isn't surprising there) |
| `INFO` | status is `Expected` / `Not Available` but matching files already exist — maybe update the status |

Commented-out rows (`parser` starting with `#`) are skipped by default;
pass `--include-commented` to check them too.

### Useful options

```
--base-url URL          Archive base URL (default: https://rawdata.oceanobservatories.org/files)
--timeout SECONDS       Read timeout per request attempt (default: 30). Connect timeout is
                        capped at 10s separately. Raise this if you see read-timeout errors
                        on large listings (e.g. a glider's flat "merged/" folder).
--retries N             Extra attempts for a timed-out/failed directory listing before it's
                        reported as an error (default: 2, i.e. 3 tries total; 0 disables retrying)
--retry-backoff SECONDS Base wait before a retry, doubling each attempt (default: 2.0)
--delay SECONDS         Pause before each new directory listing fetch, as a courtesy to the archive
--include-commented     Also check rows whose parser starts with '#'
--no-head-fallback      Skip the HEAD-request fallback for listings that don't show a size
```

If you still see read timeouts after raising `--timeout` and `--retries` (some glider
`merged/` directories accumulate thousands of files and can be genuinely slow to list),
try `--timeout 60 --retries 3`.

### Exit status

`0` if no rows came back as `ERROR`, `1` otherwise, `2` if the CSV
itself couldn't be read.

### A note on robots.txt

`rawdata.oceanobservatories.org`'s `robots.txt` disallows automated
crawling. This is expected — OOI's own documentation tells users to
override it for legitimate archive access (e.g.
`wget -r -np -e robots=off ...`, see
[their knowledge base](https://oceanobservatories.org/knowledgebase/how-do-i-download-an-entire-raw-data-directory/)).
`check_raw_archive.py` does the `requests`-library equivalent, which — like
`wget` with that flag — doesn't consult `robots.txt` on its own. Please
be a considerate user of the archive: the script caches each directory
listing so it's only fetched once even if many CSV rows share a folder,
and `--delay` is available if you want to throttle requests further.

## Typical workflow

```
# 1. Validate the new file and diff it against the last deployment
python3 ooi_ingest_check.py CP10CNSM_R00002_ingest.csv CP10CNSM_R00003_ingest.csv

# 2. Confirm the raw data referenced by the new file is actually present
python3 check_raw_archive.py CP10CNSM_R00003_ingest.csv
```
