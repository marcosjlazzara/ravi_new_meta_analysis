"""
config.py — Constants only. No logic, no I/O, no column-name literals beyond
Study_Name (the one literal column name the app is allowed to know about).

The 31-name reference schema for study files lives ONLY in
test_meta_pipeline.py. Adding a data-column list here is a QC failure.
"""

from __future__ import annotations

ACCEPTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx")
EXCEL_SHEET_INDEX: int = 0                    # brief decision 6: "Excel reads sheet 1"

MASTER_FILENAME_PREFIX: str = "master_"       # compared against stem.lower()
# Output masters are written with the longer literal prefix below. Detection still
# uses MASTER_FILENAME_PREFIX, so both "Master_X" and "Master_File_X" are found;
# this constant exists so parse_master_base_name can strip the longer form first
# and the name does not grow ("Master_File_File_X") on each round trip.
MASTER_OUTPUT_FILENAME_PREFIX: str = "master_file_"   # compared against stem.lower()
STUDY_NAME_COL: str = "Study_Name"            # the only literal column name in the app

OUTPUT_ENCODING: str = "utf-8-sig"
TIMESTAMP_FORMAT: str = "%Y-%m-%d_%H%M"       # brief decision 15
MASTER_FILENAME_PATTERN: str = "Master_File_{name}_{timestamp}.csv"
EXCEPTION_FILENAME_PATTERN: str = "Exceptions_{name}_{timestamp}.csv"  # DESIGN DEFAULT — pending confirmation, see spec section 8, item 8
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
REASON_NOT_SELECTED_MASTER: str = "not selected as master"  # DESIGN DEFAULT — pending confirmation, see spec section 8, item 5

EXCEPTION_REPORT_COLUMNS: list[str] = ["file", "status", "reason", "missing_cols", "extra_cols"]
LIST_JOIN_SEPARATOR: str = "; "

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
ZERO_WIDTH_CHARS: str = "​‌‍⁠﻿"

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
# Q16, agreed 2026-09-29 — the STEP 6 banner shown whenever any file is rejected.
# {files} = "`name` (reason)" items joined with ", ". Singular/plural variants.
MSG_FILES_REJECTED_ONE: str = (
    "**1 file was rejected and NOT added to the master:** {files}. "
    "Fix this file and run again; studies already in the master will be skipped. "
    "Details are in the exception report."
)
MSG_FILES_REJECTED_MANY: str = (
    "**{n} files were rejected and NOT added to the master:** {files}. "
    "Fix these files and run again; studies already in the master will be skipped. "
    "Details are in the exception report."
)
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
# Ruling C5, 2026-09-28 — shown under the STEP 8 upload widget.
MSG_UPLOAD_CSV_CAUTION: str = (
    "Upload the .xlsx as downloaded; saving it as CSV from Excel turns percentages into text."
)

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
