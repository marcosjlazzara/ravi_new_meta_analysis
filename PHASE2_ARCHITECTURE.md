# Meta Analysis — Phase 2 Architecture Spec (Study metadata & calculations)

**Source of truth for scope:** `PHASE2_BRIEF.md` (P1–P33, locked). This document designs *how*, never *what*.
`ARCHITECTURE.md` remains the Phase 1 design authority; section 12 below lists the exact amendments it needs.
**Status:** DESIGN — **approved by Marcos 2026-09-28**, all section 15 concerns accepted as recommended. Branch `phase2`.

Design defaults (things the brief does not settle) are numbered in section 11. Each must be marked in code with
`# DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item N`.
Items that strain or conflict with a locked decision are listed in section 15 (Concerns), not quietly designed around.

---

## 0. Scope, tier, reuse, and findings in the existing code

**Complexity tier: 2 (Structured Module), unchanged.** Four new flat modules plus one small helper module in
`code/`, and minimal additive changes to six Phase 1 modules. No CLI, no persistence, no logging config.

**Reused as-is:** `file_reader.read_table` (study/master reads, and the xlsx-as-sheet-1 rule), `schema.normalize_column`
/ `build_column_index`, `csv_writer.to_csv_bytes` (UTF-8-BOM), the `TIMESTAMP_FORMAT` filename shape, the Phase 1
`st.session_state` pattern (STEP 5 writes, STEP 6 reads outside the button block), the `check()`/`section()` test
harness, the `FileReadError`/`SchemaError` reason-token pattern.

**Built from scratch:** `numeric.py`, `calculations.py`, `template_builder.py`, `metadata_upload.py`, `final_builder.py`.

**Findings in the existing code that this design has to deal with:**

1. **There is no rule-4 literal scan and no rule-2 banned-token scan in `test_meta_pipeline.py` today.** The only
   static checks are the streamlit-import AST scan (section 9) and a config sanity check (section 1, lines 93–100)
   that fails if `config.py` holds any list or tuple longer than 5 other than `ACCEPTED_EXTENSIONS`. `PHASE2_BRIEF`
   section 9 and `CLAUDE.md` rule 4 both say the scan "is updated to exempt `config.py`". There is nothing to update.
   Stage 1 therefore **adds** both scans (section 10.1) and **replaces** the list-length check. As written, that
   check would fail on `CALCULATED_HEADERS` (8 entries) and `TEMPLATE_HEADERS` (7 entries).
2. `schema.normalize_column` uses `str.strip()`, which does **not** remove `\u200b` (U+200B is not whitespace in Python).
   Ravi's original headers end in `\u200b`, so P3 detection needs its own zero-width-stripping normaliser (section 1.4).
3. `pandas.read_csv`/`read_excel` with `header=0` rewrite headers: a blank header becomes `Unnamed: 7`, and a
   duplicate `Brand, Brand` becomes `Brand, Brand.1`. That makes P14's "blank header" and "duplicate header" rules
   undetectable through `read_table`. The Phase 2 upload is therefore read through a new header-less grid reader
   (section 1.5), which leaves `read_table` untouched.
4. `ARCHITECTURE.md` edge case 14 ("only a master uploaded → Run stays disabled") is superseded by P4.
   `CLAUDE.md`'s code-structure row "config.py — Contains NO data column names" is superseded by amended rule 4.
5. Stage 1 in `PHASE2_BRIEF` section 10 lists `app.py`, `master_detector.py` and tests. The minimal correct change also
   touches `config.py`, `models.py`, `schema.py` and `study_processor.py`. Each change is additive (section 1).

---

## 1. Module map

```
code/
├── app.py               # CHANGED — STEP 2/4/5/6 tweaks (Stage 1); Run-block additions + STEPs 7–9 (Stage 5)
├── config.py            # CHANGED — Phase 2 constants appended (section 1.1)
├── models.py            # CHANGED — MasterCandidate.is_phase2_output; 5 new dataclasses
├── numeric.py           # NEW — exact-decimal parse / multiply / format; the P17 numeric test
├── schema.py            # CHANGED — normalize_header, find_phase2_output_headers, column_letter
├── file_reader.py       # CHANGED — read_raw_grid (header-less read); read_table unchanged
├── master_detector.py   # CHANGED — P3 detection on candidates and both master builders; first_master_slot_allowed
├── study_processor.py   # CHANGED — process_file step 3b (P3); is_run_ready (P4)
├── calculations.py      # NEW — master frame -> 8 calculated columns + calculation warnings
├── template_builder.py  # NEW — distinct study list -> studyname_master .xlsx bytes (openpyxl, BytesIO)
├── metadata_upload.py   # NEW — completed-template bytes -> ParsedUpload (P10–P18 file/header/row rules)
├── final_builder.py     # NEW — master + calculations + ParsedUpload -> FinalResult (matching, value check, merge)
├── report.py            # CHANGED — phase2_warnings_to_frame, summarize_phase2_warnings
├── csv_writer.py        # CHANGED — 3 new filename builders
├── test_meta_pipeline.py# CHANGED — section 1 check replaced; sections 10–14 added
└── requirements.txt     # comment-only change for openpyxl
```

Only `app.py` imports `streamlit`. Only `template_builder.py` (and the test file) imports `openpyxl` directly.

### 1.1 `config.py` — additions (append verbatim after the existing constants)

Column names appear as literals **only** here (amended rule 4). All glossary and message text that names a column
also lives here, built from the constants so the text cannot drift from the names.

