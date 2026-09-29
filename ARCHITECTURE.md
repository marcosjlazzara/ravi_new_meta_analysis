# Meta Analysis Consolidation — Architecture Spec

**Source of truth for scope:** `META_BRIEF.md`. This document designs *how*, never *what*.
**Status:** **BUILD COMPLETE 2026-09-07.** All five phases implemented and QC-approved;
236/236 checks passing; `app.py` confirmed to launch. Section 8 items 4 and 9 are resolved;
items 1, 2, 3, 5, 6, 7 and 8 were **confirmed as built by Marcos on 2026-09-29**, and are marked at
their implementation sites in code. Item 10 is a note, not a decision.

**Phase 2 amended some contracts in this document. See section 10 before relying on
section 3, section 4 edge case 14, or the section 9 column-literal rule.**

**Browser-verified 2026-09-29** (STEPs 2–9, on the Phase 2 code) by Marcos.
**Four deviations** (brief section 7) signed off by Marcos, 2026-09-29.

---

## 0. Reused vs. new

**Reused from `../new_pg_antara_6_24/code/` — shape only:**

- `csv_writer.py` — the `build_filename()` / `to_csv_bytes()` split and `.encode("utf-8-sig")`.
- `app.py` — the orchestrator banner docstring listing STEPs and the module map.
- `master_loader.py` — the loader/validator split: a typed exception per loader,
  `df.columns = [str(c).strip() for c in df.columns]`, `file.seek(0)` discipline.
- `test_pipeline.py` — the `check(label, result, detail)` / `section(title)` PASS-FAIL
  harness with `sys.exit(1)` on failure.

**Not carried over:** `master_loader.py`'s hardcoded `_ORIGINAL_COLUMNS` / `_FULL_COLUMNS`
column-count validation. That is the exact anti-pattern brief decision 7 forbids — schema
comes from the uploaded master at runtime.

**Built from scratch:** everything else. No `mapping_config.py`, no `COLUMN_MAP`, no
`cleaner.py`, no `transformer.py`, no fuzzy matching.

**Complexity tier 2 — Structured Module.** ~9 flat files. Not tier 3: no CLI, no logging
config, no persistence, no scheduling, one deployment target.

**Hard architectural rule:** only `app.py` imports `streamlit`. Every other module takes
plain `bytes` / `str` / `DataFrame` and is testable headlessly. This is what makes the test
module possible at all.

---

## 1. Module map

```
code/
├── app.py                  # Streamlit orchestrator — the only file that runs directly
├── config.py               # Constants: extensions, prefix, status/reason strings, patterns
├── models.py               # Dataclasses passed between modules — the data contracts
├── file_reader.py          # bytes -> all-string DataFrame (.csv / .xlsx sheet 1)
├── master_detector.py      # Finds/validates the master; builds MasterContext
├── schema.py               # Column normalization, comparison, reordering, Study_Name tagging
├── study_processor.py      # Per-file pipeline + batch loop -> BatchResult
├── report.py               # BatchResult -> exception report DataFrame + summary dict
├── csv_writer.py           # Timestamped filenames + UTF-8-BOM bytes
├── test_meta_pipeline.py   # QC harness — python test_meta_pipeline.py
└── requirements.txt
```

### `config.py` — constants, no logic

```python
ACCEPTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx")
EXCEL_SHEET_INDEX: int = 0                    # brief decision 6: "Excel reads sheet 1"

MASTER_FILENAME_PREFIX: str = "master_"       # compared against stem.lower()
STUDY_NAME_COL: str = "Study_Name"            # the only literal column name in the app

OUTPUT_ENCODING: str = "utf-8-sig"
TIMESTAMP_FORMAT: str = "%Y-%m-%d_%H%M"       # brief decision 15
MASTER_FILENAME_PATTERN: str = "Master_File_{name}_{timestamp}.csv"
EXCEPTION_FILENAME_PATTERN: str = "Exceptions_{name}_{timestamp}.csv"
MASTER_TIMESTAMP_SUFFIX_RE: str = r"^(?P<name>.+)_\d{4}-\d{2}-\d{2}_\d{4}$"
ILLEGAL_FILENAME_CHARS: str = '<>:"/\\|?*'
FILENAME_REPLACEMENT_CHAR: str = "_"

STATUS_APPENDED: str = "appended"
STATUS_SKIPPED: str = "skipped"
STATUS_REJECTED: str = "rejected"

REASON_NONE: str = ""
REASON_UNREADABLE: str = "unreadable"
REASON_EMPTY_FILE: str = "empty file"
REASON_NO_DATA_ROWS: str = "no data rows"
REASON_COLUMN_MISMATCH: str = "column mismatch"
REASON_DUPLICATE_COLUMNS: str = "duplicate columns"
REASON_ALREADY_IN_MASTER: str = "already in master"
REASON_DUPLICATE_IN_BATCH: str = "duplicate in batch"
REASON_BLANK_STUDY_NAME: str = "blank study name"
REASON_NOT_SELECTED_MASTER: str = "not selected as master"

EXCEPTION_REPORT_COLUMNS: list[str] = ["file", "status", "reason", "missing_cols", "extra_cols"]
LIST_JOIN_SEPARATOR: str = "; "
```

`config.py` contains **no** list of the 32 data columns. The 31-column reference list from
brief section 4 lives **only** in `test_meta_pipeline.py`. Putting it in `config.py` is a
QC failure.

### `models.py` — data contracts, no behaviour

```python
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class UploadedItem:
    """One file as handed to the pipeline. app.py builds these from st.file_uploader."""
    index: int      # position in the upload list — the ONLY stable identity key
    name: str       # verbatim filename incl. extension
    data: bytes     # full file bytes, read once by app.py

    @property
    def stem(self) -> str: ...       # filename minus final extension, otherwise verbatim
    @property
    def extension(self) -> str: ...  # lowercased, incl. dot


@dataclass(frozen=True)
class MasterCandidate:
    """A file whose stem starts with 'master_' (case-insensitive)."""
    index: int
    name: str
    readable: bool
    has_study_name: bool
    error: str                       # "" when readable

    @property
    def is_valid(self) -> bool: ...  # readable and has_study_name


@dataclass(frozen=True, eq=False)
class MasterContext:
    """The runtime schema authority. Built once per run, never mutated."""
    frame: pd.DataFrame              # master rows, every column dtype=object holding str
    columns: list[str]               # verbatim master column names, in master order
    column_index: dict[str, str]     # normalized name -> verbatim master column name
    base_name: str                   # <Name> for Master_<Name>_<stamp>.csv
    source_file: str                 # filename the master came from ("" if created this run)
    source_index: int                # UploadedItem.index of the master; -1 if none
    existing_study_names: set[str]   # normalized (strip+casefold), blanks excluded
    created_this_run: bool           # True on the "first master" path


@dataclass(frozen=True)
class FileOutcome:
    """One row of the on-screen table AND the source of the exception report."""
    file: str                   # UploadedItem.name, verbatim
    index: int                  # UploadedItem.index
    status: str                 # config.STATUS_*
    reason: str                 # config.REASON_* ("" only when status == appended)
    missing_cols: list[str]     # master columns absent from the file (verbatim master names)
    extra_cols: list[str]       # file columns absent from the master (verbatim file names)
    study_name: str             # name used/attempted; "" if never determined
    rows: int                   # rows appended; 0 for skipped/rejected


@dataclass(frozen=True, eq=False)
class BatchResult:
    master_df: pd.DataFrame          # final consolidated master, master column order
    outcomes: list[FileOutcome]      # one per candidate study file, in upload order
    total_files: int                 # len(outcomes) — excludes the master itself
    appended: int
    skipped: int
    rejected: int
    rows_appended: int               # sum of FileOutcome.rows
    total_records: int               # len(master_df)
```

### `file_reader.py`

```python
class FileReadError(Exception):
    """Carries a config.REASON_* token so callers classify without string-sniffing."""
    def __init__(self, reason: str, detail: str = "") -> None: ...
    reason: str
    detail: str

def read_table(filename: str, data: bytes) -> pd.DataFrame:
    """Dispatch on extension. Returns a DataFrame whose every cell is a str.

    Raises FileReadError(REASON_EMPTY_FILE) for zero-length bytes or a CSV with no
    header line. Raises FileReadError(REASON_UNREADABLE) for anything else that fails
    to parse, or an unrecognised extension.

    Valid headers with zero data rows is NOT an error — it returns an empty DataFrame
    with populated .columns. The caller classifies that.
    """

def _read_csv_bytes(data: bytes) -> pd.DataFrame: ...
def _read_excel_bytes(data: bytes) -> pd.DataFrame: ...
def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Strip column-name whitespace; fillna(''); guarantee every cell is a str."""
```

### `schema.py` — the column contract

```python
class SchemaError(Exception):
    def __init__(self, reason: str, detail: str = "") -> None: ...

def normalize_column(name: str) -> str:
    """Lowercase, strip, collapse internal whitespace runs to one space.
    Implements brief decision 8."""

def build_column_index(columns: Sequence[str]) -> dict[str, str]:
    """normalized -> verbatim. Raises SchemaError(REASON_DUPLICATE_COLUMNS) if two
    columns normalize to the same key."""

def compare_columns(
    master_columns: Sequence[str],
    file_columns: Sequence[str],
    optional: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """Returns (missing, extra).
    missing: verbatim MASTER names not in the file, excluding any whose normalized
             form is in `optional`.
    extra:   verbatim FILE names not in the master.
    Both preserve source order. Purely comparative — no I/O, no mutation."""

def tag_study_name(df: pd.DataFrame, study_name: str, column: str) -> pd.DataFrame:
    """Return a copy with `column` set to `study_name` (str) on every row. Overwrites
    the column if present. Never touches other columns."""

def align_to_master(df: pd.DataFrame, master_columns: Sequence[str]) -> pd.DataFrame:
    """Rename the file's columns to their verbatim master equivalents (matched on
    normalized name) and reindex to master order. Values are NEVER touched.
    Precondition: compare_columns returned no missing and no extra — assert it."""
```