```python
# =============================================================================
# PHASE 2 — study metadata & calculations (PHASE2_BRIEF.md)
# Amended rule 4: column names appear as literals ONLY in this file.
# =============================================================================

# --- P3: Phase 1 recognises Phase 2 output ----------------------------------
REASON_PHASE2_OUTPUT: str = "calculated columns (Phase 2 output)"

# --- P24: calculation source columns, matched by normalized NAME, never letter
DEPENDENT_VARIABLE_COL: str = "dependent_variable"   # "F" in Ravi's workbook
CNT_EXPSD_HH_COL: str = "CNT_EXPSD_HH"               # "G"
ADJ_MEAN_EXPSD_GRP_COL: str = "ADJ_MEAN_EXPSD_GRP"   # "N"
MODEL_DESC_COL: str = "MODEL_DESC"
MODEL_COL: str = "Model"

# --- P22: dependent_variable values, compared against value.strip().casefold()
DEP_VAR_PEN: str = "pen"
DEP_VAR_OCC: str = "occ"
DEP_VAR_DOLHH: str = "dolhh"

# --- P25: calculated headers EXACTLY as output (zero-width chars stripped,
#     "Instacart Member" -> "Partner Member"). Order = output order (AG..AN for a
#     32-column master; letters are illustrative, placement is relative — P26).
CALC_TOTAL_ANALYZED_POPULATION: str = "Total Analyzed Population"
CALC_COUNT_CIRCANA_BUYERS: str = "Count of Circana Buyers"
CALC_PARTNER_MEMBER_OVERLAP: str = "Partner Member Overlap % with Circana Retailer"
CALC_DOLLARS_PER_HH: str = "Dollars spent at Circana Retailer by HH"
CALC_TOTAL_DOLLARS: str = "Total Dollars spent at Circana Retailers"
CALC_TOTAL_TRIPS: str = "Total Buying Trips at Circana Retailer"
CALC_TRIPS_PER_BUYER: str = "Total Buying Trips per Buyer at Circana Retailer"
CALC_OFFLINE_NEW_BUYERS: str = "Total Offline Category New Buyers"   # always empty (P25)
CALCULATED_HEADERS: tuple[str, ...] = (
    CALC_TOTAL_ANALYZED_POPULATION, CALC_COUNT_CIRCANA_BUYERS, CALC_PARTNER_MEMBER_OVERLAP,
    CALC_DOLLARS_PER_HH, CALC_TOTAL_DOLLARS, CALC_TOTAL_TRIPS, CALC_TRIPS_PER_BUYER,
    CALC_OFFLINE_NEW_BUYERS,
)
# Ravi's original wording — recognised for P3 detection only, never output.
LEGACY_CALCULATED_HEADERS: tuple[str, ...] = ("Instacart Member Overlap % with Circana Retailer",)
ZERO_WIDTH_CHARS: str = "\u200b\u200c\u200d\u2060\ufeff"

# --- P6: template headers ----------------------------------------------------
TEMPLATE_AVG_BRAND_PRICE: str = "Avg_Brand_Price"
TEMPLATE_AVG_PURCH_CYCLE: str = "Avg_Purch_Cycle"
TEMPLATE_PCT_HH_BUYING: str = "Pct_HH_Buying"
TEMPLATE_TOT_CAMP_COST: str = "Tot_Camp_Cost"
TEMPLATE_TOT_CAMP_IMPR: str = "Tot_Camp_Impr"
TEMPLATE_READ_TYPE: str = "Read_Type"
TEMPLATE_VALUE_HEADERS: tuple[str, ...] = (           # the "fixed six" merged columns (B..G)
    TEMPLATE_AVG_BRAND_PRICE, TEMPLATE_AVG_PURCH_CYCLE, TEMPLATE_PCT_HH_BUYING,
    TEMPLATE_TOT_CAMP_COST, TEMPLATE_TOT_CAMP_IMPR, TEMPLATE_READ_TYPE,
)
TEMPLATE_HEADERS: tuple[str, ...] = (STUDY_NAME_COL, *TEMPLATE_VALUE_HEADERS)   # A..G
NUMERIC_CHECKED_HEADERS: tuple[str, ...] = TEMPLATE_VALUE_HEADERS[:5]          # P16: B..F only

# --- P3 signature: any of these in a file's headers => Phase 2 output ---------
PHASE2_OUTPUT_SIGNATURE_HEADERS: tuple[str, ...] = (
    *CALCULATED_HEADERS, *LEGACY_CALCULATED_HEADERS, *TEMPLATE_VALUE_HEADERS,
)  # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item 6

# --- P11: an upload is "the master" if it carries ALL of these ---------------
MASTER_LOOKALIKE_COLUMNS: tuple[str, ...] = (MODEL_DESC_COL, MODEL_COL, DEPENDENT_VARIABLE_COL)
# DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item 8

# --- P16/P17 value check -----------------------------------------------------
VALUE_CHECK_ENABLED: bool = True
# Used with re.fullmatch on value.strip(). ASCII digits only; exponent 1–3 digits.
NUMERIC_VALUE_RE: str = r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?"

# --- P14 user extras ---------------------------------------------------------
EXTRA_HEADER_MAX_LEN: int = 15
EXTRAS_START_COL_INDEX: int = 7            # 0-based grid index of column H

# --- P20/P21 arithmetic ------------------------------------------------------
ARITH_PRECISION: int = 100                 # significant digits; products are exact far below this
AM_ROUND_TO_2DP: bool = False              # P21: full precision until Ravi asks otherwise
AM_ROUND_QUANTUM: str = "0.01"

# --- P7/P8/P18 template workbook ---------------------------------------------
TEMPLATE_SHEET_TITLE: str = "studyname_master"
GLOSSARY_SHEET_TITLE: str = "Glossary"
PCT_NUMBER_FORMAT: str = "0.00%"           # DESIGN DEFAULT — see section 11, item 18
XLSX_MAX_COLUMN: int = 16384               # XFD
TEMPLATE_STUDY_COL_WIDTH: int = 45
TEMPLATE_VALUE_COL_WIDTH: int = 18
XLSX_MIME: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MIME: str = "text/csv"

# --- P7/P19/P30 filenames (same {name}/{timestamp} contract as Phase 1) -------
TEMPLATE_FILENAME_PATTERN: str = "studyname_master_{name}_{timestamp}.xlsx"
FINAL_FILENAME_PATTERN: str = "after_formulas_master_{name}_{timestamp}.csv"
PHASE2_WARNINGS_FILENAME_PATTERN: str = "phase2_warnings_{name}_{timestamp}.csv"  # DESIGN DEFAULT — item 17

# --- P30 warnings report -----------------------------------------------------
PHASE2_WARNING_COLUMNS: list[str] = ["Study", "Model", "Column", "Issue"]
BLOCK_LABEL_PATTERN: str = "{model_desc} / {model}"        # DESIGN DEFAULT — item 5

# Warning codes (tests assert on these, never on issue text; codes are never written out)
P2W_SOURCE_COLUMN_MISSING: str = "source_column_missing"
P2W_BLOCK_ROLE_MISSING: str = "block_role_missing"
P2W_BLOCK_ROLE_DUPLICATED: str = "block_role_duplicated"
P2W_VALUE_BLANK: str = "value_blank"
P2W_VALUE_NOT_NUMERIC: str = "value_not_numeric"
P2W_VALUE_TOO_PRECISE: str = "value_too_precise"
P2W_UPLOAD_ZERO_MATCH: str = "upload_zero_match"
P2W_UPLOAD_SECOND_STUDY_NAME: str = "upload_second_study_name"
P2W_UPLOAD_BLANK_HEADER: str = "upload_blank_header"
P2W_UPLOAD_UNEXPECTED_COLUMN: str = "upload_unexpected_column"
P2W_UPLOAD_FIXED_MISSING: str = "upload_fixed_missing"
P2W_UPLOAD_FIXED_DUPLICATED: str = "upload_fixed_duplicated"
P2W_UPLOAD_EXTRA_RESERVED: str = "upload_extra_reserved"
P2W_UPLOAD_EXTRA_DUPLICATED: str = "upload_extra_duplicated"
P2W_UPLOAD_EXTRA_TOO_LONG: str = "upload_extra_too_long"
P2W_UPLOAD_ROW_NO_STUDY: str = "upload_row_no_study"
P2W_MASTER_BLANK_STUDY: str = "master_blank_study"
P2W_STUDY_NOT_IN_UPLOAD: str = "study_not_in_upload"
P2W_STUDY_DUPLICATED: str = "study_duplicated"
P2W_STUDY_NOT_IN_MASTER: str = "study_not_in_master"
P2W_VALUE_NOT_PLAIN_NUMBER: str = "value_not_plain_number"

# Issue text templates (str.format placeholders documented in section 7.5)
ISSUE_SOURCE_COLUMN_MISSING: str = "Column not found in the master — left blank: {headers}"
ISSUE_BLOCK_ROLE_MISSING: str = "No {roles} row in this model block — left blank: {headers}"
ISSUE_BLOCK_ROLE_DUPLICATED: str = "More than one {roles} row in this model block — left blank: {headers}"
ISSUE_VALUE_BLANK: str = "Blank value on the {role} row (master row {row}) — left blank: {headers}"
ISSUE_VALUE_NOT_NUMERIC: str = "Not a number ('{value}') on the {role} row (master row {row}) — left blank: {headers}"
ISSUE_VALUE_TOO_PRECISE: str = "Exact result needs more than {prec} significant digits (master row {row}) — left blank: {headers}"
ISSUE_UPLOAD_ZERO_MATCH: str = "None of the {n} studies in this file match the current master."
ISSUE_UPLOAD_SECOND_STUDY_NAME: str = "Another " + STUDY_NAME_COL + " column in column {letter} — ignored; column {first_letter} is used"
ISSUE_UPLOAD_BLANK_HEADER: str = "Column {letter} has values but no header — ignored"
ISSUE_UPLOAD_UNEXPECTED_COLUMN: str = "Unrecognised column in column {letter} — ignored. Add your own columns from column H onward"
ISSUE_UPLOAD_FIXED_MISSING: str = "Column not found in the uploaded file — left blank in the final file"
ISSUE_UPLOAD_FIXED_DUPLICATED: str = "Column appears {count} times (columns {letters}) — all ignored; left blank in the final file"
ISSUE_UPLOAD_EXTRA_RESERVED: str = "Header repeats a master or calculated column name (column {letters}) — ignored"
ISSUE_UPLOAD_EXTRA_DUPLICATED: str = "Header appears {count} times (columns {letters}) — all ignored"
ISSUE_UPLOAD_EXTRA_TOO_LONG: str = "Header is {length} characters (15 or fewer recommended) — still merged"
ISSUE_UPLOAD_ROW_NO_STUDY: str = "Row {row} has values but no study name — ignored"
ISSUE_MASTER_BLANK_STUDY: str = "{count} master row(s) have a blank " + STUDY_NAME_COL + " — metadata columns left blank"
ISSUE_STUDY_NOT_IN_UPLOAD: str = "Study not in the uploaded file — metadata columns left blank"
ISSUE_STUDY_DUPLICATED: str = "Study appears {count} times in the uploaded file (rows {rows}) — metadata columns left blank"
ISSUE_STUDY_NOT_IN_MASTER: str = "Study not in the master — row(s) {rows} ignored"
ISSUE_VALUE_NOT_PLAIN_NUMBER: str = "Not a plain number ('{value}') — merged as typed"

# --- Section 6 messages, VERBATIM. The leading symbol in PHASE2_BRIEF section 6
# selects the Streamlit box (warning / info / error / success) and is NOT part of
# the string. DESIGN DEFAULT — item 19.
MSG_PHASE2_OUTPUT: str = (
    "**This file contains calculated columns.** It looks like an `after_formulas_master` output. "
    "Please upload the original Master File (`Master_File_…`), without calculations."
)
MSG_TEMPLATE: str = (
    "**This template lists all {n} studies currently in the master, with blank values.** Values from "
    "earlier sessions are not carried over. If you completed a `studyname_master` before, copy those "
    "rows into this new file before uploading it."
)
MSG_COLUMN_MATCHING: str = (
    "**Calculations match source columns by column name, not by position** (e.g. `" + CNT_EXPSD_HH_COL
    + "`, `" + ADJ_MEAN_EXPSD_GRP_COL + "`). If a column is renamed or missing in the master, the "
    "calculated columns that depend on it are left blank and listed in the warnings."
)
MSG_WRONG_FILE: str = (
    "This doesn't look like a `studyname_master` file (no `" + STUDY_NAME_COL + "` column). "
    "Please upload the completed template downloaded above."
)
MSG_ZERO_MATCH: str = "None of the {n} studies in this file match the current master. Is this from a different project?"
MSG_MASTER_ONLY_RUN: str = "No study files uploaded. The master will be used as-is for Phase 2."
# NOT agreed wording — proposals, see section 15 item C3:
MSG_UPLOAD_IS_MASTER: str = (
    "This looks like a master or `after_formulas_master` file (it contains the master's data columns), "
    "not a `studyname_master` file. Please upload the completed template downloaded above."
)
MSG_UPLOAD_UNREADABLE: str = "This file could not be read ({detail}). Please upload the completed template downloaded above."
MSG_NO_ISSUES: str = "No issues found"
MSG_WARNINGS_SUMMARY: str = (
    "{total} warning(s) — {calc} from the calculations, {upload} from the uploaded template. "
    "The final file can still be downloaded."
)  # DESIGN DEFAULT — item 20
MSG_UPLOAD_PROMPT: str = (
    "Upload the completed template to build the final file. For calculations only, upload the "
    "blank template as downloaded."
)  # DESIGN DEFAULT — item 20

# --- P31 glossary. Confirmed 2026-09-29 (QUESTIONS_FOR_RAVI Q23/Q24) ----------
GLOSSARY_FIELDS_TITLE: str = "Columns to fill in"
GLOSSARY_FIELD_COLUMNS: tuple[str, ...] = ("Header", "Full name", "What to enter", "Example")
GLOSSARY_FIELD_ROWS: tuple[tuple[str, str, str, str], ...] = (
    (STUDY_NAME_COL, "Study name", "Locked — filled by the app from the master. Do not edit.", "Instacart_Cascade"),
    (TEMPLATE_AVG_BRAND_PRICE, "Average Brand Price", "Average price of the target brand (study period or latest 52 weeks). Number only, no currency symbol.", "3.49"),
    (TEMPLATE_AVG_PURCH_CYCLE, "Average Purchase Cycle", "Average time between purchases. Whole number (e.g. 45).", "45"),
    (TEMPLATE_PCT_HH_BUYING, "% Household Buying", "Share of households buying. Type 25% or 0.25 — stored as 0.25.", "25%"),
    (TEMPLATE_TOT_CAMP_COST, "Total Campaign Cost", "Total media cost of the campaign. Number only, no commas or currency symbol.", "150000"),
    (TEMPLATE_TOT_CAMP_IMPR, "Total Campaign Impressions", "Total impressions delivered. Number only, no commas.", "12500000"),
    (TEMPLATE_READ_TYPE, "Read Type", "Type of read, as text.", "Featured, Halo"),
)
GLOSSARY_EXTRAS_TITLE: str = "Adding your own columns"
GLOSSARY_EXTRAS_TEXT: str = (
    "Add new columns from column H onward. Each header must be unique, must not repeat a master "
    "column name, and should be 15 characters or fewer."
)
GLOSSARY_RULES_TITLE: str = "Rules"
GLOSSARY_RULES: tuple[str, ...] = (
    "Column A is locked; study names come from the master.",
    "A blank cell means \"not filled in yet\" and stays blank in the final file.",
    "Numbers: plain digits only — no $, no thousands commas, no text. Anything else is kept as typed but flagged in the warnings.",
    "Values are repeated on every row of their study in the final file.",
)
GLOSSARY_CALC_COLUMNS: tuple[str, ...] = ("Column", "Definition")     # on screen only (P31)
GLOSSARY_CALC_BLOCK_NOTE: str = (
    "A model block is the set of rows sharing " + STUDY_NAME_COL + ", " + MODEL_DESC_COL + " and " + MODEL_COL + "."
)
GLOSSARY_CALC_ROWS: tuple[tuple[str, str], ...] = (
    (CALC_TOTAL_ANALYZED_POPULATION, f"{CNT_EXPSD_HH_COL} of the {DEP_VAR_DOLHH} row. Shown on the {DEP_VAR_DOLHH} row."),
    (CALC_COUNT_CIRCANA_BUYERS, f"{ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_PEN} row × {CNT_EXPSD_HH_COL} of the {DEP_VAR_DOLHH} row, per model block. Shown on the {DEP_VAR_PEN} row."),
    (CALC_PARTNER_MEMBER_OVERLAP, f"{ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_PEN} row. Shown on the {DEP_VAR_PEN} row."),
    (CALC_DOLLARS_PER_HH, f"{ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_DOLHH} row. Shown on the {DEP_VAR_DOLHH} row."),
    (CALC_TOTAL_DOLLARS, f"{ADJ_MEAN_EXPSD_GRP_COL} × {CNT_EXPSD_HH_COL}, both of the {DEP_VAR_DOLHH} row. Shown on the {DEP_VAR_DOLHH} row."),
    (CALC_TOTAL_TRIPS, f"{ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_PEN} row × {CNT_EXPSD_HH_COL} of the {DEP_VAR_DOLHH} row × {ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_OCC} row, per model block. Shown on the {DEP_VAR_PEN} row."),
    (CALC_TRIPS_PER_BUYER, f"{ADJ_MEAN_EXPSD_GRP_COL} of the {DEP_VAR_OCC} row, full precision. Shown on the {DEP_VAR_OCC} row."),
    (CALC_OFFLINE_NEW_BUYERS, "Not calculated yet — the column is included, empty."),
)
```

`config.py` holds no logic. `ARCHITECTURE.md` section 1's "no list of the 32 data columns" still holds: the
31-name reference list stays solely in `test_meta_pipeline.py`. The replacement config check (section 10.1)
enforces this.

### 1.2 `models.py` — changes and additions

```python
@dataclass(frozen=True)
class MasterCandidate:
    index: int
    name: str
    readable: bool
    has_study_name: bool
    error: str
    is_phase2_output: bool = False     # NEW (P3). Defaulted: every existing construction still works.

    @property
    def is_valid(self) -> bool:
        return self.readable and self.has_study_name and not self.is_phase2_output   # CHANGED