### `master_detector.py`

```python
def find_master_candidates(items: Sequence[UploadedItem]) -> list[MasterCandidate]:
    """Every item whose stem.lower().startswith(config.MASTER_FILENAME_PREFIX). Each is
    read; readable/has_study_name/error populated. Never raises."""

def parse_master_base_name(filename: str) -> str:
    """'Master_Instacart_2026-09-07_1430.csv' -> 'Instacart'
       'Master_Instacart.csv'                 -> 'Instacart'
       'master_A_B_2026-09-07_1430.csv'       -> 'A_B'
    Strip extension, strip prefix case-insensitively, apply MASTER_TIMESTAMP_SUFFIX_RE
    and take group 'name' if it matches, else keep all."""

def sanitize_base_name(name: str) -> str:
    """Strip; replace ILLEGAL_FILENAME_CHARS with FILENAME_REPLACEMENT_CHAR; collapse
    repeats; strip trailing dots/spaces."""

def build_master_context_from_existing(item: UploadedItem) -> MasterContext:
    """Resume path. base_name = parse_master_base_name(item.name). columns = the file's
    verbatim columns in file order. created_this_run = False.
    Raises FileReadError / SchemaError — app.py surfaces it."""

def build_master_context_from_first_file(item: UploadedItem, base_name: str) -> MasterContext:
    """First-master path. If STUDY_NAME_COL (normalized) is absent, append it LAST and
    set every row to item.stem. If already present, leave the column and its values
    exactly as they are and do not move it.  [DESIGN DEFAULT — section 8 item 2]
    base_name = sanitize_base_name(user-typed name). created_this_run = True."""

def collect_existing_study_names(frame: pd.DataFrame, study_name_column: str) -> set[str]:
    """Normalized (strip + casefold) non-blank values."""
```

### `study_processor.py`

```python
def process_file(
    item: UploadedItem,
    master: MasterContext,
    study_name: str,
    taken_names: set[str],
) -> tuple[pd.DataFrame | None, FileOutcome]:
    """Single-file pipeline. Never raises — every failure becomes a FileOutcome.
    Order of checks is fixed:
      1. blank study_name               -> rejected, REASON_BLANK_STUDY_NAME
      2. read_table                     -> rejected, e.reason (EMPTY_FILE/UNREADABLE)
      3. build_column_index(file cols)  -> rejected, REASON_DUPLICATE_COLUMNS
      4. compare_columns(optional={study_name normalized})
                                        -> rejected, REASON_COLUMN_MISMATCH + col lists
      5. len(df) == 0                   -> skipped,  REASON_NO_DATA_ROWS
      6. normalized name in taken_names -> skipped,  REASON_ALREADY_IN_MASTER
                                                     or REASON_DUPLICATE_IN_BATCH
      7. tag_study_name -> align_to_master -> appended
    Step 4 populates missing_cols/extra_cols; every other path leaves them [].
    (Step 3, duplicate columns, deliberately leaves both empty — a duplicate-column
    error has no meaningful missing-vs-extra comparison against the master. Corrected
    2026-09-07 after Phase 4 QC; the earlier "steps 3 and 4" wording was wrong.)"""

def process_batch(
    items: Sequence[UploadedItem],
    master: MasterContext,
    study_names: Mapping[int, str],
    excluded_indices: AbstractSet[int] = frozenset(),
    excluded_outcomes: Sequence[FileOutcome] = (),
) -> BatchResult:
    """Iterate items in upload order, skipping master.source_index and every index in
    excluded_indices. Seed taken = set(master.existing_study_names); after each success
    add the normalized name so a later same-named file in the SAME batch is caught.
    Concatenate master.frame + appended frames with pd.concat(..., ignore_index=True)
    and reindex to master.columns. excluded_outcomes are merged into the outcome list
    (sorted by index) so unselected master candidates appear in the report."""
```

### `report.py`