@dataclass(frozen=True)
class Phase2Warning:
    """One row of the P30 warnings table / phase2_warnings CSV."""
    study: str      # verbatim study name ("" for file- or master-level issues)
    model: str      # block label per config.BLOCK_LABEL_PATTERN ("" when not block-specific)
    column: str     # verbatim column name concerned ("" when it has no header)
    issue: str      # human text from a config.ISSUE_* template
    code: str       # config.P2W_* token — for tests; never written to any output


@dataclass(frozen=True, eq=False)
class CalculationResult:
    frame: pd.DataFrame            # columns == list(config.CALCULATED_HEADERS), in order; len == len(master_df);
                                   # RangeIndex; dtype=object; every cell a str ("" = blank)
    warnings: list[Phase2Warning]  # emission order per section 3.6


@dataclass(frozen=True)
class UploadRow:
    study_name: str                # verbatim cell from the upload's Study_Name column
    values: dict[str, str]         # every ParsedUpload.merge_columns key present; verbatim cell text,
                                   # "" where the fixed column was missing/ignored
    row_number: int                # 1-based spreadsheet row (header row = 1)


@dataclass(frozen=True, eq=False)
class ParsedUpload:
    accepted: bool                             # False => P11 refusal, no final file
    refusal_message: str                       # "" when accepted
    merge_columns: list[str]                   # all six config.TEMPLATE_VALUE_HEADERS, then accepted extras
                                               # (verbatim stripped upload header, upload order)
    present_fixed: frozenset[str]              # fixed headers found exactly once (config verbatim)
    rows_by_study: dict[str, list[UploadRow]]  # key = study.strip().casefold(); insertion = first appearance
    warnings: list[Phase2Warning]              # file-level and row-level upload warnings, section 7.5 order


@dataclass(frozen=True, eq=False)
class FinalResult:
    frame: pd.DataFrame            # master cols (unchanged) + CALCULATED_HEADERS + merge_columns; all str
    warnings: list[Phase2Warning]  # calculation warnings, then upload warnings (section 7.5 order)
    calculation_warning_count: int
    upload_warning_count: int
    zero_match: bool               # P11 strong warning
    upload_study_count: int        # distinct normalized non-blank study names in the upload
```

### 1.3 `numeric.py` — NEW. Exact-decimal helpers; the only module that touches `decimal`

```python
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, DivisionByZero, ROUND_HALF_EVEN, ROUND_HALF_UP

ARITH_CONTEXT: Context      # Context(prec=config.ARITH_PRECISION, rounding=ROUND_HALF_EVEN,
                            #         traps=[InvalidOperation, DivisionByZero, Overflow, Inexact])
ROUNDING_CONTEXT: Context   # Context(prec=config.ARITH_PRECISION, rounding=ROUND_HALF_UP,
                            #         traps=[InvalidOperation])   — deliberate rounding only (AM flag)

class NotANumber(ValueError):
    """Raised by parse_number; .text is the stripped offending text."""

def is_plain_number(text: str) -> bool:
    """re.fullmatch(config.NUMERIC_VALUE_RE, text.strip()) is not None. Blank -> False
    (callers test blank first)."""

def parse_number(text: str) -> Decimal | None:
    """None if text.strip() == ""; NotANumber if not is_plain_number(text); else Decimal(text.strip())."""

def multiply(*values: Decimal) -> Decimal:
    """Left-to-right ARITH_CONTEXT.multiply. Raises decimal.Inexact if an exact result would need
    more than ARITH_PRECISION digits (the caller converts that to a warning)."""

def format_number(value: Decimal) -> str:
    """Fixed notation, exact, no exponent, no trailing zeros (section 2.3)."""

def format_rounded(value: Decimal, quantum: str) -> str:
    """value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP, context=ROUNDING_CONTEXT), then
    format(q, "f") with trailing zeros KEPT ("2.00"); a negative zero ("-0.00") becomes "0.00"."""
```

The contexts are used **explicitly** (`ARITH_CONTEXT.multiply`, `quantize(..., context=...)`). The thread-local
global context (`decimal.getcontext()`) is never read or modified, because Streamlit runs sessions on worker threads.

### 1.4 `schema.py` — additions

```python
def normalize_header(name: str) -> str:
    """Remove every char in config.ZERO_WIDTH_CHARS, then normalize_column(). Used by all Phase 2
    header matching (P3 signature, upload headers, reserved names)."""

def find_phase2_output_headers(columns: Sequence[str]) -> list[str]:
    """Verbatim entries of `columns` whose normalize_header() equals the normalize_header() of any
    config.PHASE2_OUTPUT_SIGNATURE_HEADERS entry, in source order. [] means 'not Phase 2 output'."""

def column_letter(index: int) -> str:
    """0-based column index -> spreadsheet letters (0 -> 'A', 7 -> 'H', 26 -> 'AA'). For warning text."""
```

### 1.5 `file_reader.py` — addition (`read_table` unchanged)

```python
def read_raw_grid(filename: str, data: bytes) -> list[list[str]]:
    """Header-less read of .csv / .xlsx sheet config.EXCEL_SHEET_INDEX. Row 0 is the header row
    EXACTLY as typed (no pandas 'Unnamed: n' / '.1' mangling). Every cell str; missing -> "".
    All rows have equal length. Same FileReadError contract as read_table (EMPTY_FILE / UNREADABLE).
    Header text is NOT stripped here — the caller strips."""
```

Implementation: give the private helpers a `header: int | None = 0` parameter (Phase 1 call sites pass nothing).
CSV: `pd.read_csv(io.BytesIO(data), dtype=str, na_filter=False, encoding=<chain>, engine="c", header=header)`.
Excel: `pd.read_excel(io.BytesIO(data), sheet_name=config.EXCEL_SHEET_INDEX, dtype=str, header=header)`.
Then `df.fillna("").astype(str)` and return `df.to_numpy().tolist()`. `dtype=str` is present on both reads.

### 1.6 `master_detector.py` — changes

- `find_master_candidates`: after `build_column_index` succeeds, set
  `is_phase2_output = bool(find_phase2_output_headers(list(df.columns)))`. Still never raises.
- New private `_refuse_phase2_output(frame)`: if `find_phase2_output_headers(frame.columns)` is non-empty, raise
  `SchemaError(config.REASON_PHASE2_OUTPUT, config.MSG_PHASE2_OUTPUT)`. It is called immediately after `read_table` in
  **both** `build_master_context_from_existing` and `build_master_context_from_first_file`.
- New:
  ```python
  def first_master_slot_allowed(candidates: Sequence[MasterCandidate]) -> bool:
      """False if any candidate is_phase2_output. app.py consults this only when there are zero
      valid candidates: a Phase 2 output offered as the master keeps Run disabled until a proper
      master is supplied (P3), rather than silently falling through to the first-master slot."""
  ```

### 1.7 `study_processor.py` — changes

- `process_file` gains **step 3b**, between the existing steps 3 and 4:
  `3b. find_phase2_output_headers(df.columns) non-empty -> rejected, REASON_PHASE2_OUTPUT` (`missing_cols`/`extra_cols` stay `[]`).
  The docstring's fixed-order list is updated. The invariant "only step 4 populates missing/extra" still holds.
- New:
  ```python
  def is_run_ready(master: MasterContext | None, study_item_count: int) -> bool:
      """P4. False if master is None; True if study_item_count > 0; otherwise True only for an
      EXISTING master (not master.created_this_run). The first-master slot is unchanged."""
  ```
- `process_batch`: **no code change.** With zero study items the loop is empty, `outcomes == list(excluded_outcomes)`
  (sorted), `master_df = master.frame.copy()` reindexed, and all counts are 0. Stage 1 adds tests that pin this down.

### 1.8 `calculations.py` — NEW

```python
def build_calculations(master_df: pd.DataFrame, am_round_2dp: bool | None = None) -> CalculationResult:
    """Section 3. Never raises on data problems — every problem becomes blank cells + a warning.
    am_round_2dp None -> config.AM_ROUND_TO_2DP. master_df is never mutated."""
```

### 1.9 `template_builder.py` — NEW (the only application module importing `openpyxl`)

```python
def list_template_studies(master_df: pd.DataFrame) -> list[str]:
    """P5: distinct Study_Name values, VERBATIM (exact-string distinct), first-appearance order,
    values whose .strip() == "" excluded. Study_Name found via build_column_index."""

def build_template_bytes(study_names: Sequence[str]) -> bytes:
    """Section 6. Workbook built in memory; wb.save(io.BytesIO()); returns buffer.getvalue()."""
```

### 1.10 `metadata_upload.py` — NEW

```python
def parse_upload(filename: str, data: bytes, master_columns: Sequence[str]) -> ParsedUpload:
    """Section 7.1–7.3. Never raises. Refusals come back as accepted=False."""
```

### 1.11 `final_builder.py` — NEW

```python
def build_final(
    master_df: pd.DataFrame,
    calculations: CalculationResult,
    upload: ParsedUpload,
    value_check: bool | None = None,
) -> FinalResult:
    """Section 7.4. Precondition (raises ValueError — a programming error, not data): upload.accepted
    and len(calculations.frame) == len(master_df). value_check None -> config.VALUE_CHECK_ENABLED."""
```

### 1.12 `report.py` — additions

```python
def phase2_warnings_to_frame(warnings: Sequence[Phase2Warning]) -> pd.DataFrame:
    """Exactly config.PHASE2_WARNING_COLUMNS (Study, Model, Column, Issue), in order, one row per
    warning, dtype=object. Empty frame WITH those columns when there are none. `code` is not output."""

def summarize_phase2_warnings(result: FinalResult) -> str:
    """"" when no warnings; else config.MSG_WARNINGS_SUMMARY formatted with total/calc/upload."""
```

### 1.13 `csv_writer.py` — additions (same shape as `build_master_filename`)

```python
def build_template_filename(base_name: str, now: datetime | None = None) -> str   # TEMPLATE_FILENAME_PATTERN
def build_final_filename(base_name: str, now: datetime | None = None) -> str      # FINAL_FILENAME_PATTERN
def build_phase2_warnings_filename(base_name: str, now: datetime | None = None) -> str
```

`'Instacart'` + 2026-09-28 14:30 gives `studyname_master_Instacart_2026-09-28_1430.xlsx`,
`after_formulas_master_Instacart_2026-09-28_1430.csv` and `phase2_warnings_Instacart_2026-09-28_1430.csv`.

---

## 2. Precision contract — Phase 2 extension

Phase 1's contract (`ARCHITECTURE.md` section 5) is unchanged: every DataFrame cell is a `str`, and master columns
pass through byte-exact. Phase 2 adds exactly one kind of arithmetic: `Decimal` on **parsed copies** of cells from
three source columns. Nothing is ever written back into a master column.

### 2.1 Parsing an input cell

1. `s = cell.strip()`. If `s == ""`, the value is **blank**.
2. If `re.fullmatch(config.NUMERIC_VALUE_RE, s)` fails, the value is **not a number**. This rejects `abc`, `1,234`,
   `$3`, `25%`, `+5`, `NaN`, `Infinity`, `1_000`, `1.2.3`, non-ASCII digits, and `1E+1000`. Python's `Decimal()` would
   accept `NaN`, `Infinity`, `1_000`, leading `+` and Unicode digits, which is why the regex gates it.
3. Otherwise `Decimal(s)`. The constructor is exact and context-independent. E-notation is fine:
   `Decimal("1.2E+06") == Decimal("1200000")`.

The same regex is P17's template value check (section 7.4). One definition of "numeric" serves both.

### 2.2 Arithmetic

`numeric.multiply` uses `ARITH_CONTEXT` (100 significant digits, `Inexact` trapped). Input coefficients in this
data are at most 17 digits, so a triple product needs at most about 51 digits. Every product is therefore
**exact**: there is no rounding anywhere (P20). If an absurd input ever needed more than 100 digits, `Inexact` is
raised and caught, and the cell becomes blank with a `P2W_VALUE_TOO_PRECISE` warning. That fails loud instead of
silently rounding. The default 28-digit context is never used. A test proves this (section 10.4).

### 2.3 Formatting a result back to a string — the one rule

`format_number(d)`:

1. `s = format(d, "f")`. This is exact fixed-point with no exponent, whatever the `Decimal`'s internal exponent:
   `Decimal("2.4E+6")` gives `"2400000"` and `Decimal("1E-7")` gives `"0.0000001"`.
2. If `"." in s`: `s = s.rstrip("0").rstrip(".")`. This removes scale-only trailing zeros, which are representation,
   not value.
3. If `s == "-0"`: `s = "0"`.

This guarantees no scientific notation and no trailing noise, and every digit is significant.

**All seven calculated columns go through this formatter, including the four copy columns (AG, AI, AJ, AM).** The
value is identical to the source; only its representation is normalised. For example, the raw CSV's `12149247.0`
becomes `12149247` in AG. Master columns A–AF keep the original text byte-for-byte. See design default 2.

**AM with `AM_ROUND_TO_2DP = True`:** `format_rounded(d, "0.01")` with `ROUND_HALF_UP`. `Decimal`'s `ROUND_HALF_UP`
is half-away-from-zero, which is what Excel's `TEXT(N,"0.00")` does. It keeps two decimals (`2` becomes `"2.00"`,
`1.005` becomes `"1.01"`, `-0.001` becomes `"0.00"`). Note that `quantize` is used, never `.round()` or builtin `round()`.

### 2.4 Worked reference values (these become literal test assertions)

| Inputs (N × G) | Exact product | App output string |
|---|---|---|
| `0.036091684` × `12149247` (workbook / sample-master values) | 36091684 × 12149247 = 438486783561948, scale 10⁻⁹ | `438486.783561948` |
| `0.03609168443151368` × `12149247.0` (raw `Holly_Rancher 27382_Scored.csv`) | 438486.788804514282198960 | `438486.78880451428219896` |
| `0.5` × `1000` | 500.0 | `500` |
| `5E-1` × `1.0E+3` | 5.00E+2 | `500` |

The first row matters. The exact product has **exactly 15 significant digits**, so Excel's 15-digit value
`438486.783561948` *is* the exact product, and the app emits that identical string. The second row shows why
section 10.5 cannot rebuild the workbook's inputs from `Samples/`: the unrounded source value changes the
product in the 8th significant digit.

### 2.5 Banned-token compliance (`CLAUDE.md` rule 2)

The design needs none of `astype(float)`, `pd.to_numeric`, `.round()`, `np.float64`, `float_format=`, `converters=`,
`parse_dates=`, `thousands=`, `decimal=`. Every read keeps `dtype=str`. Additional rules for Phase 2 code:

- no builtin `float(` or `round(`
- import names explicitly (`from decimal import Decimal, Context, ...`) and never pass a keyword argument named `decimal`
- do not name an identifier ending in `decimal` (it could trip a naive `decimal=` text grep)
- construct every new DataFrame with `dtype=object`, so no numeric-dtype frame ever reaches a `pd.concat` with str
  frames (this matters for zero-row masters, where an empty list could otherwise infer a dtype)

The AST scan in section 10.1 enforces all of this.

---

## 3. Calculation algorithm and block matching (P20–P25)

### 3.1 Column resolution

`index = build_column_index(list(master_df.columns))`. For each of `DEPENDENT_VARIABLE_COL`, `CNT_EXPSD_HH_COL`,
`ADJ_MEAN_EXPSD_GRP_COL`, `MODEL_DESC_COL`, `MODEL_COL` and `STUDY_NAME_COL`, look up `normalize_column(config.X)`. The
verbatim master name is used when found, `None` when not. Matching is case- and whitespace-insensitive (Phase 1
decision 8), and never by letter.

Dependency map (a module constant in `calculations.py`, built from config names):

| Output header | Needs |
|---|---|
| Total Analyzed Population | F, G |
| Count of Circana Buyers | F, N, G, MODEL_DESC, Model |
| Partner Member Overlap % … | F, N |
| Dollars spent … by HH | F, N |
| Total Dollars spent … | F, N, G |
| Total Buying Trips … | F, N, G, MODEL_DESC, Model |
| Total Buying Trips per Buyer … | F, N |
| Total Offline Category New Buyers | — (always blank) |

For each missing source column, in the order F, G, N, MODEL_DESC, Model: emit **one** `P2W_SOURCE_COLUMN_MISSING`
(Study "", Model "", Column = the config name, `{headers}` = the dependent output headers joined with
`config.LIST_JOIN_SEPARATOR`). Every dependent cell stays blank. If F is missing, return an all-blank frame at this
point. Single-row columns never need MODEL_DESC or Model, so they still calculate when those two are missing.

### 3.2 Row roles

`role[i] = v.strip().casefold()` if it equals `pen`, `occ` or `dolhh`; otherwise `None`. So `Pen`, ` OCC ` and `DolHH`
all match, and `dolocc` or any unknown value gets `None`. Rows with `None` receive nothing and produce no warning.
Row identity is always the **position `i`** in `master_df`. Nothing depends on row order.

### 3.3 Single-row columns (computed per row, like Excel's per-row `IF`)

| role | column | value |
|---|---|---|
| dolhh | Total Analyzed Population | `fmt(G[i])` |
| dolhh | Dollars spent … by HH | `fmt(N[i])` |
| dolhh | Total Dollars spent … | `fmt(multiply(N[i], G[i]))` |
| pen | Partner Member Overlap % … | `fmt(N[i])` |
| occ | Total Buying Trips per Buyer … | `fmt(N[i])`, or `format_rounded` if AM rounding is on |

These are computed on **every** row with that role, including rows in broken blocks. That is what P23's "single-row
columns still calculate" means.

### 3.4 Block matching (P22/P23) — cross-row columns

Only when MODEL_DESC and Model both resolved:

1. `key[i] = (study[i].strip(), model_desc[i].strip(), model[i].strip())`. The comparison is exact after strip
   (design default 3). Group **all** rows by key into `dict[key, list[int]]` in first-appearance order.
2. Per block: `by_role = {pen: [...], occ: [...], dolhh: [...]}`.
   - `missing = [r for r in (pen, occ, dolhh) if len(by_role[r]) == 0]` gives **one** `P2W_BLOCK_ROLE_MISSING`, with
     `{roles}` like `'pen', 'occ'`.
   - `dup = [r ... if len > 1]` gives **one** `P2W_BLOCK_ROLE_DUPLICATED`, with `{roles}` like `'pen' (2 rows)`.
   - If either list is non-empty, **both** cross-row columns (Count of Circana Buyers, Total Buying Trips) stay blank
     for the whole block. This follows P23 literally: a missing `occ` also blanks Count of Circana Buyers (see C4).
     `{headers}` names both.
3. Clean block with `p, o, d` as the single row of each role:
   - `CountBuyers[p] = fmt(multiply(N[p], G[d]))`
   - `TotalTrips[p] = fmt(multiply(N[p], G[d], N[o]))`
   The operands are fetched through the same recorder as section 3.5, so every problem cell is recorded before the
   result is decided.

When MODEL_DESC or Model is missing, no blocks are formed. The two cross-row columns are covered by the single
`P2W_SOURCE_COLUMN_MISSING` warning.

### 3.5 Blank / unparseable input cells — DESIGN DEFAULT 1

A problem cell is recorded by `(row i, source column)` together with the set of output headers it blanked. A blank
`G` on a dolhh row blanks four headers and produces **one** warning:
- blank gives `P2W_VALUE_BLANK`
- not numeric gives `P2W_VALUE_NOT_NUMERIC` (`{value}` = the stripped text, truncated to 40 characters)

The warning fields are:
- Study = `study[i]` verbatim
- Model = block label
- Column = the verbatim master source column name
- `{role}` = `dep[i].strip()`
- `{row}` = `i + 2`, the spreadsheet row in the downloaded master

Cells that are **not needed** never warn. For example, `CNT_EXPSD_HH` is blank on every pen/occ row by design.
`decimal.Inexact` from `multiply` gives `P2W_VALUE_TOO_PRECISE`, with Column = the output header.

### 3.6 Warning emission order (deterministic)

1. `P2W_SOURCE_COLUMN_MISSING`, in the order F, G, N, MODEL_DESC, Model.
2. All other calculation warnings, stably sorted by `(anchor_row, kind_rank)`:
   - anchor = the block's first row for block warnings, and the cell's row for value/precision warnings
   - kind_rank: block = 0, value = 1, precision = 2

Block label = `BLOCK_LABEL_PATTERN.format(model_desc=md.strip(), model=m.strip())`, or `""` when either column is
missing.

### 3.7 Output

`pd.DataFrame(out, columns=list(config.CALCULATED_HEADERS), dtype=object)`, where `out[h]` is a `list[str]` of length
`len(master_df)`. The Offline column is all `""`. The frame has a RangeIndex and every cell is `str`. `master_df` is
untouched.

---

## 4. Output-as-input detection (P3)

**Rule:** a file is Phase 2 output iff `find_phase2_output_headers(its column headers)` is non-empty. That means at
least one header, after zero-width stripping and case/whitespace normalisation, equals one of: the 8 calculated
headers, Ravi's legacy "Instacart Member Overlap % with Circana Retailer", or the six merged template headers.
Including the merged headers follows P3's "calculated/merged columns" literally (design default 6).

| Path | Where | Behaviour |
|---|---|---|
| Study file | `process_file` step 3b (after the duplicate-columns check, before the column-mismatch check) | `rejected` / `REASON_PHASE2_OUTPUT`; the run continues. After Run, STEP 6 shows `st.warning(MSG_PHASE2_OUTPUT)` followed by the affected filenames. |
| `Master_*` candidate | `find_master_candidates` sets `is_phase2_output=True`, so `is_valid=False` | STEP 2 shows `st.warning(f"'{name}': " + MSG_PHASE2_OUTPUT)`. If **another** valid master exists, the flagged file falls into the study pool and is rejected by step 3b. If **no** valid master exists, `first_master_slot_allowed()` is False: STEP 2b is **not** rendered, `master` stays `None`, and Run stays disabled until a proper master is uploaded (design default 7). |
| Resume / first-master builders | `_refuse_phase2_output` | `SchemaError(REASON_PHASE2_OUTPUT, MSG_PHASE2_OUTPUT)`. `app._load_master` shows it and stops. This is the existing unloadable-master exception, and the second line of defence (for example, an `after_formulas_*.csv` picked in STEP 2b). |
| Studyname upload | `parse_upload` | An `after_formulas_master` carries all three `MASTER_LOOKALIKE_COLUMNS`, so it is refused with `MSG_UPLOAD_IS_MASTER` (section 7.1). |

Phase 1 behaviour is unchanged for every file without signature headers. The trap test still appends
`MaserFile_XXXX_DATE.csv`, and all existing fixtures keep their reasons.

---

## 5. Master-only Run (P4)

- `app.py` STEP 5: `ready = is_run_ready(master, len(study_items))`, replacing `master is not None and len(study_items) > 0`.
- STEP 4, when `study_items` is empty: if `master.created_this_run`, keep the existing message ("No study files left
  to review — everything uploaded is the master."). Otherwise `st.info(config.MSG_MASTER_ONLY_RUN)`.
- The not-ready reasons text is unchanged. "At least one study file must be available" can now only appear on the
  first-master path.
- `process_batch` with zero study items gives 0 appended, `outcomes` = the excluded outcomes only (for example an
  unselected second master), `master_df` equal cell-for-cell to `master.frame`, and `total_records = len(master.frame)`.
  STEP 6 renders normally and Phase 2 unlocks.

---

## 6. Template workbook (`template_builder.build_template_bytes`)

**Sheet 1**, `TEMPLATE_SHEET_TITLE`, created first so it is sheet index 0 (P10 reads sheet 1):

1. `A1:G1` = `TEMPLATE_HEADERS`, `Font(bold=True)`. `ws.freeze_panes = "A2"`.
2. `A2:A{n+1}` = study names. After assigning each value, set `cell.data_type = "s"`. Without that, openpyxl would
   store a name starting with `=` as a formula, and `00123` must stay text. Any character matched by openpyxl's
   `ILLEGAL_CHARACTERS_RE` is removed from the written value. Such a study would then fail to match at merge time and
   surface as a warning pair (edge case P2-29).
3. `B1:G{n+1}` are materialised, empty except for the headers, each with `Protection(locked=False)`.
   `D2:D{n+1}` also get `number_format = PCT_NUMBER_FORMAT`. Column A cells keep the default `locked=True`.
4. Column dimensions, so cells typed later anywhere in B onward, including H+ headers and values, are unlocked:
   - `A`: width `TEMPLATE_STUDY_COL_WIDTH` (locked)
   - `B` with `min=2, max=3`: width `TEMPLATE_VALUE_COL_WIDTH`, `Protection(locked=False)`
   - `D` with `min=4, max=4`: same, plus `number_format = PCT_NUMBER_FORMAT`
   - `E` with `min=5, max=XLSX_MAX_COLUMN`: same width, `Protection(locked=False)`
5. `ws.protection.sheet = True`. **No password**: never call `set_password` or assign `.password`.
   `ws.protection.formatColumns = False`, so users may widen columns (design default 18). Every other flag stays at
   openpyxl's default.

**Sheet 2**, `GLOSSARY_SHEET_TITLE` (not protected):

| Rows | Content |
|---|---|
| 1 | `GLOSSARY_FIELDS_TITLE` (bold) |
| 2 | `GLOSSARY_FIELD_COLUMNS` (bold) |
| 3 – 9 | `GLOSSARY_FIELD_ROWS`, every cell `data_type="s"` so `25%` and `3.49` stay text |
| 10 | blank |
| 11 – 12 | `GLOSSARY_EXTRAS_TITLE` (bold), then `GLOSSARY_EXTRAS_TEXT` |
| 13 | blank |
| 14 | `GLOSSARY_RULES_TITLE` (bold) |
| 15 – 18 | `"- " + rule` for each of `GLOSSARY_RULES` |

Widths A 18, B 28, C 80 (wrap text), D 20. Calculated-column entries are **not** written here (P31: on screen only).

Save: `buf = io.BytesIO(); wb.save(buf); return buf.getvalue()`. There are no filesystem writes.

---

## 7. Upload validation and merge

### 7.1 `parse_upload` — fixed order of checks

1. `grid = read_raw_grid(filename, data)`. A `FileReadError` is **refused** with
   `MSG_UPLOAD_UNREADABLE.format(detail=e.detail or e.reason)`. An empty grid is **refused** with `MSG_WRONG_FILE`.
2. `headers = [h.strip() for h in grid[0]]` and `body = grid[1:]`.
3. Study_Name columns = the positions where `normalize_header(h) == normalize_header(STUDY_NAME_COL)`. None found is
   **refused** with `MSG_WRONG_FILE` (P11). More than one: the leftmost is used, and each other one gets
   `P2W_UPLOAD_SECOND_STUDY_NAME` and is ignored (design default 10).
4. If every one of `MASTER_LOOKALIKE_COLUMNS` (normalised) is among the headers, **refuse** with
   `MSG_UPLOAD_IS_MASTER` (P11, design default 8). This is the only P11 halt besides step 3. Phase 1 results stay on
   screen.
5. Classify every other column position, left to right (7.2).
6. Build the rows (7.3).
7. Return `accepted=True`. `merge_columns = list(TEMPLATE_VALUE_HEADERS) + [accepted extras]`.

### 7.2 Header classification

For each position `j` (other than the chosen Study_Name column):

| Condition (first match wins) | Result |
|---|---|
| header `""` | Ignored. If any `body[r][j].strip()` is non-empty, `P2W_UPLOAD_BLANK_HEADER` (Column ""). |
| `normalize_header(h)` equals a fixed value header | A fixed-header occurrence (matched by **name at any position**) |
| `j >= EXTRAS_START_COL_INDEX` (H onward) | An extra candidate |
| otherwise (an unknown header in B–G) | Ignored, `P2W_UPLOAD_UNEXPECTED_COLUMN` (design default 11) |

Fixed headers, in config order:
- exactly one occurrence: the column is used, and the header is added to `present_fixed`
- zero occurrences: `P2W_UPLOAD_FIXED_MISSING` (P15), and the column is blank in the final file
- two or more: `P2W_UPLOAD_FIXED_DUPLICATED`, all occurrences ignored, blank (design default 12)

Extras are grouped by `normalize_header`, in first-appearance order. The reserved set is the normalised names of
every master column, every `CALCULATED_HEADERS` entry, `LEGACY_CALCULATED_HEADERS` and `TEMPLATE_HEADERS`
(design default 13).
- Reserved name: `P2W_UPLOAD_EXTRA_RESERVED`, all occurrences ignored.
- Otherwise more than one occurrence: `P2W_UPLOAD_EXTRA_DUPLICATED`, all ignored.
- Otherwise accepted. The output header is the upload header verbatim (stripped). If `len(header) > EXTRA_HEADER_MAX_LEN`,
  `P2W_UPLOAD_EXTRA_TOO_LONG`, **still merged** (P14).

### 7.3 Rows

For body row `r` (spreadsheet row `r + 2`): `name = row[study_pos]`, and `values = {col: row[pos]}` for present fixed
headers and accepted extras. Every other merge column is `""`. Values are **verbatim**, never stripped or altered.
- If `name.strip() == ""`: when any value is non-blank, `P2W_UPLOAD_ROW_NO_STUDY`; otherwise the row is ignored
  silently (design default 14).
- Otherwise append `UploadRow` under `key = name.strip().casefold()` (P12).

### 7.4 `build_final` — matching, value check, merge

1. The Study_Name column is resolved via `build_column_index(master_df.columns)`.
   Row key = `study.strip().casefold()`. Master keys are taken in first-appearance order, with the display name =
   the first verbatim value. If any master rows have a blank study name, one `P2W_MASTER_BLANK_STUDY`
   (design default 14).
2. `matched = master_keys ∩ upload keys`. `zero_match = not matched`, which includes an upload with zero named rows.
   `upload_study_count = len(upload.rows_by_study)`. If `zero_match`, `P2W_UPLOAD_ZERO_MATCH` goes first among the
   upload warnings, and app.py also shows `MSG_ZERO_MATCH` (P11).
3. For each master key, in order, take the **filled** rows = its UploadRows with at least one non-blank value
   (design default 15):
   - there are no rows at all: `P2W_STUDY_NOT_IN_UPLOAD` (P13)
   - rows exist but none is filled: "not filled in yet", merged blank, **no** warning (P13)
   - exactly one filled row: merge its values. If value checking is on, then for each header in
     `NUMERIC_CHECKED_HEADERS ∩ present_fixed` whose value is non-blank and `not is_plain_number(value)`, emit
     `P2W_VALUE_NOT_PLAIN_NUMBER`. The value is still merged as typed (P16). Only merged values are checked
     (design default 16). `Read_Type` and extras are never checked.
   - two or more filled rows: `P2W_STUDY_DUPLICATED`, merged blank (P13)
4. For each upload key not in the master, in upload order: `P2W_STUDY_NOT_IN_MASTER` (Study = first verbatim upload
   name, `{rows}` = all row numbers). The rows are ignored.
5. `merged = pd.DataFrame({col: [values_by_key.get(row_key, {}).get(col, "") for row_key in master_row_keys] for col in merge_columns}, columns=merge_columns, dtype=object)`.
   Values repeat on every row of the study (P27).
6. `final = pd.concat([master_df.reset_index(drop=True), calculations.frame, merged], axis=1)`.
   Assert (raising `RuntimeError`, fail loud):
   - columns == master columns + `CALCULATED_HEADERS` + `merge_columns`
   - all column names unique
   - `len(final) == len(master_df)`
   Study_Name is not repeated (P26).
7. `warnings = calculations.warnings + [ZERO_MATCH?] + upload.warnings + [MASTER_BLANK_STUDY?] + per-master-study warnings + not-in-master warnings`.

**The P17 regex** is `-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?`, used with `re.fullmatch` on
`value.strip()`.
- Accepts: `3.49`, `-2`, `1500000`, `1.2E+06`, `0.25`, `.5`, `5.`, `1e-07`, ` 3.49 `
- Warns: `1,500`, `$3.49`, `25%`, `abc`, `+5`, `1.2.3`, `3,49`, `NaN`, `inf`, `1 000`
- Blank is fine.

**P18:** a value typed as `25%` into the percent-formatted xlsx cell is stored by Excel as the number 0.25, and
`read_raw_grid` (pandas `dtype=str`) yields the string `"0.25"`. A `25%` in a CSV upload is text: it is warned and
merged as `25%` (see C5).

### 7.5 Warning catalogue

| Code | Study | Model | Column | Placeholders |
|---|---|---|---|---|
| source_column_missing | "" | "" | config source name | headers |
| block_role_missing / _duplicated | block study | block label | master `dependent_variable` name | roles, headers |
| value_blank / value_not_numeric | row study | block label | master source column | role, row, value, headers |
| value_too_precise | row study | block label | output header | prec, row, headers |
| upload_zero_match | "" | "" | `Study_Name` | n |
| upload_second_study_name | "" | "" | that header | letter, first_letter |
| upload_blank_header | "" | "" | "" | letter |
| upload_unexpected_column | "" | "" | that header | letter |
| upload_fixed_missing / _duplicated | "" | "" | fixed header | count, letters |
| upload_extra_reserved / _duplicated / _too_long | "" | "" | extra header | letters, count, length |
| upload_row_no_study | "" | "" | `Study_Name` | row |
| master_blank_study | "" | "" | `Study_Name` | count |
| study_not_in_upload / study_duplicated | master display name | "" | `Study_Name` | count, rows |
| study_not_in_master | upload display name | "" | `Study_Name` | rows |
| value_not_plain_number | master display name | "" | fixed header | value |

Lists (`headers`, `letters`, `rows`) are joined with `config.LIST_JOIN_SEPARATOR`.

---

## 8. `app.py` — STEPs 7–9 and session state (Stage 5)

### 8.1 Run block additions (inside `if st.button("Run", ...)`, after the existing writes, same `now`)

```
calc = build_calculations(result.master_df)
studies = list_template_studies(result.master_df)
st.session_state["p2_calc"] = calc
st.session_state["p2_base_name"] = master.base_name
st.session_state["p2_template_bytes"] = build_template_bytes(studies)
st.session_state["p2_template_filename"] = build_template_filename(master.base_name, now)
st.session_state["p2_template_study_count"] = len(studies)
```

### 8.2 Session-state contract

| Key | Written | Read | Why |
|---|---|---|---|
| `result`, `master_bytes`, `exception_bytes`, `master_filename`, `exception_filename` | Run (Phase 1, unchanged) | STEP 6 | Survive download/upload reruns |
| `p2_calc`, `p2_base_name`, `p2_template_*` | Run only, all together | STEPs 7–9 | Depend only on the master, which changes only on Run |
| `p2_upload` (widget key) | Streamlit | STEP 8 | Keeps the uploaded template across reruns and across a new Run |
| *(not stored)* `ParsedUpload`, `FinalResult`, final bytes, warnings bytes and their filenames | — | recomputed on **every** rerun | P29: always derived from the current master and the current upload |

"Current master" is `st.session_state["result"].master_df`, the last Run's updated master. It is the same object
STEP 6 renders. Caching the calculations at Run is still "always derived", because they are a pure function of that
frame and are rebuilt whenever Run rebuilds it. When Run is pressed with a template already uploaded, the Run block
executes before STEP 9 in the same script run, so the final file is rebuilt from the new master and the retained
upload with no extra action (P29). Recomputing the merge each rerun costs a few milliseconds at 8,000 rows.

### 8.3 Render flow (after STEP 6, guarded by `result is not None and "p2_calc" in st.session_state`)

```
st.header("Phase 2 · Study metadata & calculations")

STEP 7  st.subheader("STEP 7 — Download template")
        st.info(MSG_TEMPLATE.format(n=p2_template_study_count))
        col1: st.download_button("Download studyname_master", p2_template_bytes,
                                 p2_template_filename, mime=XLSX_MIME, key="dl_template")
        col2: st.expander("Glossary"): fields table (GLOSSARY_FIELD_ROWS / _COLUMNS), extras text,
              rules list, then GLOSSARY_CALC_BLOCK_NOTE + calculated table (GLOSSARY_CALC_ROWS)

STEP 8  st.subheader("STEP 8 — Upload completed template (.xlsx or .csv)")
        up = st.file_uploader(..., type=["xlsx", "csv"], accept_multiple_files=False, key="p2_upload")
        if up is None: st.caption(MSG_UPLOAD_PROMPT); (nothing further)
        parsed = parse_upload(up.name, up.getvalue(), list(result.master_df.columns))
        if not parsed.accepted: st.error(parsed.refusal_message); (nothing further)

STEP 9  final = build_final(result.master_df, p2_calc, parsed); now9 = datetime.now()
        st.subheader("STEP 9 — Final file")
        st.info(MSG_COLUMN_MATCHING)                                   # always (P24)
        if final.zero_match: st.warning(MSG_ZERO_MATCH.format(n=final.upload_study_count))
        if final.warnings:
            st.warning(summarize_phase2_warnings(final))
            with st.expander("Details"): st.dataframe(phase2_warnings_to_frame(final.warnings), hide_index=True)
        else:
            st.success(MSG_NO_ISSUES)
        st.dataframe(final.frame.head(20)); st.caption("Showing 20 of N rows …")
        st.download_button("Download after_formulas_master", to_csv_bytes(final.frame),
                           build_final_filename(p2_base_name, now9), mime=CSV_MIME, key="dl_final")
        if final.warnings:
            st.download_button("Download phase2_warnings",
                               to_csv_bytes(phase2_warnings_to_frame(final.warnings)),
                               build_phase2_warnings_filename(p2_base_name, now9), mime=CSV_MIME,
                               key="dl_p2_warnings")
```

Stage 1 `app.py` diffs (STEP 2 P3 branch, STEP 2b gate, STEP 4 message, STEP 5 `is_run_ready`, STEP 6 P3 notice) are
specified in sections 4 and 5. The banner docstring gains STEPs 7–9 and the new modules.

---

## 9. Edge cases — Phase 2

| # | Situation | Behaviour |
|---|---|---|
| P2-1 | Existing master only, no studies | Run enabled; `MSG_MASTER_ONLY_RUN`; 0 appended; master unchanged; Phase 2 unlocks. |
| P2-2 | Single file, zero candidates (first-master path) | Run stays disabled (unchanged). |
| P2-3 | Two valid masters, no studies | Pick one. The loser is `skipped` / `not selected as master`. Run enabled. |
| P2-4 | `Master_*` with calculated/merged headers, no other valid master | Not valid; P3 warning; STEP 2b suppressed; Run disabled. |
| P2-5 | Same, alongside a proper master | Proper master used; the flagged file is rejected with `REASON_PHASE2_OUTPUT` as a study. |
| P2-6 | `after_formulas_*.csv` in the batch | Study path: rejected, P3 reason. Picked in STEP 2b: `SchemaError`, and `_load_master` halts with the P3 message. |
| P2-7 | Signature headers with trailing `\u200b`, or the legacy "Instacart Member …" | Still detected (`normalize_header`). |
| P2-8 | Master with zero data rows | Template lists 0 studies; calculation frame has 0 rows; final file is header-only. |
| P2-9 | Master Study_Name values differing only by case/space | Both appear in the template (verbatim-distinct). Upload rows collide under P12, so `study_duplicated`, blank. |
| P2-10 | Blank Study_Name rows in master | Excluded from the template; merged columns blank; one `master_blank_study`; calculations still run (block study key ""). |
| P2-11 | Blocks not 4 rows, out of order, or interleaved | Key matching; results identical to sorted input (shuffle test). |
| P2-12 | `Pen`, ` OCC `, `DolHH` | Matched (strip + casefold). |
| P2-13 | Missing role in a block | Both cross-row columns blank for the block; single-row columns still computed; one `block_role_missing`. |
| P2-14 | Duplicated role | Same blanking; each duplicate row keeps its own single-row values; one `block_role_duplicated`. |
| P2-15 | Block of only `dolocc` / unknown roles | One `block_role_missing` naming all three roles. |
| P2-16 | Source column missing from master | Dependent columns blank everywhere; one warning; merge unaffected. |
| P2-17 | Source column in a different case (`cnt_expsd_hh`) | Found by normalised lookup. |
| P2-18 | Needed input blank / non-numeric | Blank output + one warning per cell, listing every column it blanked. Unneeded blanks are silent. |
| P2-19 | E-notation input | Parsed exactly; output in fixed notation. |
| P2-20 | Result would exceed 100 significant digits | Blank + `value_too_precise`. Never rounded. |
| P2-21 | Upload unreadable or zero-byte | Refused (`MSG_UPLOAD_UNREADABLE`); Phase 1 results intact. |
| P2-22 | Upload without Study_Name (a study file, the exception report, the warnings CSV) | Refused (`MSG_WRONG_FILE`). |
| P2-23 | Upload is the master, or an `after_formulas_master` | Refused (`MSG_UPLOAD_IS_MASTER`). |
| P2-24 | Study_Name present, zero matches | Accepted; strong warning; final file carries calculations only. |
| P2-25 | Blank template uploaded as downloaded | Accepted; no upload warnings; calculations-only final file (P28). |
| P2-26 | Two Study_Name columns | Leftmost used; warning for the other. |
| P2-27 | Fixed header renamed in B–G (e.g. `Avg Price`) | `upload_fixed_missing` for the fixed one, plus `upload_unexpected_column` for the renamed one. |
| P2-28 | Fixed column moved to H+, or fixed column duplicated | Moved: matched by name. Duplicated: all copies ignored, blank + warning. |
| P2-29 | Master study name with XML-illegal control characters | Stripped in the template, so the names differ and `study_not_in_upload` + `study_not_in_master` fire (loud, not silent). |
| P2-30 | CSV upload with `25%` / `$3.49` / `1,500` | Warned, merged as typed. |
| P2-31 | Phase 1 uploads cleared after Run | `st.stop()` at STEP 1 hides Phase 1 and Phase 2 (existing behaviour); the Phase 2 upload widget state is dropped. Re-upload and Run again. |
| P2-32 | Phase 1 uploads changed, Run not pressed | Phase 2 keeps using the last Run's master (consistent with STEP 6). |
| P2-33 | Download click (any of the 5 buttons) | Rerun; final file recomputed deterministically; Phase 1 and the template unchanged. |
| P2-34 | Base name empty (`master_.csv`) | Phase 2 filenames become `studyname_master__<ts>.xlsx` and similar. The existing STEP 3 warning already covers this. |

---

## 10. Test plan — `test_meta_pipeline.py`

Existing sections 1–9 are unchanged except for **one** replaced check (10.1). New sections are appended before the
Summary; each is added in its own stage. The Summary line gains ` | {_skipped} skipped`. Skipped checks are never
counted as passed or failed.

### 10.1 Section 1 amendment + Section 10 "Rule scans" (Stage 1 — guards every later stage)

- **Replace** the config check at lines 93–100 with:
  - (a) the set of `REFERENCE_STUDY_COLUMNS` names equal (exact string) to any config value (scalars, and elements of
    sequences, including nested) is exactly `{MODEL_DESC, Model, dependent_variable, CNT_EXPSD_HH, ADJ_MEAN_EXPSD_GRP}`
  - (b) no single config sequence contains more than 3 reference names
- **Rule 4 literal scan (AST):**
  - Scan every `code/*.py` except `config.py` and `test_meta_pipeline.py`.
  - Collect every `ast.Constant` str, excluding bare string statements (`ast.Expr` whose value is a Constant: this
    covers docstrings). Comments are not in the AST.
  - FAIL on any constant that equals, **exactly** (case-sensitive), a name in `REFERENCE_STUDY_COLUMNS` ∪
    `{STUDY_NAME_COL}` ∪ `TEMPLATE_HEADERS` ∪ `CALCULATED_HEADERS` ∪ `LEGACY_CALCULATED_HEADERS`.
  - Exact matching is deliberate: `report.py` legitimately uses the literal `"study_name"` as an outcomes-table key.
  - Non-vacuity check: the same scan run on `config.py` finds at least 5 hits.
- **Rule 2 banned-construct scan (AST), on every `code/*.py` including the test file.** FAIL on:
  - an Attribute `to_numeric`, `float64` or `round` used as a call (`.round(`)
  - a Name call to `float` or `round`
  - an `astype(...)` whose argument is `float` or a string starting with `float`
  - any keyword `float_format`, `converters`, `parse_dates`, `thousands` or `decimal`
  - any `read_csv`/`read_excel` call lacking the keyword `dtype=str` (`ast.Name` with id `str`)
  - Non-vacuity check: a small in-memory source string containing each banned form yields one hit each.
- **Rule 3 no-write scan (AST), excluding the test file.** FAIL on:
  - a Name call to `open`
  - an Attribute call to `write_text`, `write_bytes`, `to_excel`, `mkdir` or `makedirs`
  - a `to_csv` call with any positional argument or a `path_or_buf` keyword
  - a `.save(` call whose first argument is not an `ast.Name`
- `openpyxl` is imported only by `template_builder.py` (and the test file).
- The streamlit scan (section 9) is unchanged and covers the new modules automatically.

### 10.2 Section 11 "Stage 1 — master-only Run and P3 detection"

- `is_run_ready` truth table: (None, 0) is False; (None, 3) False; (existing, 0) True; (existing, 2) True;
  (first-master, 0) False; (first-master, 1) True.
- `process_batch([master_item], existing_ctx, {})` returns appended 0, `outcomes == []`, `total_records == 52`, and a
  `master_df` equal cell-for-cell to the source master frame.
- The same call with an unselected-master `excluded_outcome` returns `outcomes == [that outcome]`, skipped 1.
- `find_phase2_output_headers` returns:
  - `[]` on the real master and on every study sample
  - hits on the calculated headers (plain, with `\u200b` suffix, different case)
  - hits on the legacy Instacart header and on `Read_Type`
- Synthetic `Master_File_Test_2026-09-28_1200.csv`, built in memory = real master + calculated headers:
  - `find_master_candidates` gives `is_phase2_output True`, `is_valid False`, readable True
  - `build_master_context_from_existing` raises `SchemaError`, with `.reason == REASON_PHASE2_OUTPUT` and
    `str(e) == MSG_PHASE2_OUTPUT`
  - `build_master_context_from_first_file` raises the same
  - `first_master_slot_allowed` is False for it and True for ordinary candidates
- `process_file` on those bytes as a study gives `rejected` / `REASON_PHASE2_OUTPUT` with `missing_cols == extra_cols == []`.
- **Order tests:**
  - calculated headers plus a duplicate column give `duplicate columns` (step 3 before 3b)
  - calculated headers plus a missing column give the P3 reason (3b before 4)
- **Regression:** every existing Phase 1 fixture keeps its status and reason. Asserted by the untouched
  sections 4–9 passing.

### 10.3 Section 12 "Stage 2 — template"

- `list_template_studies` on names `["B","A","B"," A","","  ","a","=SUM(1)","00123"]` returns
  `["B","A"," A","a","=SUM(1)","00123"]`.
- Real sample master: `["Holly_Rancher 27382_Scored"]`. The full-batch master from section 6 lists 10 names in
  first-appearance order.
- `build_template_bytes` returns bytes starting with `b"PK"`. Reloaded with `openpyxl.load_workbook(BytesIO)` in the
  test:
  - `sheetnames == [TEMPLATE_SHEET_TITLE, GLOSSARY_SHEET_TITLE]`
  - row 1 == `TEMPLATE_HEADERS` and is bold
  - A2.. are the names verbatim with `data_type == "s"` (`=SUM(1)` and `00123` stay strings)
  - B–G body cells are empty
  - `protection.sheet is True`, `protection.password` is falsy
  - A cells locked; `B1:G{n+1}` unlocked
  - column dimensions `E` have `min == 5`, `max == 16384`, `protection.locked is False`; `D` has the percent format
  - `freeze_panes == "A2"`
  - glossary cells equal the config text
- Round trips:
  - `read_table("t.xlsx", bytes)` gives columns == `list(TEMPLATE_HEADERS)` and verbatim names
  - `read_raw_grid` gives the same header row
  - `parse_upload(template)` is accepted with 0 warnings
- `build_template_filename("Instacart", fixed_now)` gives the exact expected string.

### 10.4 Section 13a "Stage 3 — calculations, layer 1 (synthetic, always runs, no client data)"

Uses a helper that builds a small all-str master (config column names, plus a row-id column `RowId`, plus
`Study_Name`) and an independent **integer-arithmetic oracle** `_exact_product_str(*texts)`. The oracle splits each
decimal string into (int coefficient, scale), multiplies the ints, places the point and strips zeros. It does not use
`Decimal`, so it is not circular.

- `numeric` units:
  - `format_number`: `500.0`→`500`, `2.4E+6`→`2400000`, `1E-7`→`0.0000001`, `-0.0`→`0`, `0.000100`→`0.0001`,
    `438486.7835619480`→`438486.783561948`
  - `parse_number`: `" 1.5 "` parses; `""` and `"  "` give None; every item in the section 7.4 warn list raises
    `NotANumber`
  - `format_rounded`: `1.945`→`1.95`, `2`→`2.00`, `-0.001`→`0.00`, `1.005`→`1.01`
- **Clean block** (pen N=0.5; occ N=2; dolocc N=9; dolhh N=3.25, G=1000). Expected:
  - Total Analyzed Population = `1000` on dolhh
  - Count of Circana Buyers = `500` on pen
  - Partner Member Overlap = `0.5` on pen
  - Dollars … by HH = `3.25` on dolhh
  - Total Dollars = `3250` on dolhh
  - Total Buying Trips = `1000` on pen
  - Trips per Buyer = `2` on occ
  - Offline column blank on every row; the dolocc row fully blank
  - frame columns == `CALCULATED_HEADERS`; length == master length; every cell str; no warnings
- **Casing:** `Pen`, ` OCC `, `DolHH` give identical output.
- **Shuffle:** two interleaved blocks in scrambled order produce identical values mapped back by `RowId`.
- **Broken blocks:**
  - missing occ: both cross-row columns blank for that block; single-row columns present; one
    `block_role_missing` with the correct study/model/column
  - duplicated pen: both pen rows get their own Partner Member Overlap; cross-row columns blank; one
    `block_role_duplicated`
  - dolocc-only block: one warning naming all three roles
- **Missing source columns:**
  - drop `CNT_EXPSD_HH`: 4 dependent columns blank everywhere, 3 computed, exactly one `source_column_missing` with
    Column `CNT_EXPSD_HH`
  - drop `dependent_variable`: everything blank, one warning
  - drop `Model`: cross-row columns blank, single-row columns computed, one warning
  - rename to `cnt_expsd_hh`: still found
- **Problem cells:**
  - blank G on dolhh: 4 columns blank, **one** `value_blank` listing them, `{row}` correct
  - `abc` in N on pen: `value_not_numeric`
  - blank G on the pen row: **no** warning
- **Exactness (literal strings):**
  - `0.036091684`×`12149247` gives `438486.783561948`
  - `0.03609168443151368`×`12149247.0` gives `438486.78880451428219896`
  - `5E-1`×`1.0E+3` gives `500`
  - Total Analyzed Population from `12149247.0` gives `12149247`
  - Partner Member Overlap from `0.03609168443151368` is unchanged
  - Triple product `0.03609168443151368 × 12149247.0 × 1.9454682413648197` equals `_exact_product_str(...)` and
    **differs** from the same product under a 28-digit context (proves the default context is not used)
- **AM flag:** default gives full precision; `am_round_2dp=True` gives `1.9454682413648197`→`1.95`, `2`→`2.00`.
- **Hygiene:** `decimal.getcontext().prec == 28` after every call (global context untouched); `master_df` equals a
  pre-call deep copy.
- **Real-sample anchor (uses `Samples/`, reported separately from layer 1):** on
  `Master_Instacart_2026-09-07_1200.csv`, Count of Circana Buyers on row index 0 is `"438486.783561948"`, and there
  are zero calculation warnings.

### 10.5 Section 13b "Stage 3 — layer 2, reference-workbook comparison"

**Input decision: use the workbook's own A–AF values as the master, not a rebuild from `Samples/`.** The workbook's
inputs were Excel-rounded before Excel computed its cached results: its AH2 is `0.036091684 × 12149247`. Rebuilding
from the source CSVs would feed `0.03609168443151368` and give `438486.78880451428219896`, which disagrees at the
8th significant digit. That would fail a correct app. The comparison must test the app's arithmetic on the exact
inputs Excel used. This departs from `PHASE2_BRIEF` section 8's "rebuild … from the same 3 sample studies" wording
(see C1). A structural cross-check against `Samples/` is kept, so the workbook is still tied to the three studies.

If `ROOT / "Phase 2 process" / "master_file_w_calculations.xlsx"` is absent: print
`[SKIPPED] SKIPPED — reference workbook not found: <path>` and increment `_skipped`. No `check()` is called.

Otherwise:

1. `wb = pd.read_excel(BytesIO(bytes), sheet_name="MaserFile_from STEP4 (2)", dtype=str).fillna("")`. pandas loads
   cached values (openpyxl `data_only=True`). Also `openpyxl.load_workbook(BytesIO(bytes), data_only=True)` for cell
   types.
2. Checks:
   - 212 rows
   - the first 32 stripped headers == `REFERENCE_STUDY_COLUMNS + [Study_Name]`
   - headers at positions 32–38, under `normalize_header`, equal the first 7 `CALCULATED_HEADERS` (the legacy
     Instacart name accepted at position 34)
   - per-study row counts in first-appearance order == `[52, 80, 80]`
3. Build the master realistically:
   - `to_csv_bytes(wb.iloc[:, :32])` → `UploadedItem(0, "Master_Reference_2026-09-28_0000.csv", ...)` →
     `build_master_context_from_existing` → `process_batch([item], ctx, {})`, which also exercises P4
   - `calc = build_calculations(res.master_df)`
   - check: zero calculation warnings
4. **Columns AG–AL (6):** on all 212 rows.
   - Excel blank ↔ app blank.
   - Excel non-blank: parse both with `Decimal`. The Excel string may be float-repr E-notation; the test parses it.
     Pass iff `|app − excel| ≤ 10^(excel.adjusted() − 14)`, i.e. agreement within one unit in the 15th significant
     digit. Compute with a local `Context(prec=100)`.
   - Non-blank count per column == 53.
5. **AM:** Excel blank ↔ app blank. Otherwise `format_rounded(Decimal(app), "0.01") == excel.strip()`. Also,
   `build_calculations(master, am_round_2dp=True)` AM must equal the Excel text exactly. The Offline column is blank
   on all rows.
6. **Text-stored inputs.**
   - Via openpyxl, count `ADJ_MEAN_EXPSD_GRP` cells with `data_type == "s"` and print the count.
   - If a product-column cell fails step 4 **and** one of its inputs is a text cell with more than 15 significant
     digits, re-test it against the product of those inputs reduced to 15 significant digits. Try both
     `ROUND_DOWN` and `ROUND_HALF_EVEN`, because Excel's text-to-number coercion keeps 15 digits.
   - Report such cells as `[EXCEL TEXT-COERCION] k cells` so QC sees them. Any other mismatch fails.
7. **Shuffled rerun:** `perm = list(range(212)); random.Random(20260928).shuffle(perm)`, then `build_calculations`
   on `res.master_df.iloc[perm].reset_index(drop=True)`. Un-permute; all 8 columns must be **string-identical** to
   the unshuffled output, and the warnings must be identical.
8. **Structural cross-check vs `Samples/`:**
   - Concatenate `Holly_Rancher 27382_Scored.csv`, `Instacart_Cascade_scored.csv` and `Instacart_Bel Brands_scored.csv`
     in that order (declared in the test).
   - The `(MODEL_DESC, Model, dependent_variable)` sequence must equal the workbook's 212-row sequence.
   - Informational print: the number of N/G cells whose `Decimal` differs between workbook and source (this documents
     the rounding that justifies the input decision).
9. Print `LAYER 2 RAN — 212 rows, 7 columns, <k> non-blank cells compared`. **QC sign-off on Stage 3 requires this line.**

### 10.6 Section 14 "Stage 4 — upload validation, merge, warnings"

Uploads are built in memory: CSV via `csv.writer`, xlsx via `build_template_bytes` then edited with openpyxl in the
test. Nothing is written to disk.

- `read_raw_grid`:
  - CSV `Study_Name,Brand,Brand,` keeps `Brand`, `Brand`, `""` unmangled
  - xlsx with an empty H1 but a value in H2 gives `""` at index 7
  - zero-byte input raises `FileReadError(EMPTY_FILE)`
- **Refusals** (`accepted is False`, exact message):
  - no Study_Name: `MSG_WRONG_FILE`
  - real master CSV: `MSG_UPLOAD_IS_MASTER`
  - synthetic after_formulas: `MSG_UPLOAD_IS_MASTER`
  - garbage bytes: `MSG_UPLOAD_UNREADABLE` prefix
  - zero-byte: unreadable
  - header-only CSV without Study_Name: wrong file
- **P12:** ` instacart_cascade ` matches `Instacart_Cascade`.
- **P13 matrix:**
  - not in upload: blank + `study_not_in_upload`
  - upload-only study: `study_not_in_master`
  - two filled rows: blank + `study_duplicated` with row numbers
  - one filled row + one blank row: merged, no warning
  - named all-blank row: blank, **no** warning
- **P14:**
  - extras at H/I merged after the fixed six in upload order
  - blank header with values: warning; blank header without values: silent
  - 16-character header: `upload_extra_too_long` and merged
  - duplicate extras (`Brand`/`brand`): both ignored + warning
  - `Channels`: reserved
  - `Count of Circana Buyers`: reserved
  - unknown header in column C: `upload_unexpected_column`
- **P15:** `Avg Price` in B gives `upload_fixed_missing` (Avg_Brand_Price blank) plus `upload_unexpected_column`.
  `Read_Type` moved to J is matched. Two `Tot_Camp_Cost` columns give `upload_fixed_duplicated`, blank.
- **Two Study_Name columns:** leftmost used + warning.
- **P16/P17:**
  - every accept/warn example from section 7.4 checked through `build_final` on `Avg_Brand_Price`
  - `Read_Type` = `abc` and an extra = `abc`: no warning
  - `value_check=False`: no value warnings
  - warned values are merged byte-identical
- **P18:** xlsx with `D2 = 0.25` (numeric, percent format) merges `"0.25"`; CSV `25%` is warned and merged as `25%`.
- **Zero match:** `zero_match True`, `upload_study_count` correct, `upload_zero_match` first among upload warnings.
- **P26/P27 on the full-batch master (732 rows):**
  - final columns == master + `CALCULATED_HEADERS` + fixed six + extras
  - Study_Name appears once
  - length and order identical
  - every master cell string-identical
  - each study's values on every one of its rows
- **P29 proxy:** `build_final` against the full-batch master, then against master + one more study with the same
  parsed upload. The new study gets `study_not_in_upload`; the frame reflects the new master. Two calls with identical
  inputs give byte-identical `to_csv_bytes`.
- **Report:**
  - `phase2_warnings_to_frame` columns == `PHASE2_WARNING_COLUMNS`; empty case keeps the columns
  - `summarize_phase2_warnings` exact string; `""` when there are no warnings
  - filename builders exact
- **End-to-end precision:** `to_csv_bytes(final.frame)` starts with the BOM. Re-parsed with the stdlib `csv` module,
  all master columns are identical to the master's CSV fields, and the literal `0.19163628728414203` survives
  (Bounty appended via `process_batch`).

---

## 11. Design defaults pending confirmation

Each is marked in code with `# DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item N`.

1. A needed master input cell that is blank or not numeric makes the dependent outputs blank, with one warning per cell.
2. The copy columns (AG, AI, AJ, AM) go through `format_number`: same value, normalised text (`12149247.0` becomes
   `12149247`). They are not byte-copied.
3. Block key = `Study_Name`, `MODEL_DESC`, `Model`, compared exactly after `strip()`. `dependent_variable` is
   compared after strip + casefold.
4. Broken blocks give one warning per problem type (missing / duplicated). Unknown `dependent_variable` values
   receive nothing, silently.
5. The warning "Model" field is `"<MODEL_DESC> / <Model>"`.
6. The P3 signature includes the six merged headers, following P3's literal wording. Consequence: a `studyname_master`
   template dropped into the Phase 1 batch is rejected with the P3 reason, not "column mismatch".
7. P3 on the master path with no valid master suppresses the first-master slot.
8. P11 "contains master columns" means containing **all** of `MODEL_DESC`, `Model` and `dependent_variable`.
9. An unreadable or empty upload is refused (proposed wording, C3).
10. Two Study_Name columns in an upload: the leftmost is used, with a warning.
11. Fixed headers are matched by name at any position. An unknown header in columns A–G is ignored with a warning.
12. A duplicated header (fixed or extra) has all its occurrences ignored, with a warning. Nobody guesses which copy
    is right.
13. The reserved names for extras also include the calculated headers, the legacy header and `TEMPLATE_HEADERS`.
14. Upload rows with values but no study name are ignored with a warning. Blank-name master rows are excluded from
    the template, and get blank merged columns plus one warning.
15. All-blank upload rows do not count towards P13's "same study twice".
16. The P16 value check runs only on values that are actually merged.
17. Warnings filename: `phase2_warnings_<name>_<YYYY-MM-DD_HHMM>.csv`.
18. Percent cell format `0.00%`. `formatColumns` is allowed under sheet protection, so users can widen columns.
19. The section 6 leading symbols select the Streamlit box type and are not embedded in the strings.
20. `MSG_WARNINGS_SUMMARY` and `MSG_UPLOAD_PROMPT` wording.

---

## 12. Documentation placement — recommendation

**Save this spec as a separate `PHASE2_ARCHITECTURE.md`**, mirroring the `META_BRIEF.md` / `PHASE2_BRIEF.md` split.
`ARCHITECTURE.md` is a QC-approved, "BUILD COMPLETE" document. Interleaving Phase 2 into it would blur what was
signed off.

Add to `ARCHITECTURE.md` **one short new "Section 10 — Phase 2 amendments"**, listing exactly where Phase 1
contracts changed, so nothing in it is silently stale:
- edge case 14 superseded (P4)
- `process_file` step 3b
- `MasterCandidate.is_phase2_output` and the new `is_valid`
- the section 3 detection contract extended (P3)
- `file_reader.read_raw_grid`
- the new test sections, and the section 1 check replaced

The developer should also update `CLAUDE.md`'s code-structure table: the `config.py` row, the new modules, and the
test count.

---

## 13. Dependencies

No new packages. `openpyxl>=3.1` is already required. It is now also imported directly by `template_builder.py`, so
update its `requirements.txt` comment to "pandas .xlsx engine + template writer". Standard library additions:
`decimal`, `re`, `io`, and `random` (test only).

---

## 14. Build stages and QC gates (`PHASE2_BRIEF` section 10)

| Stage | Implement | Tests | QC gate |
|---|---|---|---|
| 1 | config (P3/P4 constants + all names), models, schema additions, master_detector, study_processor, app.py STEP 2/4/5/6 | 10.1 (scans + replaced config check), 10.2 | All Phase 1 checks green; the new scans green and non-vacuous; P4 truth table; P3 on all three paths. |
| 2 | numeric.py (format/parse only), template_builder, csv_writer template filename, glossary config | 10.3 | Template reloads with correct protection, types, format and sheets; round-trips through `read_table`/`read_raw_grid`. |
| 3 | numeric.py (multiply, contexts), calculations.py | 10.4, 10.5 | **Blocking:** layer 1 green **and** the `LAYER 2 RAN` line present and green. A SKIPPED run cannot be signed off. |
| 4 | file_reader.read_raw_grid, metadata_upload, final_builder, report additions, remaining filenames | 10.6 | P10–P18, P26–P27, P30 contracts; end-to-end precision on the final CSV. |
| 5 | app.py Run block + STEPs 7–9 + banner | streamlit scan | **First** the Phase 1 interactive checklist in `CLAUDE.md`. Then interactively: template opens in Excel; A refuses edits; B–G and H1 editable; `25%` in D2 shows 25.00%; upload merges `0.25`; Phase 1 results survive the Phase 2 upload and all 5 downloads; Run again keeps the upload and rebuilds the final file; refusal messages render; a real `.xlsx` upload works. |

---

## 15. Concerns — items needing Marcos's decision

- **C1. Reference comparison input (differs from `PHASE2_BRIEF` section 8 wording).** Rebuilding the master from
  `Samples/` cannot meet the 15-digit standard, because the workbook's A–AF values are Excel-rounded. AH2 would come
  out as `…78880451…` instead of `…783561948`. **Recommend:** compare using the workbook's own A–AF, plus the
  structural cross-check against `Samples/` (10.5 step 8).
- **C2. P11 vs P14 conflict.** P11 refuses an upload that "contains master columns". P14 says an extra that clashes
  with a master column is "ignored + warning". Both cannot apply to the same upload. **Recommend:** refuse only when
  all of `MODEL_DESC`, `Model` and `dependent_variable` are present; any other clash follows P14.
- **C3. Two refusals have no agreed wording:** the master-uploaded-in-STEP-8 case (it *has* Study_Name, so
  `MSG_WRONG_FILE` would be false), and the unreadable file. **Recommend** the `MSG_UPLOAD_IS_MASTER` /
  `MSG_UPLOAD_UNREADABLE` texts in section 1.1.
- **C4. P23 taken literally blanks Count of Circana Buyers when only `occ` is missing,** although that column does
  not use `occ`. **Recommend:** keep it literal. A structurally broken block should not export cross-row numbers.
- **C5. The Excel "Save as CSV" trap.** Saving the template as CSV writes displayed text. The percent column becomes
  `25.00%` (warned, merged as text per P16), and General-format numbers may be shortened. **Recommend:** add one
  sentence to the STEP 8 caption: "Upload the .xlsx as downloaded; saving it as CSV from Excel turns percentages
  into text."
- **C6. The rule scans `CLAUDE.md` refers to do not exist.** Stage 1 adds the rule-4 and rule-2 scans and **modifies
  one existing Phase 1 check** (the config list-length check, which would otherwise fail). **Recommend:** accept.
  It is the only Phase 1 test that changes.
- **C7. Excel text coercion in layer 2.** If the workbook stores some `N` values as text with more than 15 digits,
  Excel multiplied a 15-digit version of them. 10.5 step 6 isolates and reports those cells instead of failing the
  app. **Recommend:** accept. The count is printed, so it is visible, not hidden.

---

## 16. Handoff

```
HANDOFF TO: python-developer
COMPLEXITY TIER: 2 (Structured Module, flat code/ directory)

IMPLEMENT IN THIS ORDER (one stage per QC cycle, on branch phase2):
1. Stage 1 — config.py (Phase 2 block, section 1.1), models.py, schema.py additions,
   master_detector.py, study_processor.py, app.py STEP 2/4/5/6; tests 10.1 + 10.2
2. Stage 2 — numeric.py (parse/format), template_builder.py, template filename; test 10.3
3. Stage 3 — numeric.py (contexts/multiply), calculations.py; tests 10.4 + 10.5
   (BLOCKING: layer 2 must actually run)
4. Stage 4 — file_reader.read_raw_grid, metadata_upload.py, final_builder.py, report.py and
   csv_writer.py additions; test 10.6
5. Stage 5 — app.py Run block + STEPs 7–9 + banner; then the interactive checklist
   (Phase 1 checklist first)

HARD RULES:
- Only app.py imports streamlit; only template_builder.py imports openpyxl.
- dtype=str on every read; Decimal only in numeric.py via explicit contexts; no float(),
  round(), .round(), or any rule-2 banned token; every new DataFrame dtype=object.
- Column names as literals only in config.py.
- No filesystem writes; the xlsx is built in BytesIO.
- The schema comes from the master at runtime; source columns are resolved by normalized name.
- Halts: unloadable master (incl. P3 on the master builders) and the P11 upload refusal only.

DO NOT make design decisions not covered in this spec. Section 11 items are defaults —
implement them as stated and mark each with the DESIGN DEFAULT comment.
Section 15 items await Marcos; if he has not ruled before a stage needs one, implement the
stated recommendation and flag it in the stage report.

QC CHECKPOINT: qc-reviewer after EVERY stage.
```

Relevant files read for this design (all absolute):
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\PHASE2_BRIEF.md
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\CLAUDE.md
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\ARCHITECTURE.md
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\QUESTIONS_FOR_RAVI.md
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\code\ (app.py, config.py, models.py, file_reader.py, schema.py, master_detector.py, study_processor.py, report.py, csv_writer.py, test_meta_pipeline.py, requirements.txt)
- C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\Samples\Master_Instacart_2026-09-07_1200.csv and Holly_Rancher 27382_Scored.csv (these confirmed the 0.036091684 vs 0.03609168443151368 rounding)
- The reference workbook C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\Phase 2 process\master_file_w_calculations.xlsx exists but could not be opened with read-only tools. Its sheet layout, text-stored cells and exact cached strings are therefore taken from PHASE2_BRIEF section 3. Stage 3 QC must confirm them when layer 2 first runs.