```python
def outcomes_to_frame(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """All outcomes, for the on-screen table: file, status, reason, study_name, rows,
    missing_cols, extra_cols (lists joined with LIST_JOIN_SEPARATOR)."""

def build_exception_report(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """Only outcomes where status != STATUS_APPENDED. Exactly
    config.EXCEPTION_REPORT_COLUMNS, in that order (brief section 5). Returns an empty
    frame WITH those columns when there are no exceptions."""

def summarize(result: BatchResult) -> dict[str, int]:
    """Keys, in display order:
      'Total files processed', 'Files successfully appended',
      'Files skipped (already in master)', 'Files rejected',
      'Records appended this run', 'Total records in master'."""
```

### `csv_writer.py`

```python
def build_master_filename(base_name: str, now: datetime | None = None) -> str: ...
def build_exception_filename(base_name: str, now: datetime | None = None) -> str: ...
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """df.to_csv(index=False).encode(config.OUTPUT_ENCODING).
    MUST NOT pass float_format, MUST NOT be preceded by any rounding."""
```

`now` is injectable purely so tests can assert the filename format deterministically.

### `test_meta_pipeline.py`

Standalone, `python test_meta_pipeline.py`, `check()`/`section()` harness from the
predecessor, `sys.exit(1)` on any failure. Sections:

1. Imports and config sanity
2. Reading the 12 real sample files (all readable; header counts 31 / 32 — 10 study files plus the two byte-identical masters, see section 8 item 9)
3. **Precision round-trip** (section 5) — the single most important test
4. `normalize_column` / `compare_columns` / `align_to_master` unit checks
5. Master detection: 0 / 1 / 2 candidates; `parse_master_base_name`; `Maser…` not detected
6. Full batch: 10 study files into the sample master; first-master path; re-run idempotency
7. Edge-case fixtures — `test_fixtures/` on disk plus in-memory `bytes` cases
8. Exception report and summary shape

`REFERENCE_STUDY_COLUMNS` (the 31 names from brief section 4) is defined **here and nowhere
else**, used only to assert the samples still look like we think they do.

---

## 2. Orchestration flow — `app.py`

Top-of-file banner docstring in the predecessor's style listing STEP 1…6 and the module map.

```
STEP 0  st.set_page_config / title
        Restore st.session_state["result"], ["master_bytes"], ["exception_bytes"],
        ["master_filename"], ["exception_filename"] if present.

STEP 1  INPUT SECTION  (brief flow 1)
        uploads = st.file_uploader("Drop the whole batch", type=["csv","xlsx"],
                                   accept_multiple_files=True)
        Immediately materialise: items = [UploadedItem(i, f.name, f.getvalue()) ...]
        Bytes are read exactly once. Nothing downstream touches a Streamlit object.
        If not items: st.info(...) and stop.

STEP 2  MASTER DETECTION  (brief flow 2)
        candidates = find_master_candidates(items)
        valid   = [c for c in candidates if c.is_valid]
        invalid = [c for c in candidates if not c.is_valid]
        For each invalid: st.warning naming the file and why (unreadable / no
        Study_Name column) and stating it will be treated as a study file.

        len(valid) == 1 -> master_item = that one
        len(valid) >  1 -> st.selectbox("Two master files were found. Which one is the
                           current master?"). Unselected valid candidates are EXCLUDED
                           from study processing and get FileOutcome(skipped,
                           not selected as master).
        len(valid) == 0 -> STEP 2b

STEP 2b FIRST-MASTER SLOT — rendered ONLY when len(valid) == 0  (brief flow 4)
        st.selectbox("Which file do you want to use as the first Master?",
                     options=[item.name for item in items], index=None)
        st.text_input("Study name for this master")   (brief flow 5)
        Both required before Run is enabled.
        master = build_master_context_from_first_file(chosen_item, typed_name)
        The chosen item is excluded from the study list by its .index.

STEP 3  MASTER LOADED  (brief flow 3)
        master = build_master_context_from_existing(master_item)   [resume path]
        st.caption: source filename, row count, column count, base name carried
        forward, and how many distinct Study_Name values it already holds.
        On FileReadError/SchemaError: st.error and stop — the ONE place a failure
        halts, because without a master there is no schema to validate against.

STEP 4  STUDY NAME REVIEW  (brief decision 11)
        study_items = [i for i in items if i.index not in excluded_indices]
        Default study_name = item.stem.
        st.data_editor over a 2-column frame (File [disabled], Study_Name [editable]),
        key="study_names", hide_index=True.
        Read the edited frame back into study_names: dict[int, str].
        st.warning if any two edited names normalize equal, or any is blank —
        warning only, never a blocker.

STEP 5  RUN
        Enabled only when: master is not None (and on the first-master path a file is
        chosen AND a study name typed) and len(study_items) > 0.
        result = process_batch(items, master, study_names, excluded_indices,
                               excluded_outcomes)
        Build both byte payloads and both filenames NOW and store in st.session_state.
        (Clicking a download_button triggers a rerun; results computed only inside the
        `if st.button(...)` block would vanish.)

STEP 6  OUTPUT  (brief flow 6)
        Render from st.session_state, OUTSIDE the button block:
          - summarize() as st.columns of st.metric
          - outcomes_to_frame() as st.dataframe
          - st.dataframe(result.master_df.head(20)) + caption
          - st.download_button "Download updated master"
          - st.download_button "Download exception report"  (always offered, even when
            empty, so the user never wonders whether it failed to render)
        Footer credit line, matching the predecessor.
```

---

## 3. Master detection contract

**A file is a master candidate iff** `Path(name).stem.lower().startswith("master_")`.
**A candidate is valid iff** it is also readable **and** `build_column_index(df.columns)`
contains the normalized key `"study_name"`.

| Valid candidates | Behaviour |
|---|---|
| 0 | First-master slot renders (STEP 2b). All uploaded files offered as the choice. Any prefix-matching-but-invalid file stays in the study pool with a visible warning. |
| 1 | It is the master. Its columns and column order are the rule. Excluded from the study list by `index`. |
| >1 | `st.selectbox` asks which. Unselected valid candidates are excluded from processing and recorded as `skipped` / `not selected as master`. |

**Name carry-forward** (brief decision 17) is `parse_master_base_name`, applied only on the
resume path. On the first-master path the name is typed and passed through
`sanitize_base_name`.

**Consequence:** `Samples/MaserFile_XXXX_DATE.csv` does **not** match `master_` (the `Maser`
typo). Running the sample folder as-is takes the **zero-candidates path** — correct per
decision 15, but the out-of-the-box demo does not auto-detect. See section 8 item 9.

---

## 4. Edge cases and required behaviour

| # | Situation | Behaviour |
|---|---|---|
| 1 | Zero-byte file | `rejected` / `empty file`. `read_table` short-circuits on `len(data) == 0`; also catches `pd.errors.EmptyDataError`. |
| 2 | Valid headers, zero data rows | `skipped` / `no data rows`. Structure is fine, so not rejected. Contributes 0 rows and does **not** reserve its `Study_Name`. **[section 8 item 4]** |
| 3 | Corrupt / non-tabular file with a valid extension | `rejected` / `unreadable`. Every parser exception caught and converted; `detail` goes on screen but not into the report's fixed `reason` token. |
| 4 | CSV that is not UTF-8 | `_read_csv_bytes` tries `utf-8-sig`, then `cp1252`, then `latin-1`. Only if all three fail is it `unreadable`. |
| 5 | Two files in one batch producing the same `Study_Name` | First in upload order appends; each later one is `skipped` / `duplicate in batch`. The `taken` set grows during the loop. |
| 6 | `Study_Name` already in the master | `skipped` / `already in master`. Re-running a batch appends nothing (decision 12). |
| 7 | Designated first-master file appended twice | Prevented structurally: `MasterContext.source_index` is skipped by `process_batch`. Do **not** de-duplicate by filename — two uploads can share a name. |
| 8 | `Master_*` file with no `Study_Name` column | Not a valid candidate. `st.warning`. Stays in the study pool and is validated like any other file. **[section 8 item 3]** |
| 8b | `Master_*` file that reads fine but has duplicate columns | Classified `readable=False` with the real message in `.error` — `MasterCandidate` has no third state for "read fine but schema-ambiguous", so the label is forced by the data model. **Phase 5 requirement:** `app.py` MUST surface `candidate.error` verbatim in the not-readable warning branch. A hardcoded "this file is unreadable" string would send the user hunting for a corrupt file when the actual problem is two columns normalizing to the same name. Confirmed correct in Phase 3 QC. |
| 9 | Study file that already has a `Study_Name` column | Not `extra` — the master has it. Incoming values overwritten by `tag_study_name` per decision 11. No warning. |
| 10 | Two file columns normalizing to the same name | `rejected` / `duplicate columns`, `extra_cols` lists both. Same rule on the master makes the master load fail loudly. |
| 11 | Blank/whitespace-only `Study_Name` after editing | `rejected` / `blank study name`. Checked before the file is read. |
| 12 | `.xlsx` whose sheet 1 is empty or is a chart sheet | `rejected` / `unreadable`. |
| 13 | Master with zero data rows | Legal. Schema still comes from its header row. `existing_study_names` empty. |
| 14 | Only a master uploaded, no study files | Run stays disabled; `st.info` explains. |
| 15 | Duplicate filenames in one batch | Fine — `index` is the identity key. Both appear separately; the second hits `duplicate in batch`. |
| 16 | Study file with an extra column | `rejected` / `column mismatch`, `extra_cols` populated. Never silently dropped (decision 10). |
| 17 | `Study_Name` not last in an uploaded master | Master order wins (decisions 7/9). Position left as-is. Only a *newly created* master gets it appended last. **[section 8 item 7]** |

---

## 5. Precision contract — non-negotiable

The app performs **zero arithmetic**. The guarantee is achieved by never letting a value
become a number at all.

**Mandatory read configuration:**

```python
pd.read_csv(io.BytesIO(data), dtype=str, na_filter=False,
            encoding=<attempted>, engine="c")

pd.read_excel(io.BytesIO(data), sheet_name=config.EXCEL_SHEET_INDEX, dtype=str)
```

Followed by `_finalize`: `df.columns = [str(c).strip() for c in df.columns]`, then
`df = df.fillna("").astype(str)`. After `_finalize`, **every cell in every DataFrame in this
application is a Python `str`** — master frame, study frames, and concatenated output alike.

**Banned anywhere in the codebase — each is an automatic QC rejection:**

- `astype(float)`, `astype("float64")`, `pd.to_numeric`, `.round()`, `np.float64`
- `float_format=` on `to_csv`
- `pd.read_csv` / `pd.read_excel` without `dtype=str`
- `converters=`, `parse_dates=`, `thousands=`, `decimal=`
- `pd.concat` between a str-dtype frame and any numeric-dtype frame

**Why strings rather than float64 round-tripping:** float64 → `to_csv` would in practice
round-trip these 17-significant-digit values correctly via shortest-repr, but that is a
guarantee resting on pandas' repr behaviour and it degrades silently for anything wider.
Strings are byte-exact by construction and cost nothing here — no column is ever computed on.

**Accepted limitation for the README:** if an input `.xlsx` was itself saved by Excel with
precision-as-displayed, the loss already happened upstream. The app preserves whatever the
cell holds; it never adds loss. `Samples/MaserFile_XXXX_DATE.csv` already contains
`0.035810509` where the source has `0.03581050949715417` — that pre-existing loss is carried
forward verbatim and must not be "fixed".

**QC CHECKPOINT (blocking, test section 3):**

1. Read `Samples/Instacart_Bounty_scored.csv` raw with the stdlib `csv` module into
   `list[dict[str, str]]`.
2. Run it through `read_table → tag_study_name → align_to_master → process_batch → to_csv_bytes`.
3. Decode the output, re-parse with the stdlib `csv` module.
4. Assert: for every source row and every one of the 31 source columns, the output field is
   **string-identical** to the source field. Not float-equal — identical characters.
5. Assert the literal `"0.19163628728414203"` is present in the output bytes.
6. Assert `Study_Name` is the only field the output row has that the source row does not.
7. Assert `to_csv_bytes(df)[:3] == b"\xef\xbb\xbf"` (UTF-8 BOM).

---

## 6. Dependencies

`code/requirements.txt`:

```
streamlit>=1.30      # file_uploader(accept_multiple_files), data_editor, download_button
pandas>=2.0          # DataFrame read/align/concat/write
openpyxl>=3.1        # pandas .xlsx engine
```

All three are already in the predecessor's `requirements.txt`. **Dropped:** `rapidfuzz`,
`streamlit-searchbox` — no fuzzy matching in this tool. Nothing new needs installing.

---

## 7. Build phases — each independently QC-able

**Phase 1 — Foundations.** `config.py`, `models.py`, `file_reader.py`. Test sections 1–3.
QC gate: all 12 sample files read; every cell is `str`; **the precision round-trip passes**.
Nothing proceeds until section 3 is green.

**Phase 2 — Schema.** `schema.py`. Test section 4.
QC gate: `normalize_column` handles case/whitespace; `compare_columns` returns correct
missing/extra against the `test_fixtures/` bad-header files; `align_to_master` reorders
without altering a single value; `optional` correctly exempts `Study_Name`.

**Phase 3 — Master detection.** `master_detector.py`. Test section 5.
QC gate: 0/1/2-candidate paths; `parse_master_base_name` on all four documented forms;
`MaserFile_XXXX_DATE.csv` correctly **not** detected; a first-master context built from a
file that already has `Study_Name` leaves that column untouched.

**Phase 4 — Processing and reporting.** `study_processor.py`, `report.py`. Test sections 6–8.
QC gate: 10 samples into the sample master gives the exact expected row count; a second
identical run appends zero; every edge case in section 4 produces its specified
status/reason; the exception report has exactly the 5 brief-specified columns in order.

**Phase 5 — Output and UI.** `csv_writer.py`, `app.py`, `requirements.txt`.
QC gate: filenames match `Master_<Name>_<YYYY-MM-DD_HHMM>.csv`; UTF-8 BOM present; no module
other than `app.py` imports `streamlit` (grep check); download buttons survive a rerun; the
first-master slot appears only when zero valid candidates exist.

---

## 8. Open items — requester decisions (all confirmed as built by Marcos, 2026-09-29)

A default is specified for each so the developer is never blocked. Each default is marked in
code with `# DESIGN DEFAULT — confirmed 2026-09-29, see spec section 8, item N` (it read "pending
confirmation" until then).

1. **"Total records consolidated"** (brief section 5) — rows added this run, or rows in the
   final master? Default: show **both**.
2. **First-master file that already contains `Study_Name`** — this is the real sample
   (`MaserFile_XXXX_DATE.csv`, holding `Holly_Rancher 27382_Scored`). Brief flow 4 says
   "`Study_Name` added", silent on this case. Default: leave the column and its values
   completely untouched. The alternative would overwrite all 52 rows with
   `MaserFile_XXXX_DATE` and destroy real data.
3. **`Master_*` file lacking `Study_Name`** — brief flow 2 says verify the column, not what
   happens when verification fails. Default: warn, exclude from candidacy, process as an
   ordinary study file. Alternative: reject outright with a dedicated reason.
4. ~~**Valid headers, zero data rows**~~ — **RESOLVED 2026-09-07: `skipped` / `no data rows`,
   does not reserve its `Study_Name`.** The structure is valid, so a rejection would be
   misleading, and a real version of the same study later in the batch must still be able
   to append.
5. **Unselected master candidate when two are found** — brief says the app asks which, not
   what becomes of the loser. Default: excluded, reported as `skipped` /
   `not selected as master`. The literal alternative would append an entire second master's
   rows into the first.
6. **`Study_Name` duplicate comparison sensitivity** — decision 8's insensitivity is scoped
   to *column names*. Default for duplicate detection: strip + casefold, stored verbatim, so
   `instacart_bounty` and `Instacart_Bounty` collide. Alternative: exact match.
7. **`Study_Name` position in an inherited master** — decision 11 says "last column",
   decisions 7/9 say master order is the rule. These conflict when a user's master has it
   elsewhere. Default: master order always wins; "last" applies only to a newly created column.
8. **Exception report filename** — not specified. Default:
   `Exceptions_<Name>_<YYYY-MM-DD_HHMM>.csv`, same base name and stamp as the master.
9. ~~**The `Maser` typo**~~ — **RESOLVED 2026-09-07: a correctly-named copy was added.**
   `Samples/Master_Instacart_2026-09-07_1200.csv` is byte-identical to
   `MaserFile_XXXX_DATE.csv` (MD5 `baab1c71abbf10e81c16588c57737d63`) and gives the resume
   path something real to run against.

   **Trap the test suite must cover:** `Samples/` now contains *both* files. Dropping the
   whole folder in yields exactly one valid master (`Master_Instacart_…`), and
   `MaserFile_XXXX_DATE.csv` falls through to the study pool — where it **matches the master
   schema perfectly**, because it has the same 32 columns including `Study_Name`. It would be
   appended as a study named `MaserFile_XXXX_DATE`, silently duplicating Holly_Rancher's 52
   rows under a second name.

   This is the design working exactly as specified — decision 11 overwrites the incoming
   `Study_Name`, and nothing in the spec detects that a study file is really a master in
   disguise. It is correct behaviour with a surprising outcome, so:
   - Test section 6 must assert this happens rather than assuming a clean 10-file append.
   - Whoever demos the tool should drop in the 10 study files plus **one** master, not the
     whole folder.
10. **Note, not an ambiguity:** decision 13's "master stays at 32 columns" is descriptive of
    the current data, not an invariant. Nothing in application logic asserts 32; the count is
    asserted only in `test_meta_pipeline.py` against the sample files.

---

## 9. Handoff

```
HANDOFF TO: python-developer
COMPLEXITY TIER: 2 (Structured Module, flat code/ directory)

IMPLEMENT IN THIS ORDER:
1. config.py + models.py + file_reader.py        (Phase 1 — stop at the precision gate)
2. schema.py                                      (Phase 2)
3. master_detector.py                             (Phase 3)
4. study_processor.py + report.py                 (Phase 4)
5. csv_writer.py + app.py + requirements.txt      (Phase 5)
6. test_meta_pipeline.py grows with each phase — do not leave it to the end

HARD RULES:
- Only app.py may import streamlit.
- No column name other than Study_Name appears as a literal in code/ (the 31-name
  reference list belongs in test_meta_pipeline.py alone).
- dtype=str everywhere; the banned-call list in section 5 is absolute.
- No filesystem writes anywhere in the app. Downloads only.
- Validation never halts the run. The single exception is a master that cannot be
  loaded, because there is then no schema to validate against.

DO NOT make design decisions not covered in this spec.
The 10 items in section 8 are open with the requester — implement the stated default,
mark it with the DESIGN DEFAULT comment, and do not invent a different one.

QC CHECKPOINT: qc-reviewer after EVERY phase, not only at the end.
The Phase 1 precision round-trip is a blocking gate.
```

---

## 10. Phase 2 amendments

Added 2026-09-29, after the Phase 2 build (branch `phase2`) passed QC and browser verification.
Phase 2 is designed in `PHASE2_ARCHITECTURE.md`; this section lists only the places where a
**Phase 1** contract in this document changed, so nothing above is silently stale.
Decision numbers `P#` refer to `PHASE2_BRIEF.md`.

| Where in this doc | What changed | Detail |
|---|---|---|
| Section 4, edge case 14 | **Superseded by P4.** An existing master with zero study files now **runs**: Run is enabled, `st.info(config.MSG_MASTER_ONLY_RUN)` is shown, and the result is 0 appended with `master_df` equal to the master. The first-master path is unchanged; it still needs at least one other file. | `study_processor.is_run_ready(master, study_item_count)` replaces `master is not None and len(study_items) > 0` in STEP 5. `process_batch` itself did not change. `PHASE2_ARCHITECTURE.md` section 5 |
| `study_processor.py`, `process_file` | New **step 3b**, after the duplicate-columns check and before the column-mismatch check. A file whose headers carry any Phase 2 calculated or merged column is `rejected` with `REASON_PHASE2_OUTPUT` (P3). `missing_cols`/`extra_cols` stay empty, so it is still true that only step 4 populates them. | `schema.find_phase2_output_headers`. `PHASE2_ARCHITECTURE.md` sections 1.7, 4 |
| `models.py`, `MasterCandidate` | New field `is_phase2_output: bool = False`. `is_valid` is now `readable and has_study_name and not is_phase2_output`. | `PHASE2_ARCHITECTURE.md` section 1.2 |
| Section 3, master detection contract | Extended by P3. A `master_*` file that is Phase 2 output is not a valid candidate: STEP 2 warns. If another valid master exists, the file goes to the study pool and step 3b rejects it. If none exists, `master_detector.first_master_slot_allowed()` is False, STEP 2b is not rendered and Run stays disabled. Both master-context builders also refuse Phase 2 output with `SchemaError(REASON_PHASE2_OUTPUT)`. That is the existing "master cannot be loaded" exception, now covering a second case. | `PHASE2_ARCHITECTURE.md` sections 1.6, 4 |
| `file_reader.py` | New `read_raw_grid(filename, data)`: a header-less read that returns the header row exactly as typed, with no pandas `Unnamed: n` / `.1` mangling. Used by the Phase 2 template upload. `read_table` is unchanged. Still `dtype=str` on every read. | `PHASE2_ARCHITECTURE.md` section 1.5 |
| Section 9 handoff, hard rule on column literals | **Amended.** Column names may appear as literals only in `config.py`, not "only `Study_Name`". Phase 2 must name its source columns (`dependent_variable`, `CNT_EXPSD_HH`, `ADJ_MEAN_EXPSD_GRP`, `MODEL_DESC`, `Model`) and match them by name, never by letter. The 31-name reference list is still in `test_meta_pipeline.py` only. | `CLAUDE.md` rule 4 |
| Section 5, precision contract | **Extended, not relaxed.** Source values still pass through byte-exact. The 8 calculated columns are computed with `decimal.Decimal` on parsed copies, never float, in `numeric.py`, the only module that touches `decimal`. | `CLAUDE.md` rule 2. `PHASE2_ARCHITECTURE.md` section 2 |
| `test_meta_pipeline.py` | The section 1 check "config.py carries no list of the 32 data columns" is **replaced**. The set of reference column names appearing anywhere in `config` must be exactly the 5 calculation source columns, and no single config sequence may hold more than 3 of them. New sections: **10** AST rule scans (rules 2, 3 and 4, plus the openpyxl import location), **11** master-only Run and P3 detection, **12** template, **13a** calculations with synthetic data, **13b** comparison against Ravi's reference workbook, **14** upload validation, merge and warnings. Total: 236 checks became 556, then 561 with the Q16 banner checks in section 8. | `PHASE2_ARCHITECTURE.md` section 10 |
| Section 2, STEP 6 | **New, Q16 (2026-09-29).** When any file is rejected, a warning banner at the top of Results lists every rejected file with its reason, and tells the user to fix the files and run again. Built by `report.rejected_files_message` from `config.MSG_FILES_REJECTED_ONE` / `_MANY`. The count uses the same rule as `BatchResult.rejected`. Behaviour is unchanged: rejected files still don't block the rest of the batch (Q15: the schema stays locked by choice). | `QUESTIONS_FOR_RAVI.md` Q15/Q16 |

New Phase 2 modules (`numeric.py`, `calculations.py`, `template_builder.py`,
`metadata_upload.py`, `final_builder.py`) and the Phase 2 STEPs 7–9 in `app.py` are specified
in `PHASE2_ARCHITECTURE.md` alone.
