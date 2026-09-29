"""
test_meta_pipeline.py — End-to-end QC script for the Meta Analysis Consolidation
pipeline. Run with: python test_meta_pipeline.py
Uses real sample files and the deliberate test_fixtures edge cases. No mocking.
Prints PASS/FAIL for every check.

Sections (grows with each build phase — see ARCHITECTURE.md section 7):
  1. Imports and config sanity                       [Phase 1]
  2. Reading the real sample files                    [Phase 1]
  3. Precision round-trip (BLOCKING gate)              [Phase 1]
  4. normalize_column / compare_columns / align_to_master   [Phase 2]
  5. Master detection (0/1/2 candidates, name parsing)       [Phase 3]
  6. Full batch processing                                   [Phase 4]
  7. Edge-case fixtures (full set)                            [Phase 4]
  8. Exception report and summary shape                       [Phase 4]
  9. csv_writer.py + Phase 5 QC checkpoint (precision round-trip
     through the complete pipeline, filenames, BOM, streamlit-import grep) [Phase 5]

REFERENCE_STUDY_COLUMNS (the 31 names from META_BRIEF.md section 4) is defined
HERE AND NOWHERE ELSE. config.py must never carry this list.
"""

from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths to real files
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "Samples"
FIXTURES_DIR = ROOT / "test_fixtures"
CODE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Helpers — copied in style from new_pg_antara_6_24/code/test_pipeline.py
# ---------------------------------------------------------------------------
_passed = 0
_failed = 0
_skipped = 0


def check(label: str, result: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "PASS" if result else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    if result:
        _passed += 1
    else:
        _failed += 1


def skip(label: str, detail: str = "") -> None:
    """Marks a check as skipped rather than passed/failed (Stage 3's
    reference-workbook comparison, section 13b, is the first user of this).
    Never counted as passed or failed.
    """
    global _skipped
    line = f"[SKIPPED] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    _skipped += 1


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# The 31-name reference schema. Defined HERE AND NOWHERE ELSE
# (ARCHITECTURE.md section 1 / META_BRIEF.md section 4). config.py must never
# carry this list. Moved above Section 1 (Stage 1) so the amended Section 1
# config-sanity check (10.1a/b) can use it too.
# ---------------------------------------------------------------------------
REFERENCE_STUDY_COLUMNS: list[str] = [
    "MODEL_DESC", "Model", "TIME_AGG_PERIOD", "START_WEEK", "END_WEEK", "dependent_variable",
    "CNT_EXPSD_HH", "UDJ_AVG_EXPSD_HH_PRE", "UDJ_AVG_CNTRL_HH_PRE", "UDJ_AVG_EXPSD_HH_PST",
    "UDJ_AVG_CNTRL_HH_PST", "UDJ_DOD_EFFCT", "UDJ_DIFF_EFFCT", "ADJ_MEAN_EXPSD_GRP",
    "ADJ_MEAN_CNTRL_GRP", "ADJ_DOD_EFFCT", "TWOTAIL_PVAL", "ONETAIL_PVAL", "ABS_DIFF", "DOL_DIFF",
    "ONETAIL_80_PCT_INTRVL_UB", "ONETAIL_80_PCT_INTRVL_LB", "ONETAIL_90_PCT_INTRVL_UB",
    "ONETAIL_90_PCT_INTRVL_LB", "TWOTAIL_80_PCT_INTRVL_UB", "TWOTAIL_80_PCT_INTRVL_LB",
    "TWOTAIL_90_PCT_INTRVL_UB", "TWOTAIL_90_PCT_INTRVL_LB", "CNT_IMPRESSIONS", "CNT_Model_HH",
    "Channels",
]


# ---------------------------------------------------------------------------
# SECTION 1 — Imports and config sanity
# ---------------------------------------------------------------------------
section("1. Imports and Config Sanity")

try:
    import config
    from models import UploadedItem, MasterCandidate, MasterContext, FileOutcome, BatchResult
    from file_reader import FileReadError, read_table
    check("config, models, file_reader import OK", True)
except Exception as e:
    check("config, models, file_reader import OK", False, str(e))
    print("\nCannot continue — fix imports first.")
    sys.exit(1)

check(
    "ACCEPTED_EXTENSIONS == ('.csv', '.xlsx')",
    config.ACCEPTED_EXTENSIONS == (".csv", ".xlsx"),
    str(config.ACCEPTED_EXTENSIONS),
)
check("EXCEL_SHEET_INDEX == 0", config.EXCEL_SHEET_INDEX == 0)
check("MASTER_FILENAME_PREFIX == 'master_'", config.MASTER_FILENAME_PREFIX == "master_")
check("STUDY_NAME_COL == 'Study_Name'", config.STUDY_NAME_COL == "Study_Name")
check("OUTPUT_ENCODING == 'utf-8-sig'", config.OUTPUT_ENCODING == "utf-8-sig")
check("REASON_NONE is the empty string", config.REASON_NONE == "")
check(
    "EXCEPTION_REPORT_COLUMNS is exactly the 5 brief-specified columns, in order",
    config.EXCEPTION_REPORT_COLUMNS == ["file", "status", "reason", "missing_cols", "extra_cols"],
    str(config.EXCEPTION_REPORT_COLUMNS),
)

# --- (10.1) Replaces the old "config.py carries no list of the 32 data
# columns" check, which would fail on Phase 2's CALCULATED_HEADERS (8
# entries) and TEMPLATE_HEADERS (7 entries). Amended rule 4: column names
# appear as literals ONLY in config.py — so config.py legitimately DOES
# carry the P24 source-column names (P24 requires config.py to be the only
# place they live). What must still hold: the FULL 31-name reference schema
# never leaks into config.py, and no single config sequence smuggles in more
# than the 3 names MASTER_LOOKALIKE_COLUMNS legitimately needs (P11).
def _walk_config_strings(value: object) -> set[str]:
    """Recursively collect every str leaf from a config value: scalars and
    elements of sequences, including nested sequences."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set, frozenset)):
        found: set[str] = set()
        for item in value:
            found |= _walk_config_strings(item)
        return found
    return set()


def _config_public_values() -> list[object]:
    return [getattr(config, name) for name in dir(config) if not name.startswith("_")]


_config_string_pool: set[str] = set()
for _v in _config_public_values():
    _config_string_pool |= _walk_config_strings(_v)

_reference_hits_in_config = _config_string_pool & set(REFERENCE_STUDY_COLUMNS)
check(
    "(10.1a) config.py string values intersect REFERENCE_STUDY_COLUMNS on exactly the 5 "
    "P24 source-column names, never the other 26",
    _reference_hits_in_config
    == {"MODEL_DESC", "Model", "dependent_variable", "CNT_EXPSD_HH", "ADJ_MEAN_EXPSD_GRP"},
    str(sorted(_reference_hits_in_config)),
)

_max_reference_names_in_one_sequence = 0
for _v in _config_public_values():
    if isinstance(_v, (list, tuple, set, frozenset)):
        _count = sum(1 for _s in _walk_config_strings(_v) if _s in REFERENCE_STUDY_COLUMNS)
        _max_reference_names_in_one_sequence = max(_max_reference_names_in_one_sequence, _count)
check(
    "(10.1b) no single config sequence contains more than 3 reference names "
    "(MASTER_LOOKALIKE_COLUMNS legitimately carries exactly 3 — P11)",
    _max_reference_names_in_one_sequence <= 3,
    str(_max_reference_names_in_one_sequence),
)

# --- models sanity ---
item = UploadedItem(index=0, name="Instacart_Bounty_scored.csv", data=b"x")
check("UploadedItem.stem strips the extension", item.stem == "Instacart_Bounty_scored", item.stem)
check("UploadedItem.extension is lowercased, incl. dot", item.extension == ".csv", item.extension)

item_no_ext = UploadedItem(index=1, name="notes", data=b"x")
check("UploadedItem.stem is verbatim when there is no extension", item_no_ext.stem == "notes", item_no_ext.stem)
check("UploadedItem.extension is '' when there is no extension", item_no_ext.extension == "", repr(item_no_ext.extension))

valid_candidate = MasterCandidate(index=0, name="Master_X.csv", readable=True, has_study_name=True, error="")
invalid_candidate = MasterCandidate(index=1, name="Master_Y.csv", readable=True, has_study_name=False, error="")
unreadable_candidate = MasterCandidate(index=2, name="Master_Z.csv", readable=False, has_study_name=False, error="boom")
check("MasterCandidate.is_valid is True when readable and has_study_name", valid_candidate.is_valid is True)
check("MasterCandidate.is_valid is False when has_study_name is False", invalid_candidate.is_valid is False)
check("MasterCandidate.is_valid is False when unreadable", unreadable_candidate.is_valid is False)

# --- FileReadError sanity ---
err = FileReadError(config.REASON_UNREADABLE, "boom")
check(
    "FileReadError carries .reason and .detail",
    err.reason == config.REASON_UNREADABLE and err.detail == "boom",
)

# ---------------------------------------------------------------------------
# SECTION 2 — Reading the real sample files
# ---------------------------------------------------------------------------
section("2. Reading Real Sample Files")

check("REFERENCE_STUDY_COLUMNS has exactly 31 entries", len(REFERENCE_STUDY_COLUMNS) == 31, f"got {len(REFERENCE_STUDY_COLUMNS)}")

STUDY_FILES: list[str] = [
    "Holly_Rancher 27382_Scored.csv",
    "Instacart - LOreal 1P_scored.csv",
    "Instacart - Nates Honey_scored.csv",
    "Instacart Firehook of Virginia_scored.csv",
    "Instacart_Bel Brands_scored.csv",
    "Instacart_Bounty_scored.csv",
    "Instacart_Cascade_scored.csv",
    "Instacart_GoGo Squeez_scored.csv",
    "Instacart_Planters_scored.csv",
    "Instacart_Stella Artois_scored.csv",
]
MASTER_FILES: list[str] = [
    "MaserFile_XXXX_DATE.csv",
    "Master_Instacart_2026-09-07_1200.csv",
]


def _all_cells_are_str(df) -> bool:
    return all(isinstance(v, str) for v in df.to_numpy().ravel())


check(f"{len(STUDY_FILES)} study sample files enumerated", len(STUDY_FILES) == 10, f"got {len(STUDY_FILES)}")

for filename in STUDY_FILES:
    path = SAMPLES_DIR / filename
    try:
        df = read_table(filename, path.read_bytes())
        check(f"{filename} reads via read_table", True, f"{len(df)} rows, {len(df.columns)} cols")
        check(
            f"{filename} has the 31 reference columns, in order",
            list(df.columns) == REFERENCE_STUDY_COLUMNS,
            "" if list(df.columns) == REFERENCE_STUDY_COLUMNS else f"got {list(df.columns)}",
        )
        check(f"{filename} every cell is str after _finalize", _all_cells_are_str(df))
    except Exception as e:
        check(f"{filename} reads via read_table", False, str(e))

for filename in MASTER_FILES:
    path = SAMPLES_DIR / filename
    try:
        df = read_table(filename, path.read_bytes())
        check(f"{filename} reads via read_table", True, f"{len(df)} rows, {len(df.columns)} cols")
        expected_columns = REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL]
        check(
            f"{filename} has 32 columns (31 reference + Study_Name)",
            list(df.columns) == expected_columns,
            "" if list(df.columns) == expected_columns else f"got {list(df.columns)}",
        )
        check(f"{filename} every cell is str after _finalize", _all_cells_are_str(df))
    except Exception as e:
        check(f"{filename} reads via read_table", False, str(e))

check(
    "The two master samples are byte-identical (per spec section 8 item 9)",
    (SAMPLES_DIR / "MaserFile_XXXX_DATE.csv").read_bytes()
    == (SAMPLES_DIR / "Master_Instacart_2026-09-07_1200.csv").read_bytes(),
)

# --- test_fixtures edge cases reachable through read_table alone (Phase 1 subset) ---
try:
    read_table(
        "reject_empty_file_scored.csv",
        (FIXTURES_DIR / "reject_empty_file_scored.csv").read_bytes(),
    )
    check("reject_empty_file_scored.csv raises FileReadError", False, "no exception was raised")
except FileReadError as e:
    check(
        "reject_empty_file_scored.csv raises REASON_EMPTY_FILE",
        e.reason == config.REASON_EMPTY_FILE,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "reject_empty_file_scored.csv raises REASON_EMPTY_FILE",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    read_table("no_header_line.csv", b"\n\n\n")
    check("non-zero bytes with no header line raise FileReadError", False, "no exception was raised")
except FileReadError as e:
    check(
        "non-zero bytes with no header line raise REASON_EMPTY_FILE",
        e.reason == config.REASON_EMPTY_FILE,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "non-zero bytes with no header line raise REASON_EMPTY_FILE",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    headers_only_df = read_table(
        "edge_headers_only_scored.csv",
        (FIXTURES_DIR / "edge_headers_only_scored.csv").read_bytes(),
    )
    check(
        "edge_headers_only_scored.csv returns an empty frame, NOT an error",
        len(headers_only_df) == 0,
        f"got {len(headers_only_df)} rows",
    )
    check(
        "edge_headers_only_scored.csv has the 31 reference columns populated",
        list(headers_only_df.columns) == REFERENCE_STUDY_COLUMNS,
        "" if list(headers_only_df.columns) == REFERENCE_STUDY_COLUMNS else f"got {list(headers_only_df.columns)}",
    )
except Exception as e:
    check("edge_headers_only_scored.csv returns an empty frame, NOT an error", False, str(e))

# ---------------------------------------------------------------------------
# SECTION 3 — Precision round-trip (BLOCKING — the Phase 1 QC gate)
# ---------------------------------------------------------------------------
section("3. Precision Round-Trip (BLOCKING)")

BOUNTY_FILE = SAMPLES_DIR / "Instacart_Bounty_scored.csv"

# Step 1: read raw with the stdlib csv module into list[dict[str, str]].
raw_rows: list[dict[str, str]] = []
try:
    with open(BOUNTY_FILE, "r", encoding="utf-8-sig", newline="") as f:
        raw_rows = list(csv.DictReader(f))
    check("Instacart_Bounty_scored.csv parsed with stdlib csv", True, f"{len(raw_rows)} rows")
except Exception as e:
    check("Instacart_Bounty_scored.csv parsed with stdlib csv", False, str(e))

# Step 2 (Phase 1 subset — only read_table exists; tag_study_name / align_to_master /
# process_batch / to_csv_bytes are Phase 2/4/5 and do not exist yet).
bounty_df = None
try:
    bounty_df = read_table(BOUNTY_FILE.name, BOUNTY_FILE.read_bytes())
    check("Instacart_Bounty_scored.csv read via read_table", True, f"{len(bounty_df)} rows")
except Exception as e:
    check("Instacart_Bounty_scored.csv read via read_table", False, str(e))

if raw_rows and bounty_df is not None:
    check(
        "read_table row count matches stdlib csv row count",
        len(bounty_df) == len(raw_rows),
        f"stdlib={len(raw_rows)} read_table={len(bounty_df)}",
    )

    # Step 4: every field of every row is string-identical — not float-equal.
    mismatches: list[tuple[int, str, str, str]] = []
    non_str_cells: list[tuple[int, str, type]] = []
    for i, raw_row in enumerate(raw_rows):
        for col in REFERENCE_STUDY_COLUMNS:
            raw_value = raw_row[col]
            table_value = bounty_df.iloc[i][col]
            if not isinstance(table_value, str):
                non_str_cells.append((i, col, type(table_value)))
            elif raw_value != table_value:
                mismatches.append((i, col, raw_value, table_value))

    check(
        "Every field of every row is a Python str",
        len(non_str_cells) == 0,
        f"{len(non_str_cells)} non-str cells, first: {non_str_cells[0]}" if non_str_cells else "",
    )
    check(
        "Every field of every row is string-identical to the source (31 cols)",
        len(mismatches) == 0,
        f"{len(mismatches)} mismatches, first: {mismatches[0]}" if mismatches else "",
    )

    # Step 5: the literal 17-significant-digit value survives verbatim.
    literal_present = any(
        (bounty_df[col] == "0.19163628728414203").any() for col in REFERENCE_STUDY_COLUMNS
    )
    check("Literal '0.19163628728414203' survives read_table verbatim", literal_present)
else:
    check("Precision round-trip", False, "skipped — source parse or read_table failed")

print(
    "\n[NOTE] QC CHECKPOINT steps 6-7 (Study_Name is the only field the output "
    "adds\nbeyond the source; to_csv_bytes(df)[:3] == UTF-8 BOM) are completed "
    "in Section 9\nbelow, now that schema.py, study_processor.py and "
    "csv_writer.py all exist (Phase 5)."
)

# ---------------------------------------------------------------------------
# SECTION 4 — schema.py unit checks                              [Phase 2]
# ---------------------------------------------------------------------------
section("4. Schema Unit Checks")

from schema import (
    SchemaError,
    normalize_column,
    build_column_index,
    compare_columns,
    tag_study_name,
    align_to_master,
)

MASTER_FILE = SAMPLES_DIR / "Master_Instacart_2026-09-07_1200.csv"
master_df = read_table(MASTER_FILE.name, MASTER_FILE.read_bytes())
MASTER_COLUMNS: list[str] = list(master_df.columns)
check(
    "Master sample has 32 columns (31 reference + Study_Name), in order",
    MASTER_COLUMNS == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL],
    "" if MASTER_COLUMNS == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL] else f"got {MASTER_COLUMNS}",
)

# --- normalize_column -------------------------------------------------------
check("normalize_column lowercases", normalize_column("ABS_DIFF") == "abs_diff", normalize_column("ABS_DIFF"))
check(
    "normalize_column strips leading/trailing whitespace",
    normalize_column("  ABS_DIFF  ") == "abs_diff",
    repr(normalize_column("  ABS_DIFF  ")),
)
check(
    "normalize_column collapses internal multi-space runs to one space",
    normalize_column("ABS   DIFF") == "abs diff",
    repr(normalize_column("ABS   DIFF")),
)
check(
    "normalize_column collapses mixed whitespace runs (tabs/newlines) to one space",
    normalize_column("ABS\t\n DIFF") == "abs diff",
    repr(normalize_column("ABS\t\n DIFF")),
)
check(
    "Two names differing only by case/whitespace normalize identically (collide)",
    normalize_column(" Study_Name ") == normalize_column("study_name"),
    f"{normalize_column(' Study_Name ')!r} vs {normalize_column('study_name')!r}",
)

# --- build_column_index -----------------------------------------------------
happy_index = build_column_index(["MODEL_DESC", "Model", "Study_Name"])
check(
    "build_column_index happy path maps normalized -> verbatim",
    happy_index == {"model_desc": "MODEL_DESC", "model": "Model", "study_name": "Study_Name"},
    str(happy_index),
)

try:
    build_column_index(["ABS_DIFF", "abs_diff"])
    check("build_column_index raises SchemaError on duplicate normalized names", False, "no exception was raised")
except SchemaError as e:
    check(
        "build_column_index raises SchemaError(REASON_DUPLICATE_COLUMNS) on duplicate normalized names",
        e.reason == config.REASON_DUPLICATE_COLUMNS,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "build_column_index raises SchemaError(REASON_DUPLICATE_COLUMNS) on duplicate normalized names",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

# --- compare_columns against the deliberate reject fixtures -----------------
missing_cols_df = read_table(
    "reject_missing_column_scored.csv",
    (FIXTURES_DIR / "reject_missing_column_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(missing_cols_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_missing_column_scored.csv: missing == ['ABS_DIFF']", missing == ["ABS_DIFF"], str(missing))
check("reject_missing_column_scored.csv: extra == []", extra == [], str(extra))

extra_cols_df = read_table(
    "reject_extra_column_scored.csv",
    (FIXTURES_DIR / "reject_extra_column_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(extra_cols_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_extra_column_scored.csv: extra == ['RETAILER_ID']", extra == ["RETAILER_ID"], str(extra))
check("reject_extra_column_scored.csv: missing == []", missing == [], str(missing))

missing_and_extra_df = read_table(
    "reject_missing_and_extra_scored.csv",
    (FIXTURES_DIR / "reject_missing_and_extra_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(missing_and_extra_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_missing_and_extra_scored.csv: missing == ['DOL_DIFF']", missing == ["DOL_DIFF"], str(missing))
check(
    "reject_missing_and_extra_scored.csv: extra == ['BANNER', 'REGION']",
    extra == ["BANNER", "REGION"],
    str(extra),
)

# --- optional exempts Study_Name for a normal 31-column study file ----------
bounty_for_compare = read_table(BOUNTY_FILE.name, BOUNTY_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(bounty_for_compare.columns), optional=[config.STUDY_NAME_COL])
check(
    "optional exempts Study_Name: 31-col study file vs 32-col master reports no missing",
    missing == [],
    str(missing),
)
check("optional exempts Study_Name: no extra either", extra == [], str(extra))

# --- pass_reordered_columns_scored.csv: clean compare + full reorder --------
REORDERED_FILE = FIXTURES_DIR / "pass_reordered_columns_scored.csv"
reordered_df = read_table(REORDERED_FILE.name, REORDERED_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(reordered_df.columns), optional=[config.STUDY_NAME_COL])
check("pass_reordered_columns_scored.csv compares clean: missing == []", missing == [], str(missing))
check("pass_reordered_columns_scored.csv compares clean: extra == []", extra == [], str(extra))

# align_to_master's own precondition check has no `optional` — it mirrors the
# real pipeline order (study_processor step 7): tag_study_name runs BEFORE
# align_to_master, so the frame already carries all 32 master columns by the
# time align_to_master sees it.
reordered_tagged = tag_study_name(reordered_df, "pass_reordered_columns_scored", config.STUDY_NAME_COL)
aligned_reordered = align_to_master(reordered_tagged, MASTER_COLUMNS)
check(
    "align_to_master restores exact master column order on the reversed fixture",
    list(aligned_reordered.columns) == MASTER_COLUMNS,
    "" if list(aligned_reordered.columns) == MASTER_COLUMNS else f"got {list(aligned_reordered.columns)}",
)

# --- value-integrity assertion: reordering never alters a single character --
value_mismatches: list[tuple[int, str, str, str]] = []
for col in reordered_df.columns:
    before = reordered_df[col].tolist()
    after = aligned_reordered[col].tolist()
    for row_idx, (b, a) in enumerate(zip(before, after)):
        if b != a:
            value_mismatches.append((row_idx, col, b, a))
check(
    "align_to_master value-integrity: every cell string-identical before/after reorder",
    len(value_mismatches) == 0,
    f"{len(value_mismatches)} mismatches, first: {value_mismatches[0]}" if value_mismatches else "",
)

# --- pass_messy_header_case_scored.csv: mixed case + padded whitespace -----
MESSY_FILE = FIXTURES_DIR / "pass_messy_header_case_scored.csv"
messy_df = read_table(MESSY_FILE.name, MESSY_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(messy_df.columns), optional=[config.STUDY_NAME_COL])
check("pass_messy_header_case_scored.csv compares clean: missing == []", missing == [], str(missing))
check("pass_messy_header_case_scored.csv compares clean: extra == []", extra == [], str(extra))

messy_tagged = tag_study_name(messy_df, "pass_messy_header_case_scored", config.STUDY_NAME_COL)
aligned_messy = align_to_master(messy_tagged, MASTER_COLUMNS)
check(
    "align_to_master aligns the messy-case/whitespace fixture to master order",
    list(aligned_messy.columns) == MASTER_COLUMNS,
    "" if list(aligned_messy.columns) == MASTER_COLUMNS else f"got {list(aligned_messy.columns)}",
)

# --- tag_study_name -----------------------------------------------------
tagged = tag_study_name(bounty_for_compare, "Instacart_Bounty_scored", config.STUDY_NAME_COL)
check(
    "tag_study_name sets the column on every row",
    (tagged[config.STUDY_NAME_COL] == "Instacart_Bounty_scored").all(),
)
other_cols_untouched = all(
    tagged[col].tolist() == bounty_for_compare[col].tolist()
    for col in bounty_for_compare.columns
    if col != config.STUDY_NAME_COL
)
check("tag_study_name leaves every other column untouched", other_cols_untouched)

master_with_existing_study_name = tag_study_name(master_df, "Overwritten_Name", config.STUDY_NAME_COL)
check(
    "tag_study_name overwrites a pre-existing Study_Name column",
    (master_with_existing_study_name[config.STUDY_NAME_COL] == "Overwritten_Name").all(),
)
other_cols_untouched_master = all(
    master_with_existing_study_name[col].tolist() == master_df[col].tolist()
    for col in master_df.columns
    if col != config.STUDY_NAME_COL
)
check(
    "tag_study_name overwrite path leaves every other column untouched",
    other_cols_untouched_master,
)

# --- align_to_master raises SchemaError on a violated precondition ---------
try:
    align_to_master(missing_cols_df, MASTER_COLUMNS)
    check("align_to_master raises SchemaError when a column is missing", False, "no exception was raised")
except SchemaError as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is missing",
        e.reason == config.REASON_COLUMN_MISMATCH,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is missing",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    align_to_master(extra_cols_df, MASTER_COLUMNS)
    check("align_to_master raises SchemaError when a column is extra", False, "no exception was raised")
except SchemaError as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is extra",
        e.reason == config.REASON_COLUMN_MISMATCH,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is extra",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

# ---------------------------------------------------------------------------
# SECTION 5 — Master detection                                   [Phase 3]
# ---------------------------------------------------------------------------
section("5. Master Detection")

import pandas as pd

from master_detector import (
    find_master_candidates,
    parse_master_base_name,
    sanitize_base_name,
    build_master_context_from_existing,
    build_master_context_from_first_file,
    collect_existing_study_names,
)

MASTER_FILE_NAME = "Master_Instacart_2026-09-07_1200.csv"
MASER_TYPO_FILE_NAME = "MaserFile_XXXX_DATE.csv"

# --- parse_master_base_name: all four documented forms ----------------------
check(
    "parse_master_base_name: 'Master_Instacart_2026-09-07_1430.csv' -> 'Instacart'",
    parse_master_base_name("Master_Instacart_2026-09-07_1430.csv") == "Instacart",
    parse_master_base_name("Master_Instacart_2026-09-07_1430.csv"),
)
check(
    "parse_master_base_name: 'Master_File_Instacart_2026-09-07_1430.csv' -> 'Instacart' "
    "(output prefix stripped whole, so 'File_' cannot accumulate on re-upload)",
    parse_master_base_name("Master_File_Instacart_2026-09-07_1430.csv") == "Instacart",
    parse_master_base_name("Master_File_Instacart_2026-09-07_1430.csv"),
)
check(
    "parse_master_base_name: 'Master_Instacart.csv' -> 'Instacart' (no timestamp suffix)",
    parse_master_base_name("Master_Instacart.csv") == "Instacart",
    parse_master_base_name("Master_Instacart.csv"),
)
check(
    "parse_master_base_name: 'master_A_B_2026-09-07_1430.csv' -> 'A_B' (lowercase prefix + timestamp)",
    parse_master_base_name("master_A_B_2026-09-07_1430.csv") == "A_B",
    parse_master_base_name("master_A_B_2026-09-07_1430.csv"),
)
check(
    "parse_master_base_name: lowercase-prefixed variant with no timestamp keeps the whole remainder",
    parse_master_base_name("master_simplename.csv") == "simplename",
    parse_master_base_name("master_simplename.csv"),
)
check(
    "parse_master_base_name: prefix stripped case-insensitively on the real sample master",
    parse_master_base_name(MASTER_FILE_NAME) == "Instacart",
    parse_master_base_name(MASTER_FILE_NAME),
)

# --- sanitize_base_name ------------------------------------------------------
check(
    "sanitize_base_name replaces every illegal character with the replacement char",
    sanitize_base_name('A<B>C:D"E/F\\G|H?I*J') == "A_B_C_D_E_F_G_H_I_J",
    sanitize_base_name('A<B>C:D"E/F\\G|H?I*J'),
)
check(
    "sanitize_base_name collapses repeated replacement characters into one",
    sanitize_base_name("A///B") == "A_B",
    sanitize_base_name("A///B"),
)
check(
    "sanitize_base_name strips leading/trailing whitespace",
    sanitize_base_name("  Instacart  ") == "Instacart",
    repr(sanitize_base_name("  Instacart  ")),
)
check(
    "sanitize_base_name strips trailing dots and spaces",
    sanitize_base_name("Instacart..  ") == "Instacart",
    repr(sanitize_base_name("Instacart..  ")),
)

# --- sanitize_base_name on pathological all-illegal-character inputs --------
# Fix (post-215 QC): a typed study name of "..." sanitizes to "" because dots
# are not in config.ILLEGAL_FILENAME_CHARS and are stripped entirely by the
# trailing .rstrip(". ") — that empty base_name used to flow straight into
# build_master_filename() unguarded, producing an unlabeled
# "Master__<timestamp>.csv". Verified behaviour below: only pure-dot /
# whitespace-and-dot inputs sanitize to "" — inputs made only of characters
# from ILLEGAL_FILENAME_CHARS (e.g. "*", "/") sanitize to a single "_"
# (replacement char, collapsed), which is non-empty and a legal — if terse —
# base name. Both shapes are asserted here so the distinction is locked in;
# the app.py gate below only rejects the true "" case.
check(
    'sanitize_base_name(\'...\') == \'\' (pure dots strip away entirely)',
    sanitize_base_name("...") == "",
    repr(sanitize_base_name("...")),
)
check(
    "sanitize_base_name('   ...   ') == '' (whitespace + dots, both stripped)",
    sanitize_base_name("   ...   ") == "",
    repr(sanitize_base_name("   ...   ")),
)
check(
    "sanitize_base_name('***') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("***") == "_",
    repr(sanitize_base_name("***")),
)
check(
    "sanitize_base_name('///') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("///") == "_",
    repr(sanitize_base_name("///")),
)
check(
    "sanitize_base_name('<<<>>>') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("<<<>>>") == "_",
    repr(sanitize_base_name("<<<>>>")),
)


def _first_master_gate_passes(typed_name: str) -> bool:
    """Mirrors app.py STEP 2b's first-master gate exactly (app.py cannot be
    imported here — it is the only module allowed to import streamlit and
    executes top-level Streamlit calls on import). When this returns False,
    app.py leaves `master` at None: Run stays disabled, no st.stop(), no
    default name substitution, and build_master_filename() is never reached.
    """
    return bool(typed_name.strip()) and bool(sanitize_base_name(typed_name))


for _pathological_name, _expect_gate_pass in [
    ("...", False),
    ("   ...   ", False),
    ("***", True),
    ("///", True),
    ("<<<>>>", True),
    ("Instacart", True),   # control: an ordinary name must still pass
    ("", False),           # control: blank was already rejected pre-fix
    ("   ", False),        # control: whitespace-only was already rejected pre-fix
]:
    check(
        f"first-master gate on {_pathological_name!r}: "
        f"{'passes (build_master_filename reachable)' if _expect_gate_pass else 'blocked (build_master_filename never reached)'}",
        _first_master_gate_passes(_pathological_name) is _expect_gate_pass,
        _first_master_gate_passes(_pathological_name),
    )

# For every input the gate blocks, prove the danger it prevents: applying
# build_master_filename directly to the unguarded sanitized result would have
# produced the unlabeled "Master__<timestamp>.csv" artifact described in the
# defect report.
from datetime import datetime as _datetime_s5
from csv_writer import build_master_filename

_fixed_now = _datetime_s5(2026, 9, 7, 14, 30)
for _blocked_name in ("...", "   ...   "):
    _unguarded_filename = build_master_filename(sanitize_base_name(_blocked_name), _fixed_now)
    check(
        f"unguarded build_master_filename({_blocked_name!r}) would yield the "
        "unlabeled 'Master_File__...' artifact the gate exists to prevent",
        _unguarded_filename == "Master_File__2026-09-07_1430.csv",
        _unguarded_filename,
    )
    check(
        f"the gate blocks {_blocked_name!r} before that call is ever reached",
        _first_master_gate_passes(_blocked_name) is False,
    )

# --- resume-path safety: parse_master_base_name has no sanitize step -------
# Checked per the task's instruction to confirm (not assume) the resume path
# is safe. Finding: parse_master_base_name CAN return "" — a filename like
# "master_.csv" has the entire stem consumed by the prefix, leaving an empty
# remainder that MASTER_TIMESTAMP_SUFFIX_RE (which requires 1+ chars via
# `.+`) does not match, so the empty remainder is returned as-is. This is a
# real, reachable case (not merely a shape lookalike), so app.py STEP 3 warns
# on it (see app.py: "master.base_name has no usable name" branch).
check(
    "parse_master_base_name('master_.csv') == '' — resume-path base_name can be empty",
    parse_master_base_name("master_.csv") == "",
    repr(parse_master_base_name("master_.csv")),
)
check(
    "parse_master_base_name('Master_.csv') == '' — case-insensitive prefix, same empty result",
    parse_master_base_name("Master_.csv") == "",
    repr(parse_master_base_name("Master_.csv")),
)


def _resume_path_needs_warning(filename: str) -> bool:
    """Mirrors app.py STEP 3's resume-path safety check for a master whose
    base_name parsed empty (created_this_run is always False on this path)."""
    return not parse_master_base_name(filename).strip()


check(
    "resume-path warning predicate fires for 'master_.csv'",
    _resume_path_needs_warning("master_.csv") is True,
)
check(
    "resume-path warning predicate does NOT fire for the real sample master filename",
    _resume_path_needs_warning(MASTER_FILE_NAME) is False,
)

# --- zero-candidate path: only study files -----------------------------------
zero_candidate_items = [
    UploadedItem(index=i, name=name, data=(SAMPLES_DIR / name).read_bytes())
    for i, name in enumerate(STUDY_FILES)
]
zero_candidates = find_master_candidates(zero_candidate_items)
check(
    "zero-candidate path: a batch of only study files yields no candidates",
    zero_candidates == [],
    str(zero_candidates),
)

# --- one-candidate path -------------------------------------------------------
one_candidate_items = zero_candidate_items + [
    UploadedItem(
        index=len(zero_candidate_items),
        name=MASTER_FILE_NAME,
        data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes(),
    )
]
one_candidates = find_master_candidates(one_candidate_items)
one_valid = [c for c in one_candidates if c.is_valid]
check(
    "one-candidate path: exactly one valid candidate found",
    len(one_valid) == 1,
    str(one_candidates),
)
check(
    "one-candidate path: base_name parses to 'Instacart'",
    bool(one_valid) and parse_master_base_name(one_valid[0].name) == "Instacart",
    parse_master_base_name(one_valid[0].name) if one_valid else "no valid candidate",
)

# --- two-candidate path: second file built in memory, never written to disk -
master_bytes = (SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
two_candidate_items = [
    UploadedItem(index=0, name=MASTER_FILE_NAME, data=master_bytes),
    UploadedItem(index=1, name="Master_Second_2026-09-07_1300.csv", data=master_bytes),
]
two_candidates = find_master_candidates(two_candidate_items)
two_valid = [c for c in two_candidates if c.is_valid]
check(
    "two-candidate path: two differently-named Master_* files both returned as valid",
    len(two_valid) == 2,
    str(two_candidates),
)

# --- the 'Maser' typo is correctly NOT detected ------------------------------
maser_items = [
    UploadedItem(
        index=0,
        name=MASER_TYPO_FILE_NAME,
        data=(SAMPLES_DIR / MASER_TYPO_FILE_NAME).read_bytes(),
    )
]
maser_candidates = find_master_candidates(maser_items)
check(
    "'MaserFile_XXXX_DATE.csv' is NOT detected as a master candidate ('maserfile_' != 'master_')",
    maser_candidates == [],
    str(maser_candidates),
)

# --- Master_-prefixed file lacking Study_Name --------------------------------
no_study_name_item = UploadedItem(
    index=0,
    name="Master_NoStudyName.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
no_study_name_candidates = find_master_candidates([no_study_name_item])
check(
    "Master_-prefixed file lacking Study_Name still appears as a candidate",
    len(no_study_name_candidates) == 1,
    str(no_study_name_candidates),
)
if no_study_name_candidates:
    c = no_study_name_candidates[0]
    check("... it is readable", c.readable is True)
    check("... has_study_name is False", c.has_study_name is False)
    check("... is_valid is False", c.is_valid is False)

# --- unreadable Master_-prefixed file: find_master_candidates must not raise
unreadable_master_item = UploadedItem(index=0, name="Master_Empty.csv", data=b"")
unreadable_master_candidates = find_master_candidates([unreadable_master_item])
check(
    "find_master_candidates does not raise on an unreadable Master_-prefixed file",
    len(unreadable_master_candidates) == 1,
    str(unreadable_master_candidates),
)
if unreadable_master_candidates:
    c = unreadable_master_candidates[0]
    check("... readable is False", c.readable is False)
    check("... error is populated", c.error != "", repr(c.error))
    check("... is_valid is False", c.is_valid is False)

# --- Master_-prefixed file that reads fine but has duplicate normalized -----
# columns. Coverage gap closed per Phase 3 QC follow-up: this path was only
# verified by hand before (find_master_candidates catches SchemaError from
# build_column_index before `readable` is ever set True). Built in memory
# from a real study file's bytes — never written to disk.
import io as _io

duplicate_source_bytes = (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes()
duplicate_source_text = duplicate_source_bytes.decode("utf-8-sig")
duplicate_source_rows = list(csv.reader(_io.StringIO(duplicate_source_text)))
duplicate_header = duplicate_source_rows[0]
abs_diff_index = duplicate_header.index("ABS_DIFF")

# Append a second column that normalizes to the same key as ABS_DIFF, plus
# Study_Name — so the only reason this candidate fails is the duplication.
duplicate_header_with_dupe = duplicate_header + ["Abs_Diff", config.STUDY_NAME_COL]
duplicate_data_rows = [
    row + [row[abs_diff_index], "Some_Study"] for row in duplicate_source_rows[1:]
]

duplicate_output = _io.StringIO()
csv.writer(duplicate_output).writerows([duplicate_header_with_dupe] + duplicate_data_rows)
duplicate_columns_bytes = duplicate_output.getvalue().encode("utf-8-sig")

duplicate_columns_item = UploadedItem(
    index=0, name="Master_DuplicateCols.csv", data=duplicate_columns_bytes
)
duplicate_columns_candidates = find_master_candidates([duplicate_columns_item])
check(
    "find_master_candidates does not raise on a Master_-prefixed file with duplicate normalized columns",
    len(duplicate_columns_candidates) == 1,
    str(duplicate_columns_candidates),
)
if duplicate_columns_candidates:
    c = duplicate_columns_candidates[0]
    check("... readable is False (duplicate ABS_DIFF/Abs_Diff columns)", c.readable is False)
    check("... is_valid is False", c.is_valid is False)
    check(
        "... error names both offending columns",
        c.error != "" and "ABS_DIFF" in c.error and "Abs_Diff" in c.error,
        repr(c.error),
    )

# --- build_master_context_from_existing on the real master -------------------
real_master_item = UploadedItem(
    index=0, name=MASTER_FILE_NAME, data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
)
existing_context = build_master_context_from_existing(real_master_item)
check(
    "build_master_context_from_existing: 32 columns, in file order",
    existing_context.columns == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL],
    "" if existing_context.columns == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL] else str(existing_context.columns),
)
check(
    "build_master_context_from_existing: 52 rows",
    len(existing_context.frame) == 52,
    len(existing_context.frame),
)
check(
    "build_master_context_from_existing: created_this_run is False",
    existing_context.created_this_run is False,
)
check(
    "build_master_context_from_existing: base_name == 'Instacart'",
    existing_context.base_name == "Instacart",
    existing_context.base_name,
)
check(
    "build_master_context_from_existing: existing_study_names has exactly one normalized entry",
    existing_context.existing_study_names == {"holly_rancher 27382_scored"},
    str(existing_context.existing_study_names),
)

# --- build_master_context_from_first_file on a 31-column study file ---------
bounty_item = UploadedItem(
    index=0,
    name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
bounty_original_df = read_table(bounty_item.name, bounty_item.data)
first_file_context = build_master_context_from_first_file(bounty_item, "Instacart")
check(
    "build_master_context_from_first_file: Study_Name appended LAST as column 32",
    len(first_file_context.columns) == 32 and first_file_context.columns[-1] == config.STUDY_NAME_COL,
    str(first_file_context.columns),
)
check(
    "build_master_context_from_first_file: every row's Study_Name set to the file's stem",
    (first_file_context.frame[config.STUDY_NAME_COL] == bounty_item.stem).all(),
)
check(
    "build_master_context_from_first_file: created_this_run is True",
    first_file_context.created_this_run is True,
)
check(
    "build_master_context_from_first_file: base_name sanitized from the typed name",
    first_file_context.base_name == "Instacart",
    first_file_context.base_name,
)

first_file_value_mismatches: list[tuple[int, str, str, str]] = []
for col in REFERENCE_STUDY_COLUMNS:
    before = bounty_original_df[col].tolist()
    after = first_file_context.frame[col].tolist()
    for row_idx, (b, a) in enumerate(zip(before, after)):
        if b != a:
            first_file_value_mismatches.append((row_idx, col, b, a))
check(
    "build_master_context_from_first_file: every pre-existing value is character-identical to the source",
    len(first_file_value_mismatches) == 0,
    f"{len(first_file_value_mismatches)} mismatches, first: {first_file_value_mismatches[0]}" if first_file_value_mismatches else "",
)

# --- build_master_context_from_first_file on a file that ALREADY has Study_Name
# This is the guard for DESIGN DEFAULT section 8 item 2: the column and its
# values must be left completely untouched, not overwritten with the item's
# stem. Uses the real Holly_Rancher master sample as the "chosen first file".
already_tagged_item = UploadedItem(
    index=0,
    name=MASER_TYPO_FILE_NAME,
    data=(SAMPLES_DIR / MASER_TYPO_FILE_NAME).read_bytes(),
)
already_tagged_probe = read_table(already_tagged_item.name, already_tagged_item.data)
already_tagged_context = build_master_context_from_first_file(already_tagged_item, "SomeTypedName")
check(
    "pre-existing Study_Name column keeps its original position (not moved/re-appended)",
    list(already_tagged_context.frame.columns) == list(already_tagged_probe.columns),
    str(list(already_tagged_context.frame.columns)),
)
check(
    "pre-existing Study_Name values are untouched: all 52 rows still 'Holly_Rancher 27382_Scored'",
    (already_tagged_context.frame[config.STUDY_NAME_COL] == "Holly_Rancher 27382_Scored").sum() == 52,
    str(already_tagged_context.frame[config.STUDY_NAME_COL].value_counts().to_dict()),
)
check(
    "pre-existing Study_Name values were NOT overwritten with the item's stem 'MaserFile_XXXX_DATE'",
    not (already_tagged_context.frame[config.STUDY_NAME_COL] == "MaserFile_XXXX_DATE").any(),
)
check(
    "pre-existing Study_Name values were NOT overwritten with 'Master_Instacart_2026-09-07_1200'",
    not (already_tagged_context.frame[config.STUDY_NAME_COL] == "Master_Instacart_2026-09-07_1200").any(),
)

# --- collect_existing_study_names --------------------------------------------
study_name_probe_frame = pd.DataFrame(
    {config.STUDY_NAME_COL: ["Alpha", " alpha ", "", "   ", "Beta", "ALPHA"]}
)
collected_names = collect_existing_study_names(study_name_probe_frame, config.STUDY_NAME_COL)
check(
    "collect_existing_study_names excludes blanks and normalizes case/whitespace variants together",
    collected_names == {"alpha", "beta"},
    str(collected_names),
)

# ---------------------------------------------------------------------------
# SECTION 6 — Full batch processing                              [Phase 4]
# ---------------------------------------------------------------------------
section("6. Full Batch Processing")

from study_processor import process_file, process_batch


def _make_study_items(names: list[str]) -> list[UploadedItem]:
    return [
        UploadedItem(index=i, name=name, data=(SAMPLES_DIR / name).read_bytes())
        for i, name in enumerate(names)
    ]


def _fresh_master() -> MasterContext:
    master_item = UploadedItem(
        index=999,
        name=MASTER_FILE_NAME,
        data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes(),
    )
    return build_master_context_from_existing(master_item)


# --- 10 study files into the real master -------------------------------------
full_batch_master = _fresh_master()
full_batch_items = _make_study_items(STUDY_FILES)
full_batch_study_names = {item.index: item.stem for item in full_batch_items}

expected_master_rows = len(full_batch_master.frame)

# NOTE: the real Master_Instacart_2026-09-07_1200.csv is byte-identical to
# MaserFile_XXXX_DATE.csv (spec section 8 item 9), i.e. it already contains
# Holly_Rancher's 52 rows under Study_Name "Holly_Rancher 27382_Scored"
# (confirmed in section 5: existing_study_names == {'holly_rancher 27382_scored'}).
# Feeding the real Holly_Rancher_27382_Scored.csv study file with its default
# stem name therefore collides with that pre-existing entry and is correctly
# skipped per decision 12 — it is NOT a clean 10-for-10 append. This is the
# exact same collision mechanic pinned down explicitly in THE TRAP below;
# it also fires here in the plain 10-file run because it happens to be the
# real sample master, not a synthetic empty one. Computed, not assumed:
already_present_files = [
    name for name in STUDY_FILES
    if Path(name).stem.strip().casefold() in full_batch_master.existing_study_names
]
expected_appended_files = [name for name in STUDY_FILES if name not in already_present_files]
expected_appended_count = len(expected_appended_files)
expected_study_rows_appended = sum(
    len(read_table(name, (SAMPLES_DIR / name).read_bytes())) for name in expected_appended_files
)
expected_total_rows = expected_master_rows + expected_study_rows_appended

full_batch_result = process_batch(full_batch_items, full_batch_master, full_batch_study_names)

check(
    "full batch: pre-existing collision detected — exactly 'Holly_Rancher 27382_Scored.csv' "
    "already lives in the real sample master",
    already_present_files == ["Holly_Rancher 27382_Scored.csv"],
    str(already_present_files),
)
check(
    "full batch: files not already in the master all append; the one pre-existing collision "
    "is skipped, 0 rejected",
    full_batch_result.appended == expected_appended_count
    and full_batch_result.skipped == len(already_present_files)
    and full_batch_result.rejected == 0,
    f"appended={full_batch_result.appended} skipped={full_batch_result.skipped} rejected={full_batch_result.rejected}",
)
check(
    "full batch: final row count == master rows + sum of the non-colliding files' data rows "
    "(computed from the files and the master's existing_study_names, not hardcoded)",
    len(full_batch_result.master_df) == expected_total_rows,
    f"expected={expected_total_rows} got={len(full_batch_result.master_df)}",
)
check(
    "full batch: total_records matches len(master_df)",
    full_batch_result.total_records == len(full_batch_result.master_df),
)
check(
    "full batch: master_df column order matches master's 32 columns exactly",
    list(full_batch_result.master_df.columns) == full_batch_master.columns,
    "" if list(full_batch_result.master_df.columns) == full_batch_master.columns else str(list(full_batch_result.master_df.columns)),
)
check(
    "full batch: rows_appended equals the sum of the non-colliding files' data rows",
    full_batch_result.rows_appended == expected_study_rows_appended,
    f"expected={expected_study_rows_appended} got={full_batch_result.rows_appended}",
)

# --- idempotency: feed the resulting master back in with the same 10 files --
rerun_master = MasterContext(
    frame=full_batch_result.master_df,
    columns=full_batch_master.columns,
    column_index=build_column_index(full_batch_master.columns),
    base_name=full_batch_master.base_name,
    source_file=full_batch_master.source_file,
    source_index=-1,
    existing_study_names=collect_existing_study_names(full_batch_result.master_df, config.STUDY_NAME_COL),
    created_this_run=False,
)
rerun_items = _make_study_items(STUDY_FILES)
rerun_study_names = {item.index: item.stem for item in rerun_items}
rerun_result = process_batch(rerun_items, rerun_master, rerun_study_names)

check(
    "idempotency: re-running the same batch appends 0 files",
    rerun_result.appended == 0,
    f"appended={rerun_result.appended}",
)
check(
    "idempotency: all 10 files are skipped / already in master",
    all(
        o.status == config.STATUS_SKIPPED and o.reason == config.REASON_ALREADY_IN_MASTER
        for o in rerun_result.outcomes
    ),
    str([(o.file, o.status, o.reason) for o in rerun_result.outcomes]),
)
check(
    "idempotency: row count is unchanged after the re-run",
    len(rerun_result.master_df) == len(full_batch_result.master_df),
    f"before={len(full_batch_result.master_df)} after={len(rerun_result.master_df)}",
)

# --- first-master path: a study file designated as the first master ---------
first_master_items = _make_study_items(STUDY_FILES)
BOUNTY_INDEX = STUDY_FILES.index("Instacart_Bounty_scored.csv")
first_master_ctx = build_master_context_from_first_file(first_master_items[BOUNTY_INDEX], "Instacart")
first_master_study_names = {item.index: item.stem for item in first_master_items}
first_master_result = process_batch(first_master_items, first_master_ctx, first_master_study_names)

check(
    "first-master path: the designated master file appears in NO outcome",
    all(o.index != BOUNTY_INDEX for o in first_master_result.outcomes),
    str([(o.index, o.file) for o in first_master_result.outcomes if o.index == BOUNTY_INDEX]),
)
expected_bounty_rows = len(
    read_table("Instacart_Bounty_scored.csv", (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes())
)
bounty_rows_in_master = (
    first_master_result.master_df[config.STUDY_NAME_COL] == "Instacart_Bounty_scored"
).sum()
check(
    "first-master path: its rows appear exactly once, not twice",
    bounty_rows_in_master == expected_bounty_rows,
    f"expected={expected_bounty_rows} got={bounty_rows_in_master}",
)
check(
    "first-master path: 9 other files appended (Bounty itself excluded structurally)",
    first_master_result.appended == 9,
    f"appended={first_master_result.appended}",
)

# --- THE TRAP (spec section 8 item 9) ----------------------------------------
ALL_12_FILES = STUDY_FILES + ["MaserFile_XXXX_DATE.csv", "Master_Instacart_2026-09-07_1200.csv"]
trap_items = _make_study_items(ALL_12_FILES)
MASER_INDEX = ALL_12_FILES.index("MaserFile_XXXX_DATE.csv")
MASTER_INDEX_IN_TRAP = ALL_12_FILES.index("Master_Instacart_2026-09-07_1200.csv")
HOLLY_INDEX = ALL_12_FILES.index("Holly_Rancher 27382_Scored.csv")

trap_master_ctx = build_master_context_from_existing(trap_items[MASTER_INDEX_IN_TRAP])
trap_study_names = {item.index: item.stem for item in trap_items}
trap_result = process_batch(trap_items, trap_master_ctx, trap_study_names)

check(
    "THE TRAP: the selected master file produces no outcome (excluded by source_index)",
    all(o.index != MASTER_INDEX_IN_TRAP for o in trap_result.outcomes),
)
maser_outcome = next((o for o in trap_result.outcomes if o.index == MASER_INDEX), None)
check(
    "THE TRAP: MaserFile_XXXX_DATE.csv falls through as a study file and IS appended",
    maser_outcome is not None and maser_outcome.status == config.STATUS_APPENDED,
    str(maser_outcome),
)
check(
    "THE TRAP: MaserFile_XXXX_DATE.csv's Study_Name is overwritten to its own stem",
    maser_outcome is not None and maser_outcome.study_name == "MaserFile_XXXX_DATE",
    maser_outcome.study_name if maser_outcome else "no outcome",
)
duplicated_rows = (trap_result.master_df[config.STUDY_NAME_COL] == "MaserFile_XXXX_DATE").sum()
check(
    "THE TRAP: Holly_Rancher's 52 rows are duplicated under the second name 'MaserFile_XXXX_DATE'",
    duplicated_rows == 52,
    f"got {duplicated_rows}",
)
holly_outcome = next((o for o in trap_result.outcomes if o.index == HOLLY_INDEX), None)
check(
    "THE TRAP: the real Holly_Rancher study file is skipped as already in master "
    "(its Study_Name already exists in the loaded master)",
    holly_outcome is not None
    and holly_outcome.status == config.STATUS_SKIPPED
    and holly_outcome.reason == config.REASON_ALREADY_IN_MASTER,
    str(holly_outcome),
)
expected_trap_total_rows = expected_total_rows + duplicated_rows  # Maser's duplicate re-adds
# exactly what Holly_Rancher's own-file skip withheld (both are 52 rows), so the total
# lands back on "master + all 9 non-Holly files + one duplicate copy of Holly's 52 rows".
check(
    "THE TRAP: final row count == master rows + non-colliding study files' rows + "
    "Maser's 52 duplicated rows",
    len(trap_result.master_df) == expected_trap_total_rows,
    f"expected={expected_trap_total_rows} got={len(trap_result.master_df)}",
)

# --- duplicate within one batch: two items forced to the same Study_Name ----
dup_batch_master = _fresh_master()
dup_item_a = UploadedItem(
    index=0, name="Instacart_Cascade_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes(),
)
dup_item_b = UploadedItem(
    index=1, name="Instacart_GoGo Squeez_scored.csv",
    data=(SAMPLES_DIR / "Instacart_GoGo Squeez_scored.csv").read_bytes(),
)
dup_batch_study_names = {0: "Same_Study_Name", 1: "Same_Study_Name"}
dup_batch_result = process_batch([dup_item_a, dup_item_b], dup_batch_master, dup_batch_study_names)

check(
    "duplicate in batch: the first file (upload order) appends",
    dup_batch_result.outcomes[0].status == config.STATUS_APPENDED,
    str(dup_batch_result.outcomes[0]),
)
check(
    "duplicate in batch: the second file is skipped / duplicate in batch",
    dup_batch_result.outcomes[1].status == config.STATUS_SKIPPED
    and dup_batch_result.outcomes[1].reason == config.REASON_DUPLICATE_IN_BATCH,
    str(dup_batch_result.outcomes[1]),
)

# --- excluded_indices / excluded_outcomes: unselected master candidate ------
# ZERO test coverage before this. These two params exist to support
# ARCHITECTURE.md section 4 edge case 5 / section 8 item 5: two valid master
# candidates found, the user picks one via app.py's (Phase 5) st.selectbox,
# and the unselected one must be excluded from processing and reported as
# skipped / REASON_NOT_SELECTED_MASTER. Simulated here without app.py.
excluded_master_bytes = master_bytes  # real master bytes, reused in memory (never written to disk)
excluded_second_master_name = "Master_Unselected_2026-09-07_1300.csv"

EXCL_MASTER_INDEX = 0
EXCL_BOUNTY_INDEX = 1
EXCL_CASCADE_INDEX = 2
EXCL_SECOND_MASTER_INDEX = 3

excluded_batch_items = [
    UploadedItem(index=EXCL_MASTER_INDEX, name=MASTER_FILE_NAME, data=excluded_master_bytes),
    UploadedItem(
        index=EXCL_BOUNTY_INDEX, name="Instacart_Bounty_scored.csv",
        data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
    ),
    UploadedItem(
        index=EXCL_CASCADE_INDEX, name="Instacart_Cascade_scored.csv",
        data=(SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes(),
    ),
    UploadedItem(
        index=EXCL_SECOND_MASTER_INDEX, name=excluded_second_master_name,
        data=excluded_master_bytes,
    ),
]
excluded_batch_master = build_master_context_from_existing(excluded_batch_items[EXCL_MASTER_INDEX])
check(
    "excluded_indices setup: master.source_index == the real master's index (0)",
    excluded_batch_master.source_index == EXCL_MASTER_INDEX,
    excluded_batch_master.source_index,
)

excluded_batch_study_names = {
    EXCL_BOUNTY_INDEX: "Instacart_Bounty_scored",
    EXCL_CASCADE_INDEX: "Instacart_Cascade_scored",
}
excluded_second_master_outcome = FileOutcome(
    file=excluded_second_master_name,
    index=EXCL_SECOND_MASTER_INDEX,
    status=config.STATUS_SKIPPED,
    reason=config.REASON_NOT_SELECTED_MASTER,
    missing_cols=[],
    extra_cols=[],
    study_name="",
    rows=0,
)

excluded_batch_result = process_batch(
    excluded_batch_items,
    excluded_batch_master,
    excluded_batch_study_names,
    excluded_indices={EXCL_SECOND_MASTER_INDEX},
    excluded_outcomes=[excluded_second_master_outcome],
)

check(
    "excluded_indices: master.source_index (0) produces no outcome, independently of "
    "excluded_indices (which only contains 3)",
    all(o.index != EXCL_MASTER_INDEX for o in excluded_batch_result.outcomes),
    str([(o.index, o.file) for o in excluded_batch_result.outcomes if o.index == EXCL_MASTER_INDEX]),
)
check(
    "excluded_indices: the unselected second master (index 3) is NOT processed — its rows "
    "(a duplicate of Holly_Rancher's 52) do not appear in master_df",
    (excluded_batch_result.master_df[config.STUDY_NAME_COL] == excluded_second_master_name).sum() == 0,
)
check(
    "excluded_outcomes: the supplied FileOutcome for the unselected master is present "
    "verbatim in result.outcomes",
    excluded_second_master_outcome in excluded_batch_result.outcomes,
    str(excluded_batch_result.outcomes),
)
check(
    "excluded_outcomes: outcomes remain sorted by index after merging",
    [o.index for o in excluded_batch_result.outcomes]
    == sorted(o.index for o in excluded_batch_result.outcomes),
    str([o.index for o in excluded_batch_result.outcomes]),
)

expected_excluded_bounty_rows = len(
    read_table("Instacart_Bounty_scored.csv", (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes())
)
expected_excluded_cascade_rows = len(
    read_table("Instacart_Cascade_scored.csv", (SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes())
)
expected_excluded_total_rows = (
    len(excluded_batch_master.frame) + expected_excluded_bounty_rows + expected_excluded_cascade_rows
)
check(
    "excluded_indices/excluded_outcomes: appended/skipped/total_files reconcile — 2 real "
    "study files appended, 1 injected skipped outcome, 3 total outcomes, 0 rejected",
    excluded_batch_result.appended == 2
    and excluded_batch_result.skipped == 1
    and excluded_batch_result.rejected == 0
    and excluded_batch_result.total_files == 3,
    f"appended={excluded_batch_result.appended} skipped={excluded_batch_result.skipped} "
    f"rejected={excluded_batch_result.rejected} total_files={excluded_batch_result.total_files}",
)
check(
    "excluded_indices/excluded_outcomes: final row count == master rows + the two real "
    "study files' rows only (the excluded second master contributes nothing)",
    len(excluded_batch_result.master_df) == expected_excluded_total_rows,
    f"expected={expected_excluded_total_rows} got={len(excluded_batch_result.master_df)}",
)

# ---------------------------------------------------------------------------
# SECTION 7 — Edge-case fixtures (full set)                      [Phase 4]
# ---------------------------------------------------------------------------
section("7. Edge-Case Fixtures — Full Set")

edge_case_master = _fresh_master()


def _fixture_item(name: str, index: int = 0) -> UploadedItem:
    return UploadedItem(index=index, name=name, data=(FIXTURES_DIR / name).read_bytes())


# --- the three rejection fixtures: column mismatch with correct missing/extra
reject_missing_item = _fixture_item("reject_missing_column_scored.csv")
_, reject_missing_outcome = process_file(
    reject_missing_item, edge_case_master, "reject_missing_column_scored", set()
)
check(
    "reject_missing_column_scored.csv: rejected / column mismatch",
    reject_missing_outcome.status == config.STATUS_REJECTED
    and reject_missing_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_missing_outcome),
)
check(
    "reject_missing_column_scored.csv: missing_cols == ['ABS_DIFF']",
    reject_missing_outcome.missing_cols == ["ABS_DIFF"],
    str(reject_missing_outcome.missing_cols),
)
check(
    "reject_missing_column_scored.csv: extra_cols == []",
    reject_missing_outcome.extra_cols == [],
    str(reject_missing_outcome.extra_cols),
)

reject_extra_item = _fixture_item("reject_extra_column_scored.csv")
_, reject_extra_outcome = process_file(
    reject_extra_item, edge_case_master, "reject_extra_column_scored", set()
)
check(
    "reject_extra_column_scored.csv: rejected / column mismatch",
    reject_extra_outcome.status == config.STATUS_REJECTED
    and reject_extra_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_extra_outcome),
)
check(
    "reject_extra_column_scored.csv: extra_cols == ['RETAILER_ID']",
    reject_extra_outcome.extra_cols == ["RETAILER_ID"],
    str(reject_extra_outcome.extra_cols),
)
check(
    "reject_extra_column_scored.csv: missing_cols == []",
    reject_extra_outcome.missing_cols == [],
    str(reject_extra_outcome.missing_cols),
)

reject_both_item = _fixture_item("reject_missing_and_extra_scored.csv")
_, reject_both_outcome = process_file(
    reject_both_item, edge_case_master, "reject_missing_and_extra_scored", set()
)
check(
    "reject_missing_and_extra_scored.csv: rejected / column mismatch",
    reject_both_outcome.status == config.STATUS_REJECTED
    and reject_both_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_both_outcome),
)
check(
    "reject_missing_and_extra_scored.csv: missing_cols == ['DOL_DIFF']",
    reject_both_outcome.missing_cols == ["DOL_DIFF"],
    str(reject_both_outcome.missing_cols),
)
check(
    "reject_missing_and_extra_scored.csv: extra_cols == ['BANNER', 'REGION'], each listed separately",
    reject_both_outcome.extra_cols == ["BANNER", "REGION"],
    str(reject_both_outcome.extra_cols),
)

# --- unrelated spreadsheet ----------------------------------------------------
reject_unrelated_item = _fixture_item("reject_unrelated_notes.csv")
_, reject_unrelated_outcome = process_file(
    reject_unrelated_item, edge_case_master, "reject_unrelated_notes", set()
)
check(
    "reject_unrelated_notes.csv: rejected (unrelated spreadsheet, column mismatch)",
    reject_unrelated_outcome.status == config.STATUS_REJECTED,
    str(reject_unrelated_outcome),
)

# --- zero-byte file ------------------------------------------------------------
reject_empty_item = _fixture_item("reject_empty_file_scored.csv")
_, reject_empty_outcome = process_file(
    reject_empty_item, edge_case_master, "reject_empty_file_scored", set()
)
check(
    "reject_empty_file_scored.csv: rejected / empty file (via process_file, not raised)",
    reject_empty_outcome.status == config.STATUS_REJECTED
    and reject_empty_outcome.reason == config.REASON_EMPTY_FILE,
    str(reject_empty_outcome),
)

# --- valid headers, zero data rows: skipped AND does not reserve its name ----
headers_only_item = _fixture_item("edge_headers_only_scored.csv", index=0)
real_bounty_item = UploadedItem(
    index=1, name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
shared_name_study_names = {0: "Shared_Study_Name", 1: "Shared_Study_Name"}
headers_only_result = process_batch(
    [headers_only_item, real_bounty_item], edge_case_master, shared_name_study_names
)
check(
    "edge_headers_only_scored.csv: skipped / no data rows",
    headers_only_result.outcomes[0].status == config.STATUS_SKIPPED
    and headers_only_result.outcomes[0].reason == config.REASON_NO_DATA_ROWS,
    str(headers_only_result.outcomes[0]),
)
check(
    "edge_headers_only_scored.csv does NOT reserve its Study_Name: a later real file "
    "with the same name still appends",
    headers_only_result.outcomes[1].status == config.STATUS_APPENDED,
    str(headers_only_result.outcomes[1]),
)

# --- REAL order test: step 5 (no data rows) must fire before step 6 (name
# collision). The block above never actually forces a collision — it calls
# process_batch with taken_names seeded empty, so the zero-row file's name
# was never "already taken" when step 6 ran. Here the collision is forced
# directly: process_file is called on the zero-row fixture with its own
# normalized study name PRE-SEEDED into taken_names, so the file is
# simultaneously zero-row AND a duplicate. If step 6 ran first, this would
# be skipped / already-in-master or duplicate-in-batch; the spec's fixed
# order (ARCHITECTURE.md study_processor.py step 5 before step 6) requires
# REASON_NO_DATA_ROWS instead.
order_test_study_name = "Order_Collision_Study"
order_test_taken = {order_test_study_name.strip().casefold()}
order_test_item = _fixture_item("edge_headers_only_scored.csv")
_, order_test_outcome = process_file(
    order_test_item, edge_case_master, order_test_study_name, order_test_taken
)
check(
    "REAL order test: zero-row file whose name is ALREADY in taken_names still reports "
    "skipped / no data rows (step 5 fires before step 6)",
    order_test_outcome.status == config.STATUS_SKIPPED
    and order_test_outcome.reason == config.REASON_NO_DATA_ROWS,
    str(order_test_outcome),
)

# --- complementary order test: step 1 (blank study name) must fire before
# step 2 (read_table). Garbage bytes built in memory (never written to disk)
# paired with a blank study name: if step 2 ran first, read_table would
# raise FileReadError and the outcome would be rejected / unreadable (or
# empty file, depending on what the garbage parses as). The fixed order
# requires REASON_BLANK_STUDY_NAME instead, because the study_name check
# never lets execution reach read_table at all.
garbage_bytes = b"\x00\x01\xff\xfe\x02\x03not,a,real\x00csv\xffheader\n\x01\x02"
garbage_item = UploadedItem(index=0, name="garbage_unreadable.csv", data=garbage_bytes)
_, garbage_blank_outcome = process_file(garbage_item, edge_case_master, "   ", set())
check(
    "REAL order test: unreadable garbage bytes + blank study name still reports "
    "rejected / blank study name (step 1 fires before step 2)",
    garbage_blank_outcome.status == config.STATUS_REJECTED
    and garbage_blank_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(garbage_blank_outcome),
)


# --- reordered / messy-case fixtures: append, every value character-identical
def _assert_values_identical(fixture_name: str, study_name: str) -> None:
    fixture_item = _fixture_item(fixture_name)
    original_df = read_table(fixture_name, fixture_item.data)
    aligned_df, outcome = process_file(fixture_item, edge_case_master, study_name, set())
    check(f"{fixture_name}: appended", outcome.status == config.STATUS_APPENDED, str(outcome))
    if aligned_df is None:
        check(f"{fixture_name}: value integrity (skipped, no frame)", False, "process_file returned None")
        return
    mismatches = []
    for col in original_df.columns:
        master_col = edge_case_master.column_index[normalize_column(col)]
        before = original_df[col].tolist()
        after = aligned_df[master_col].tolist()
        for row_idx, (b, a) in enumerate(zip(before, after)):
            if b != a:
                mismatches.append((row_idx, col, b, a))
    check(
        f"{fixture_name}: every value character-identical after align",
        len(mismatches) == 0,
        f"{len(mismatches)} mismatches, first: {mismatches[0]}" if mismatches else "",
    )
    check(
        f"{fixture_name}: Study_Name tagged correctly",
        (aligned_df[config.STUDY_NAME_COL] == study_name).all(),
    )


_assert_values_identical("pass_reordered_columns_scored.csv", "pass_reordered_columns_scored")
_assert_values_identical("pass_messy_header_case_scored.csv", "pass_messy_header_case_scored")

# --- blank study name rejects --------------------------------------------------
blank_name_item = UploadedItem(
    index=0, name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
_, blank_name_outcome = process_file(blank_name_item, edge_case_master, "   ", set())
check(
    "blank/whitespace-only study name: rejected / blank study name",
    blank_name_outcome.status == config.STATUS_REJECTED
    and blank_name_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(blank_name_outcome),
)
check(
    "blank study name is checked before the file is read: missing_cols/extra_cols stay []",
    blank_name_outcome.missing_cols == [] and blank_name_outcome.extra_cols == [],
)

# --- missing study_names entry defaults to blank, not to item.stem ----------
_, missing_key_outcome = process_file(blank_name_item, edge_case_master, {}.get(0, ""), set())
check(
    "study_processor never invents a stem fallback for a missing study name: "
    "an empty default is rejected exactly like an explicit blank",
    missing_key_outcome.status == config.STATUS_REJECTED
    and missing_key_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(missing_key_outcome),
)
missing_key_batch = process_batch(
    [blank_name_item], edge_case_master, {}  # deliberately no entry for index 0
)
check(
    "process_batch: a study_names dict missing an item's index defaults to '' "
    "(rejected / blank study name), never silently falls back to item.stem",
    missing_key_batch.outcomes[0].status == config.STATUS_REJECTED
    and missing_key_batch.outcomes[0].reason == config.REASON_BLANK_STUDY_NAME,
    str(missing_key_batch.outcomes[0]),
)

# --- duplicate columns within a study file reject ------------------------------
bounty_bytes = (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes()
bounty_text = bounty_bytes.decode("utf-8-sig")
bounty_rows_raw = list(csv.reader(_io.StringIO(bounty_text)))
bounty_header = bounty_rows_raw[0]
bounty_abs_diff_index = bounty_header.index("ABS_DIFF")
dup_col_header = bounty_header + ["Abs_Diff"]
dup_col_rows = [row + [row[bounty_abs_diff_index]] for row in bounty_rows_raw[1:]]
dup_col_output = _io.StringIO()
csv.writer(dup_col_output).writerows([dup_col_header] + dup_col_rows)
dup_col_bytes = dup_col_output.getvalue().encode("utf-8-sig")

dup_col_item = UploadedItem(index=0, name="Instacart_DupCols_scored.csv", data=dup_col_bytes)
_, dup_col_outcome = process_file(dup_col_item, edge_case_master, "Instacart_DupCols_scored", set())
check(
    "study file with duplicate normalized columns: rejected / duplicate columns",
    dup_col_outcome.status == config.STATUS_REJECTED
    and dup_col_outcome.reason == config.REASON_DUPLICATE_COLUMNS,
    str(dup_col_outcome),
)
check(
    "duplicate columns rejection leaves missing_cols/extra_cols empty (only step 4 populates them)",
    dup_col_outcome.missing_cols == [] and dup_col_outcome.extra_cols == [],
)

# ---------------------------------------------------------------------------
# SECTION 8 — Exception report and summary shape                 [Phase 4]
# ---------------------------------------------------------------------------
section("8. Exception Report and Summary Shape")

from report import outcomes_to_frame, build_exception_report, summarize

# --- a mixed outcome set covering appended / skipped / rejected -------------
sample_outcomes = [
    FileOutcome(
        file="ok_study.csv", index=0, status=config.STATUS_APPENDED, reason=config.REASON_NONE,
        missing_cols=[], extra_cols=[], study_name="Ok_Study", rows=10,
    ),
    FileOutcome(
        file="dup_study.csv", index=1, status=config.STATUS_SKIPPED, reason=config.REASON_ALREADY_IN_MASTER,
        missing_cols=[], extra_cols=[], study_name="Ok_Study", rows=0,
    ),
    FileOutcome(
        file="bad_study.csv", index=2, status=config.STATUS_REJECTED, reason=config.REASON_COLUMN_MISMATCH,
        missing_cols=["ABS_DIFF", "DOL_DIFF"], extra_cols=["RETAILER_ID"], study_name="Bad_Study", rows=0,
    ),
]

outcomes_frame = outcomes_to_frame(sample_outcomes)
check(
    "outcomes_to_frame: has the 7 documented columns, in order",
    list(outcomes_frame.columns)
    == ["file", "status", "reason", "study_name", "rows", "missing_cols", "extra_cols"],
    str(list(outcomes_frame.columns)),
)
check("outcomes_to_frame: one row per outcome", len(outcomes_frame) == 3, len(outcomes_frame))
check(
    "outcomes_to_frame: missing_cols joined with LIST_JOIN_SEPARATOR",
    outcomes_frame.loc[2, "missing_cols"] == config.LIST_JOIN_SEPARATOR.join(["ABS_DIFF", "DOL_DIFF"]),
    outcomes_frame.loc[2, "missing_cols"],
)

exception_frame = build_exception_report(sample_outcomes)
check(
    "build_exception_report: exactly config.EXCEPTION_REPORT_COLUMNS, in order",
    list(exception_frame.columns) == config.EXCEPTION_REPORT_COLUMNS,
    str(list(exception_frame.columns)),
)
check(
    "build_exception_report: only non-appended outcomes (2 of 3)",
    len(exception_frame) == 2,
    len(exception_frame),
)
check(
    "build_exception_report: contains no appended rows",
    (exception_frame["status"] != config.STATUS_APPENDED).all(),
)
check(
    "build_exception_report: extra_cols joined with LIST_JOIN_SEPARATOR",
    exception_frame.loc[exception_frame["file"] == "bad_study.csv", "extra_cols"].iloc[0] == "RETAILER_ID",
)

# --- empty exception report still carries the 5 columns ----------------------
all_appended_outcomes = [
    FileOutcome(
        file="a.csv", index=0, status=config.STATUS_APPENDED, reason=config.REASON_NONE,
        missing_cols=[], extra_cols=[], study_name="A", rows=5,
    ),
]
empty_exception_frame = build_exception_report(all_appended_outcomes)
check(
    "build_exception_report: empty frame (no exceptions) still has the 5 columns",
    list(empty_exception_frame.columns) == config.EXCEPTION_REPORT_COLUMNS,
    str(list(empty_exception_frame.columns)),
)
check("build_exception_report: empty frame has 0 rows", len(empty_exception_frame) == 0, len(empty_exception_frame))

# --- summarize: six keys, in display order, reconciling against a real result
summary = summarize(full_batch_result)
expected_summary_keys = [
    "Total files processed",
    "Files successfully appended",
    "Files skipped (already in master)",
    "Files rejected",
    "Records appended this run",
    "Total records in master",
]
check(
    "summarize: exactly the six documented keys, in display order",
    list(summary.keys()) == expected_summary_keys,
    str(list(summary.keys())),
)
check(
    "summarize: 'Total files processed' == appended + skipped + rejected",
    summary["Total files processed"]
    == summary["Files successfully appended"]
    + summary["Files skipped (already in master)"]
    + summary["Files rejected"],
    str(summary),
)
check(
    "summarize: counts reconcile against the full-batch BatchResult directly",
    summary["Total files processed"] == full_batch_result.total_files
    and summary["Files successfully appended"] == full_batch_result.appended
    and summary["Files skipped (already in master)"] == full_batch_result.skipped
    and summary["Files rejected"] == full_batch_result.rejected
    and summary["Records appended this run"] == full_batch_result.rows_appended
    and summary["Total records in master"] == full_batch_result.total_records,
    str(summary),
)
check(
    "summarize: 'Total records in master' == len(master_df)",
    summary["Total records in master"] == len(full_batch_result.master_df),
)

# --- Q16: the rejected-files banner (agreed 2026-09-29) ----------------------
from report import rejected_files_message

check(
    "rejected_files_message: '' when nothing is rejected (real 10-file batch)",
    rejected_files_message(full_batch_result.outcomes) == "",
    rejected_files_message(full_batch_result.outcomes),
)
_one_banner = rejected_files_message(sample_outcomes)
check(
    "rejected_files_message: one rejection -> exactly MSG_FILES_REJECTED_ONE with '`file` (reason)'",
    _one_banner == config.MSG_FILES_REJECTED_ONE.format(files="`bad_study.csv` (column mismatch)"),
    _one_banner,
)
check(
    "rejected_files_message: skipped and appended files are not listed",
    "ok_study.csv" not in _one_banner and "dup_study.csv" not in _one_banner,
    _one_banner,
)
# Two real fixture rejections (section 7), then a blank-name one, in outcome order.
_blank_outcome = FileOutcome(
    file="no_name.csv", index=9, status=config.STATUS_REJECTED, reason=config.REASON_BLANK_STUDY_NAME,
    missing_cols=[], extra_cols=[], study_name="", rows=0,
)
_many_outcomes = [reject_missing_outcome, sample_outcomes[0], reject_extra_outcome, _blank_outcome]
_many_banner = rejected_files_message(_many_outcomes)
_many_expected_files = ", ".join(
    f"`{o.file}` ({o.reason})" for o in (reject_missing_outcome, reject_extra_outcome, _blank_outcome)
)
check(
    "rejected_files_message: 3 rejections -> exactly MSG_FILES_REJECTED_MANY, n=3, files in outcome order",
    _many_banner == config.MSG_FILES_REJECTED_MANY.format(n=3, files=_many_expected_files),
    _many_banner,
)
check(
    "rejected_files_message: the count matches the 'Files rejected' rule (status == rejected)",
    sum(1 for o in _many_outcomes if o.status == config.STATUS_REJECTED) == 3
    and reject_missing_outcome.status == config.STATUS_REJECTED
    and reject_extra_outcome.status == config.STATUS_REJECTED,
)

# ---------------------------------------------------------------------------
# SECTION 9 — csv_writer.py and the Phase 5 QC checkpoint
# ---------------------------------------------------------------------------
section("9. csv_writer.py and Phase 5 QC Checkpoint")

from datetime import datetime as _datetime

from csv_writer import build_exception_filename, build_master_filename, to_csv_bytes

_FIXED_NOW = _datetime(2026, 9, 7, 14, 30)

check(
    "build_master_filename: exact pattern with an injected fixed 'now'",
    build_master_filename("Instacart", _FIXED_NOW) == "Master_File_Instacart_2026-09-07_1430.csv",
    build_master_filename("Instacart", _FIXED_NOW),
)
check(
    "build_exception_filename: exact pattern with an injected fixed 'now'",
    build_exception_filename("Instacart", _FIXED_NOW) == "Exceptions_Instacart_2026-09-07_1430.csv",
    build_exception_filename("Instacart", _FIXED_NOW),
)

# --- to_csv_bytes: UTF-8 BOM on a minimal frame -----------------------------
_bom_probe_df = pd.DataFrame({"A": ["1"], "B": ["2"]})
_bom_bytes = to_csv_bytes(_bom_probe_df)
check(
    "to_csv_bytes: output starts with the UTF-8 BOM",
    _bom_bytes[:3] == b"\xef\xbb\xbf",
    repr(_bom_bytes[:3]),
)

# --- grep-style check: no module other than app.py imports streamlit -------
_CODE_DIR = Path(__file__).resolve().parent
_non_app_streamlit_importers: list[str] = []
for _py_file in sorted(_CODE_DIR.glob("*.py")):
    if _py_file.name in ("app.py", "test_meta_pipeline.py"):
        continue
    _tree = ast.parse(_py_file.read_text(encoding="utf-8"))
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.Import) and any(
            "streamlit" in (alias.name or "") for alias in _node.names
        ):
            _non_app_streamlit_importers.append(_py_file.name)
        elif isinstance(_node, ast.ImportFrom) and _node.module and "streamlit" in _node.module:
            _non_app_streamlit_importers.append(_py_file.name)
check(
    "no module other than app.py imports streamlit",
    _non_app_streamlit_importers == [],
    str(_non_app_streamlit_importers),
)
check(
    "app.py itself does import streamlit (sanity — the grep check above isn't vacuous)",
    any(
        (isinstance(_node, ast.Import) and any("streamlit" in (a.name or "") for a in _node.names))
        or (isinstance(_node, ast.ImportFrom) and _node.module and "streamlit" in _node.module)
        for _node in ast.walk(ast.parse((_CODE_DIR / "app.py").read_text(encoding="utf-8")))
    ),
)

# --- Final end-to-end precision check ---------------------------------------
# Completes ARCHITECTURE.md section 5's QC CHECKPOINT steps 6-7, which
# Section 3 above deferred as a "[PHASE 5 STUB]" before csv_writer.py and
# study_processor.py existed. Runs Instacart_Bounty_scored.csv through the
# COMPLETE pipeline (read_table -> tag_study_name -> align_to_master, all
# inside process_batch -> to_csv_bytes), then decodes and re-parses the
# output bytes with the stdlib csv module and compares every field back
# against `raw_rows` (parsed directly from the source file in Section 3)
# character-by-character.
precision_master_item = UploadedItem(
    index=0, name=MASTER_FILE_NAME, data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
)
precision_master_ctx = build_master_context_from_existing(precision_master_item)

precision_bounty_item = UploadedItem(index=1, name=BOUNTY_FILE.name, data=BOUNTY_FILE.read_bytes())
precision_result = process_batch(
    [precision_bounty_item], precision_master_ctx, {1: precision_bounty_item.stem}
)
check(
    "precision checkpoint: Instacart_Bounty_scored.csv appended via the full pipeline",
    any(
        o.index == 1 and o.status == config.STATUS_APPENDED
        for o in precision_result.outcomes
    ),
    str([o for o in precision_result.outcomes if o.index == 1]),
)

precision_csv_bytes = to_csv_bytes(precision_result.master_df)
check(
    "precision checkpoint: to_csv_bytes(df)[:3] == UTF-8 BOM on the real consolidated master",
    precision_csv_bytes[:3] == b"\xef\xbb\xbf",
    repr(precision_csv_bytes[:3]),
)
check(
    "precision checkpoint: literal '0.19163628728414203' survives into the output bytes",
    b"0.19163628728414203" in precision_csv_bytes,
)

precision_text = precision_csv_bytes.decode(config.OUTPUT_ENCODING)
precision_output_rows = list(csv.DictReader(_io.StringIO(precision_text)))
precision_bounty_rows = [
    r for r in precision_output_rows if r[config.STUDY_NAME_COL] == precision_bounty_item.stem
]

check(
    "precision checkpoint: output row count for Bounty matches the source row count",
    len(precision_bounty_rows) == len(raw_rows),
    f"source={len(raw_rows)} output={len(precision_bounty_rows)}",
)

if len(precision_bounty_rows) == len(raw_rows):
    precision_mismatches: list[tuple[int, str, str, str]] = []
    for i, (raw_row, out_row) in enumerate(zip(raw_rows, precision_bounty_rows)):
        for col in REFERENCE_STUDY_COLUMNS:
            if raw_row[col] != out_row[col]:
                precision_mismatches.append((i, col, raw_row[col], out_row[col]))
    check(
        "precision checkpoint: every one of the 31 source columns is character-identical "
        "in the output, for every row (re-parsed with stdlib csv after the full pipeline "
        "and to_csv_bytes round-trip)",
        len(precision_mismatches) == 0,
        f"{len(precision_mismatches)} mismatches, first: {precision_mismatches[0]}"
        if precision_mismatches
        else "",
    )

    extra_field_sets = {
        frozenset(out_row.keys()) - frozenset(raw_rows[0].keys()) for out_row in precision_bounty_rows
    }
    missing_field_sets = {
        frozenset(raw_rows[0].keys()) - frozenset(out_row.keys()) for out_row in precision_bounty_rows
    }
    check(
        "precision checkpoint: Study_Name is the only field the output row has that the "
        "source row does not",
        extra_field_sets == {frozenset({config.STUDY_NAME_COL})},
        str(extra_field_sets),
    )
    check(
        "precision checkpoint: no source field was dropped in the output",
        missing_field_sets == {frozenset()},
        str(missing_field_sets),
    )
else:
    check("precision checkpoint: field-by-field comparison", False, "skipped — row counts did not match")

# ---------------------------------------------------------------------------
# SECTION 10 — Rule scans (Stage 1 — guards every later Phase 2 stage)
# ---------------------------------------------------------------------------
section("10. Rule Scans (AST)")

_PY_FILES = sorted(CODE_DIR.glob("*.py"))
_RULE4_EXEMPT = {"config.py", "test_meta_pipeline.py"}
_RULE2_TEST_INCLUDED = True  # rule 2 scans every file, including this one
_RULE3_EXEMPT = {"test_meta_pipeline.py"}
_OPENPYXL_ALLOWED = {"template_builder.py", "test_meta_pipeline.py"}


# --- Rule 4: column-name literals appear ONLY in config.py ------------------
def _rule4_hits(source: str, banned: set[str]) -> list[tuple[int, str]]:
    """Every ast.Constant str equal EXACTLY (case-sensitive) to a banned name,
    excluding bare string statements (docstrings: an ast.Expr whose value is
    that same Constant node).
    """
    tree = ast.parse(source)
    docstring_ids = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_ids
            and node.value in banned
        ):
            hits.append((node.lineno, node.value))
    return hits


_rule4_banned_names = (
    set(REFERENCE_STUDY_COLUMNS)
    | {config.STUDY_NAME_COL}
    | set(config.TEMPLATE_HEADERS)
    | set(config.CALCULATED_HEADERS)
    | set(config.LEGACY_CALCULATED_HEADERS)
)

for _py_file in _PY_FILES:
    if _py_file.name in _RULE4_EXEMPT:
        continue
    _hits = _rule4_hits(_py_file.read_text(encoding="utf-8"), _rule4_banned_names)
    check(
        f"rule 4: {_py_file.name} carries no column-name literal outside config.py",
        _hits == [],
        str(_hits),
    )

_rule4_config_hits = _rule4_hits(
    (CODE_DIR / "config.py").read_text(encoding="utf-8"), _rule4_banned_names
)
check(
    "rule 4 non-vacuity: the same scan run on config.py finds at least 5 hits",
    len(_rule4_config_hits) >= 5,
    str(len(_rule4_config_hits)),
)


# --- Rule 2: banned numeric-coercion constructs (CLAUDE.md rule 2) ----------
_RULE2_BANNED_ATTRS = {"to_numeric", "float64", "round"}
_RULE2_BANNED_NAMES = {"float", "round"}
_RULE2_BANNED_KEYWORDS = {"float_format", "converters", "parse_dates", "thousands", "decimal"}
_RULE2_READ_FUNCS = {"read_csv", "read_excel"}


def _rule2_hits(source: str) -> dict[str, list[int]]:
    tree = ast.parse(source)
    hits: dict[str, list[int]] = {
        "banned_attr_call": [],
        "banned_name_call": [],
        "astype_float": [],
        "banned_keyword": [],
        "read_missing_dtype_str": [],
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _RULE2_BANNED_ATTRS:
            hits["banned_attr_call"].append(node.lineno)
        if isinstance(func, ast.Name) and func.id in _RULE2_BANNED_NAMES:
            hits["banned_name_call"].append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr == "astype" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id == "float":
                hits["astype_float"].append(node.lineno)
            elif (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value.startswith("float")
            ):
                hits["astype_float"].append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr in _RULE2_READ_FUNCS:
            has_dtype_str = any(
                kw.arg == "dtype" and isinstance(kw.value, ast.Name) and kw.value.id == "str"
                for kw in node.keywords
            )
            if not has_dtype_str:
                hits["read_missing_dtype_str"].append(node.lineno)
        for kw in node.keywords:
            if kw.arg in _RULE2_BANNED_KEYWORDS:
                hits["banned_keyword"].append(node.lineno)
    return hits


for _py_file in _PY_FILES:
    _hits2 = _rule2_hits(_py_file.read_text(encoding="utf-8"))
    _flat_hits2 = [h for hits in _hits2.values() for h in hits]
    check(
        f"rule 2: {_py_file.name} carries no banned numeric-coercion construct",
        _flat_hits2 == [],
        str(_hits2) if _flat_hits2 else "",
    )

_RULE2_PROBE_SOURCE = '''
import pandas as pd

a = pd.to_numeric(x)
b = c.round()
d = float(y)
e = round(z)
f = df.astype(float)
g = df2.astype("float64")
h = pd.read_csv("f.csv", converters={})
i = pd.read_csv("g.csv", parse_dates=["d"])
j = pd.read_csv("h.csv", thousands=",")
k = pd.read_excel("i.xlsx", float_format="%.2f")
m = pd.read_csv("j.csv", decimal=",")
n = pd.read_csv("k.csv")
o = pd.read_csv("l.csv", dtype=str)
'''
_rule2_probe_hits = _rule2_hits(_RULE2_PROBE_SOURCE)
check(
    "rule 2 non-vacuity: a small in-memory source string containing each banned form "
    "yields at least one hit in every category",
    all(len(v) >= 1 for v in _rule2_probe_hits.values()),
    str(_rule2_probe_hits),
)


# --- Rule 3: no filesystem writes anywhere ----------------------------------
_RULE3_BANNED_ATTRS = {"write_text", "write_bytes", "to_excel", "mkdir", "makedirs"}


def _rule3_hits(source: str) -> list[int]:
    tree = ast.parse(source)
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            hits.append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr in _RULE3_BANNED_ATTRS:
            hits.append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr == "to_csv":
            has_positional = len(node.args) > 0
            has_path_kw = any(kw.arg == "path_or_buf" for kw in node.keywords)
            if has_positional or has_path_kw:
                hits.append(node.lineno)
        if isinstance(func, ast.Attribute) and func.attr == "save" and node.args:
            if not isinstance(node.args[0], ast.Name):
                hits.append(node.lineno)
    return hits


for _py_file in _PY_FILES:
    if _py_file.name in _RULE3_EXEMPT:
        continue
    _hits3 = _rule3_hits(_py_file.read_text(encoding="utf-8"))
    check(
        f"rule 3: {_py_file.name} performs no filesystem write",
        _hits3 == [],
        str(_hits3),
    )

_RULE3_PROBE_SOURCE = '''
f = open("x.txt", "w")
p.write_text("x")
q.write_bytes(b"x")
df.to_excel("out.xlsx")
os.mkdir("d")
os.makedirs("d")
df.to_csv("out.csv")
df.to_csv(path_or_buf="out.csv")
wb.save("out.xlsx")
wb.save(buf)
'''
_rule3_probe_hits = _rule3_hits(_RULE3_PROBE_SOURCE)
check(
    "rule 3 non-vacuity: a small in-memory source string containing each banned write form "
    "is caught (9 hits), and wb.save(buf) with a Name argument is correctly NOT flagged",
    len(_rule3_probe_hits) == 9,
    str(_rule3_probe_hits),
)


# --- openpyxl imported only by template_builder.py (and the test file) -----
def _imports_openpyxl(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            "openpyxl" in (alias.name or "") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module and "openpyxl" in node.module:
            return True
    return False


for _py_file in _PY_FILES:
    if _py_file.name in _OPENPYXL_ALLOWED:
        continue
    check(
        f"openpyxl import: {_py_file.name} does not import openpyxl",
        not _imports_openpyxl(_py_file.read_text(encoding="utf-8")),
    )

# ---------------------------------------------------------------------------
# SECTION 11 — Stage 1: master-only Run and P3 detection
# ---------------------------------------------------------------------------
section("11. Stage 1 — Master-Only Run and P3 Detection")

from study_processor import is_run_ready
from master_detector import first_master_slot_allowed
from schema import find_phase2_output_headers
from models import MasterCandidate

# --- is_run_ready truth table -----------------------------------------------
_existing_master_probe = _fresh_master()
_first_master_probe = build_master_context_from_first_file(
    UploadedItem(
        index=0, name="Instacart_Bounty_scored.csv",
        data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
    ),
    "Instacart",
)

_is_run_ready_cases = [
    (None, 0, False),
    (None, 3, False),
    (_existing_master_probe, 0, True),
    (_existing_master_probe, 2, True),
    (_first_master_probe, 0, False),
    (_first_master_probe, 1, True),
]
for _master_arg, _count_arg, _expected in _is_run_ready_cases:
    _label = (
        f"is_run_ready({'None' if _master_arg is None else ('existing' if not _master_arg.created_this_run else 'first-master')}, "
        f"{_count_arg}) == {_expected}"
    )
    check(_label, is_run_ready(_master_arg, _count_arg) is _expected)

# --- process_batch([master_item], existing_ctx, {}) with zero study items ---
# The master item's index must match master.source_index for process_batch's
# structural skip (item.index == master.source_index) to exclude it — hence
# building the context from THIS item, not via _fresh_master()'s index=999.
_zero_study_master_item = UploadedItem(
    index=0, name=MASTER_FILE_NAME, data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
)
_zero_study_master = build_master_context_from_existing(_zero_study_master_item)
_zero_study_result = process_batch([_zero_study_master_item], _zero_study_master, {})
check(
    "process_batch with zero study items: appended == 0",
    _zero_study_result.appended == 0,
    _zero_study_result.appended,
)
check(
    "process_batch with zero study items: outcomes == []",
    _zero_study_result.outcomes == [],
    str(_zero_study_result.outcomes),
)
check(
    "process_batch with zero study items: total_records == 52",
    _zero_study_result.total_records == 52,
    _zero_study_result.total_records,
)
check(
    "process_batch with zero study items: master_df equal cell-for-cell to the source master frame",
    _zero_study_result.master_df.equals(_zero_study_master.frame),
)

_zero_study_excluded_outcome = FileOutcome(
    file="Master_Unselected.csv", index=1, status=config.STATUS_SKIPPED,
    reason=config.REASON_NOT_SELECTED_MASTER, missing_cols=[], extra_cols=[], study_name="", rows=0,
)
_zero_study_result_with_excluded = process_batch(
    [_zero_study_master_item], _zero_study_master, {}, excluded_outcomes=[_zero_study_excluded_outcome]
)
check(
    "process_batch with zero study items + an unselected-master excluded_outcome: "
    "outcomes == [that outcome]",
    _zero_study_result_with_excluded.outcomes == [_zero_study_excluded_outcome],
    str(_zero_study_result_with_excluded.outcomes),
)
check(
    "process_batch with zero study items + an unselected-master excluded_outcome: skipped == 1",
    _zero_study_result_with_excluded.skipped == 1,
    _zero_study_result_with_excluded.skipped,
)

# --- find_phase2_output_headers ----------------------------------------------
check(
    "find_phase2_output_headers([]) on the real master's columns is []",
    find_phase2_output_headers(list(_zero_study_master.frame.columns)) == [],
    str(find_phase2_output_headers(list(_zero_study_master.frame.columns))),
)
for _study_name in STUDY_FILES:
    _study_df = read_table(_study_name, (SAMPLES_DIR / _study_name).read_bytes())
    _hits_study = find_phase2_output_headers(list(_study_df.columns))
    check(
        f"find_phase2_output_headers([]) on {_study_name}'s columns is []",
        _hits_study == [],
        str(_hits_study),
    )

_calc_header_variants = [
    list(config.CALCULATED_HEADERS),
    [h + "​" for h in config.CALCULATED_HEADERS],
    [h.upper() for h in config.CALCULATED_HEADERS],
]
for _variant in _calc_header_variants:
    check(
        f"find_phase2_output_headers detects all {len(config.CALCULATED_HEADERS)} calculated headers "
        f"(variant: {_variant[0]!r})",
        find_phase2_output_headers(_variant) == _variant,
        str(find_phase2_output_headers(_variant)),
    )

check(
    "find_phase2_output_headers detects the legacy Instacart header",
    find_phase2_output_headers(list(config.LEGACY_CALCULATED_HEADERS))
    == list(config.LEGACY_CALCULATED_HEADERS),
)
check(
    "find_phase2_output_headers detects a merged template header (Read_Type)",
    find_phase2_output_headers([config.TEMPLATE_READ_TYPE]) == [config.TEMPLATE_READ_TYPE],
)

# --- synthetic Master_File_Test: real master + calculated headers ----------
_synthetic_master_df = _zero_study_master.frame.copy()
for _i, _header in enumerate(config.CALCULATED_HEADERS):
    _synthetic_master_df[_header] = ""
_synthetic_master_bytes = to_csv_bytes(_synthetic_master_df)
_synthetic_master_name = "Master_File_Test_2026-09-28_1200.csv"
_synthetic_master_item = UploadedItem(index=0, name=_synthetic_master_name, data=_synthetic_master_bytes)

_synthetic_candidates = find_master_candidates([_synthetic_master_item])
check(
    "synthetic Master_File_Test: find_master_candidates gives is_phase2_output True",
    len(_synthetic_candidates) == 1 and _synthetic_candidates[0].is_phase2_output is True,
    str(_synthetic_candidates),
)
check(
    "synthetic Master_File_Test: is_valid False, readable True",
    len(_synthetic_candidates) == 1
    and _synthetic_candidates[0].is_valid is False
    and _synthetic_candidates[0].readable is True,
    str(_synthetic_candidates),
)

try:
    build_master_context_from_existing(_synthetic_master_item)
    check("synthetic Master_File_Test: build_master_context_from_existing raises SchemaError", False)
except SchemaError as e:
    check(
        "synthetic Master_File_Test: build_master_context_from_existing raises "
        "SchemaError(REASON_PHASE2_OUTPUT) with MSG_PHASE2_OUTPUT",
        e.reason == config.REASON_PHASE2_OUTPUT and str(e) == config.MSG_PHASE2_OUTPUT,
        f"reason={e.reason!r} str={str(e)!r}",
    )
except Exception as e:
    check(
        "synthetic Master_File_Test: build_master_context_from_existing raises SchemaError",
        False, f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    build_master_context_from_first_file(_synthetic_master_item, "Test")
    check("synthetic Master_File_Test: build_master_context_from_first_file raises SchemaError", False)
except SchemaError as e:
    check(
        "synthetic Master_File_Test: build_master_context_from_first_file raises "
        "SchemaError(REASON_PHASE2_OUTPUT) with MSG_PHASE2_OUTPUT",
        e.reason == config.REASON_PHASE2_OUTPUT and str(e) == config.MSG_PHASE2_OUTPUT,
        f"reason={e.reason!r} str={str(e)!r}",
    )
except Exception as e:
    check(
        "synthetic Master_File_Test: build_master_context_from_first_file raises SchemaError",
        False, f"wrong exception type: {type(e).__name__}: {e}",
    )

check(
    "first_master_slot_allowed is False when the synthetic Phase 2 output candidate is present",
    first_master_slot_allowed(_synthetic_candidates) is False,
)
check(
    "first_master_slot_allowed is True for an ordinary candidate list",
    first_master_slot_allowed(
        [MasterCandidate(index=0, name="Master_X.csv", readable=True, has_study_name=True, error="")]
    )
    is True,
)

# --- process_file on the synthetic bytes as a study: REASON_PHASE2_OUTPUT --
_synthetic_as_study_item = UploadedItem(index=0, name="Study_Test.csv", data=_synthetic_master_bytes)
_, _synthetic_study_outcome = process_file(
    _synthetic_as_study_item, edge_case_master, "Study_Test", set()
)
check(
    "process_file on Phase 2 output bytes as a study: rejected / REASON_PHASE2_OUTPUT",
    _synthetic_study_outcome.status == config.STATUS_REJECTED
    and _synthetic_study_outcome.reason == config.REASON_PHASE2_OUTPUT,
    str(_synthetic_study_outcome),
)
check(
    "process_file on Phase 2 output bytes as a study: missing_cols == extra_cols == []",
    _synthetic_study_outcome.missing_cols == [] and _synthetic_study_outcome.extra_cols == [],
)

# --- order tests --------------------------------------------------------------
# calculated headers + a duplicate column -> duplicate columns (step 3 before 3b)
_dup_plus_calc_df = _synthetic_master_df.copy()
_dup_plus_calc_df["MODEL_DESC_DUP_PROBE"] = _dup_plus_calc_df["MODEL_DESC"]
_dup_plus_calc_bytes_frame = _dup_plus_calc_df.rename(
    columns={"MODEL_DESC_DUP_PROBE": "Model_Desc"}
)
_dup_plus_calc_bytes = to_csv_bytes(_dup_plus_calc_bytes_frame)
_dup_plus_calc_item = UploadedItem(index=0, name="Study_DupPlusCalc.csv", data=_dup_plus_calc_bytes)
_, _dup_plus_calc_outcome = process_file(
    _dup_plus_calc_item, edge_case_master, "Study_DupPlusCalc", set()
)
check(
    "order test: calculated headers + a duplicate column gives REASON_DUPLICATE_COLUMNS "
    "(step 3 fires before step 3b)",
    _dup_plus_calc_outcome.status == config.STATUS_REJECTED
    and _dup_plus_calc_outcome.reason == config.REASON_DUPLICATE_COLUMNS,
    str(_dup_plus_calc_outcome),
)

# calculated headers + a missing master column -> REASON_PHASE2_OUTPUT (3b before 4)
_missing_plus_calc_df = _synthetic_master_df.drop(columns=["ABS_DIFF"])
_missing_plus_calc_bytes = to_csv_bytes(_missing_plus_calc_df)
_missing_plus_calc_item = UploadedItem(
    index=0, name="Study_MissingPlusCalc.csv", data=_missing_plus_calc_bytes
)
_, _missing_plus_calc_outcome = process_file(
    _missing_plus_calc_item, edge_case_master, "Study_MissingPlusCalc", set()
)
check(
    "order test: calculated headers + a missing master column gives REASON_PHASE2_OUTPUT "
    "(step 3b fires before step 4)",
    _missing_plus_calc_outcome.status == config.STATUS_REJECTED
    and _missing_plus_calc_outcome.reason == config.REASON_PHASE2_OUTPUT,
    str(_missing_plus_calc_outcome),
)

print(
    "\n[NOTE] Regression: every existing Phase 1 fixture keeps its status and reason — "
    "asserted implicitly by Sections 4-9 above passing unchanged."
)

# ---------------------------------------------------------------------------
# SECTION 12 — Stage 2: template (PHASE2_ARCHITECTURE.md section 10.3)
# ---------------------------------------------------------------------------
section("12. Stage 2 — Template")

import io as _io_s12
from datetime import datetime as _datetime_s12
from decimal import Decimal

import openpyxl as _openpyxl_s12

from numeric import NotANumber, format_number, format_rounded, is_plain_number, parse_number
from template_builder import build_template_bytes, list_template_studies
from csv_writer import build_template_filename

# --- numeric.format_number (10.4 first bullet, applies to Stage 2) ----------
_format_number_cases = [
    ("500.0", "500"),
    ("2.4E+6", "2400000"),
    ("1E-7", "0.0000001"),
    ("-0.0", "0"),
    ("0.000100", "0.0001"),
    ("438486.7835619480", "438486.783561948"),
]
for _src, _expected in _format_number_cases:
    _got = format_number(Decimal(_src))
    check(f"format_number(Decimal({_src!r})) == {_expected!r}", _got == _expected, _got)

# --- numeric.parse_number ----------------------------------------------------
check(
    "parse_number(' 1.5 ') == Decimal('1.5')",
    parse_number(" 1.5 ") == Decimal("1.5"),
    str(parse_number(" 1.5 ")),
)
check("parse_number('') is None", parse_number("") is None)
check("parse_number('  ') is None", parse_number("  ") is None)

# Section 7.4's warn list — every one must raise NotANumber via parse_number,
# and is_plain_number must be False for every one of them.
_numeric_warn_examples = [
    "1,500", "$3.49", "25%", "abc", "+5", "1.2.3", "3,49", "NaN", "inf", "1 000",
]
for _bad in _numeric_warn_examples:
    try:
        parse_number(_bad)
        check(f"parse_number({_bad!r}) raises NotANumber", False, "no exception was raised")
    except NotANumber as e:
        check(
            f"parse_number({_bad!r}) raises NotANumber(.text == stripped input)",
            e.text == _bad.strip(),
            e.text,
        )
    except Exception as e:
        check(
            f"parse_number({_bad!r}) raises NotANumber",
            False,
            f"wrong exception type: {type(e).__name__}: {e}",
        )
    check(f"is_plain_number({_bad!r}) is False", is_plain_number(_bad) is False)

# Section 7.4's accept list — is_plain_number True, parse_number succeeds.
_numeric_accept_examples = ["3.49", "-2", "1500000", "1.2E+06", "0.25", ".5", "5.", "1e-07", " 3.49 "]
for _good in _numeric_accept_examples:
    check(f"is_plain_number({_good!r}) is True", is_plain_number(_good) is True)
    try:
        parse_number(_good)
        check(f"parse_number({_good!r}) does not raise", True)
    except Exception as e:
        check(f"parse_number({_good!r}) does not raise", False, f"{type(e).__name__}: {e}")

# --- numeric.format_rounded ---------------------------------------------------
_format_rounded_cases = [
    ("1.945", "1.95"),
    ("2", "2.00"),
    ("-0.001", "0.00"),
    ("1.005", "1.01"),
]
for _src, _expected in _format_rounded_cases:
    _got = format_rounded(Decimal(_src), config.AM_ROUND_QUANTUM)
    check(
        f"format_rounded(Decimal({_src!r}), '0.01') == {_expected!r}",
        _got == _expected,
        _got,
    )

# --- template_builder.list_template_studies: hand-built case (P5) ------------
_list_probe_df = pd.DataFrame(
    {config.STUDY_NAME_COL: ["B", "A", "B", " A", "", "  ", "a", "=SUM(1)", "00123"]}
)
_expected_list_probe = ["B", "A", " A", "a", "=SUM(1)", "00123"]
check(
    "list_template_studies: exact-string distinct, first-appearance order, "
    "blank-after-strip excluded",
    list_template_studies(_list_probe_df) == _expected_list_probe,
    str(list_template_studies(_list_probe_df)),
)

# --- list_template_studies: real sample master -------------------------------
check(
    "list_template_studies on the real sample master gives ['Holly_Rancher 27382_Scored']",
    list_template_studies(master_df) == ["Holly_Rancher 27382_Scored"],
    str(list_template_studies(master_df)),
)

# --- list_template_studies: full-batch master (Section 6) lists 10 names ----
# Independent oracle (plain dict.fromkeys over the master column, not the
# function under test) so this is not circular.
_expected_full_batch_names = [
    name
    for name in dict.fromkeys(full_batch_result.master_df[config.STUDY_NAME_COL].tolist())
    if name.strip() != ""
]
check(
    "list_template_studies on the full-batch master (Section 6) lists 10 names, "
    "in first-appearance order",
    list_template_studies(full_batch_result.master_df) == _expected_full_batch_names
    and len(_expected_full_batch_names) == 10,
    str(list_template_studies(full_batch_result.master_df)),
)

# --- build_template_bytes: structural checks (reloaded with openpyxl) -------
_template_names = list_template_studies(master_df)
_template_bytes = build_template_bytes(_template_names)
check(
    "build_template_bytes returns bytes starting with b'PK'",
    _template_bytes[:2] == b"PK",
    _template_bytes[:4],
)

_reloaded_wb = _openpyxl_s12.load_workbook(_io_s12.BytesIO(_template_bytes))
check(
    "reloaded workbook sheetnames == [TEMPLATE_SHEET_TITLE, GLOSSARY_SHEET_TITLE]",
    _reloaded_wb.sheetnames == [config.TEMPLATE_SHEET_TITLE, config.GLOSSARY_SHEET_TITLE],
    str(_reloaded_wb.sheetnames),
)
_reloaded_ws = _reloaded_wb[config.TEMPLATE_SHEET_TITLE]
_n_names = len(_template_names)

_reloaded_header_row = [
    _reloaded_ws.cell(row=1, column=c).value for c in range(1, len(config.TEMPLATE_HEADERS) + 1)
]
check(
    "reloaded template: row 1 == TEMPLATE_HEADERS",
    _reloaded_header_row == list(config.TEMPLATE_HEADERS),
    str(_reloaded_header_row),
)
check(
    "reloaded template: row 1 is bold",
    all(
        _reloaded_ws.cell(row=1, column=c).font.bold
        for c in range(1, len(config.TEMPLATE_HEADERS) + 1)
    ),
)

check(
    "reloaded template: A2.. are the study names verbatim",
    [_reloaded_ws.cell(row=r, column=1).value for r in range(2, _n_names + 2)] == _template_names,
    str([_reloaded_ws.cell(row=r, column=1).value for r in range(2, _n_names + 2)]),
)
check(
    "reloaded template: A2.. have data_type 's' (text, not formula/number)",
    all(_reloaded_ws.cell(row=r, column=1).data_type == "s" for r in range(2, _n_names + 2)),
)

check(
    "reloaded template: B..G body cells are empty",
    all(
        _reloaded_ws.cell(row=r, column=c).value is None
        for r in range(2, _n_names + 2)
        for c in range(2, len(config.TEMPLATE_HEADERS) + 1)
    ),
)

check("reloaded template: protection.sheet is True", _reloaded_ws.protection.sheet is True)
check(
    "reloaded template: protection.password is falsy (no password set)",
    not _reloaded_ws.protection.password,
    repr(_reloaded_ws.protection.password),
)

check(
    "reloaded template: column A cells are locked (default)",
    all(
        _reloaded_ws.cell(row=r, column=1).protection.locked is True
        for r in range(1, _n_names + 2)
    ),
)
check(
    "reloaded template: B1:G{n+1} are unlocked",
    all(
        _reloaded_ws.cell(row=r, column=c).protection.locked is False
        for r in range(1, _n_names + 2)
        for c in range(2, len(config.TEMPLATE_HEADERS) + 1)
    ),
)

_col_e_dim = _reloaded_ws.column_dimensions["E"]
check(
    "reloaded template: column E dimension min==5, max==16384, unlocked",
    _col_e_dim.min == 5
    and _col_e_dim.max == config.XLSX_MAX_COLUMN
    and _col_e_dim.protection.locked is False,
    f"min={_col_e_dim.min} max={_col_e_dim.max} locked={_col_e_dim.protection.locked}",
)
_col_d_dim = _reloaded_ws.column_dimensions["D"]
check(
    "reloaded template: column D dimension has the percent number format",
    _col_d_dim.number_format == config.PCT_NUMBER_FORMAT,
    _col_d_dim.number_format,
)
check(
    "reloaded template: freeze_panes == 'A2'",
    _reloaded_ws.freeze_panes == "A2",
    _reloaded_ws.freeze_panes,
)

_reloaded_glossary = _reloaded_wb[config.GLOSSARY_SHEET_TITLE]
check(
    "reloaded glossary: row 1 == GLOSSARY_FIELDS_TITLE",
    _reloaded_glossary.cell(row=1, column=1).value == config.GLOSSARY_FIELDS_TITLE,
)
check(
    "reloaded glossary: row 2 == GLOSSARY_FIELD_COLUMNS",
    [_reloaded_glossary.cell(row=2, column=c).value for c in range(1, 5)]
    == list(config.GLOSSARY_FIELD_COLUMNS),
)
_glossary_field_rows_ok = all(
    [_reloaded_glossary.cell(row=3 + i, column=c).value for c in range(1, 5)] == list(row)
    for i, row in enumerate(config.GLOSSARY_FIELD_ROWS)
)
check("reloaded glossary: rows 3-9 == GLOSSARY_FIELD_ROWS", _glossary_field_rows_ok)
check(
    "reloaded glossary: row 11/12 == extras title/text",
    _reloaded_glossary.cell(row=11, column=1).value == config.GLOSSARY_EXTRAS_TITLE
    and _reloaded_glossary.cell(row=12, column=1).value == config.GLOSSARY_EXTRAS_TEXT,
)
check(
    "reloaded glossary: row 14 + rows 15-18 == rules title/list",
    _reloaded_glossary.cell(row=14, column=1).value == config.GLOSSARY_RULES_TITLE
    and [
        _reloaded_glossary.cell(row=15 + i, column=1).value
        for i in range(len(config.GLOSSARY_RULES))
    ]
    == [f"- {r}" for r in config.GLOSSARY_RULES],
)

# --- study name with XML-illegal control characters (P2-29 / template_builder
# module docstring FINDING): openpyxl 3.1.5 raises IllegalCharacterError on a
# raw assignment instead of silently stripping (verified against the
# installed openpyxl below), so template_builder._strip_illegal_xml_chars must
# pre-empt it. build_template_bytes must not raise, and the stored cell value
# must be the stripped name, differing from the master's original — which is
# exactly what makes the P2-29 downstream mismatch warnings fire in Stage 4.
_illegal_name = "Bad\x0bName\x00Study"
_illegal_bytes = build_template_bytes([_illegal_name])
check(
    "build_template_bytes does not raise on a study name with XML-illegal "
    "control characters",
    _illegal_bytes[:2] == b"PK",
    _illegal_bytes[:4],
)
_illegal_reloaded = _openpyxl_s12.load_workbook(_io_s12.BytesIO(_illegal_bytes))
_illegal_cell_value = _illegal_reloaded[config.TEMPLATE_SHEET_TITLE]["A2"].value
check(
    "template A2 stores the XML-illegal-stripped name, not the master's "
    "original verbatim value (P2-29: this mismatch is what makes the "
    "downstream warnings fire, not silence)",
    _illegal_cell_value == "BadNameStudy" and _illegal_cell_value != _illegal_name,
    repr(_illegal_cell_value),
)
_openpyxl_raises_on_raw_illegal_assignment = False
try:
    _probe_wb = _openpyxl_s12.Workbook()
    _probe_wb.active["A1"] = _illegal_name
except Exception:
    _openpyxl_raises_on_raw_illegal_assignment = True
check(
    "non-vacuity: the installed openpyxl really does raise on a raw illegal "
    "assignment (confirms the mitigation is needed, not defensive-only)",
    _openpyxl_raises_on_raw_illegal_assignment,
)

# --- round trip: read_table sees the template's headers/names verbatim ------
_template_read_df = read_table("t.xlsx", _template_bytes)
check(
    "read_table(template) columns == TEMPLATE_HEADERS verbatim",
    list(_template_read_df.columns) == list(config.TEMPLATE_HEADERS),
    str(list(_template_read_df.columns)),
)
check(
    "read_table(template) Study_Name values verbatim",
    _template_read_df[config.STUDY_NAME_COL].tolist() == _template_names,
    str(_template_read_df[config.STUDY_NAME_COL].tolist()),
)

# --- round trip (Stage 4): read_raw_grid / parse_upload on the template -----
from file_reader import read_raw_grid as _read_raw_grid_s12
from metadata_upload import parse_upload as _parse_upload_s12

_template_grid = _read_raw_grid_s12("t.xlsx", _template_bytes)
check(
    "read_raw_grid(template) header row == TEMPLATE_HEADERS verbatim",
    _template_grid[0] == list(config.TEMPLATE_HEADERS),
    str(_template_grid[0]),
)

_template_parsed = _parse_upload_s12("t.xlsx", _template_bytes, list(master_df.columns))
check(
    "parse_upload(template) is accepted with 0 warnings",
    _template_parsed.accepted and _template_parsed.warnings == [],
    f"accepted={_template_parsed.accepted} warnings={_template_parsed.warnings}",
)

# --- csv_writer.build_template_filename --------------------------------------
_fixed_now_s12 = _datetime_s12(2026, 9, 28, 14, 30)
check(
    "build_template_filename('Instacart', fixed_now) == "
    "'studyname_master_Instacart_2026-09-28_1430.xlsx'",
    build_template_filename("Instacart", _fixed_now_s12)
    == "studyname_master_Instacart_2026-09-28_1430.xlsx",
    build_template_filename("Instacart", _fixed_now_s12),
)

# ---------------------------------------------------------------------------
# SECTION 13a — Stage 3: calculations, layer 1 (synthetic, always runs)
# (PHASE2_ARCHITECTURE.md section 10.4)
# ---------------------------------------------------------------------------
section("13a. Stage 3 — Calculations, Layer 1 (Synthetic)")

import decimal
import re as _re_s13

from calculations import build_calculations
import numeric

_SYNTH_COLUMNS: list[str] = [
    config.STUDY_NAME_COL,
    config.MODEL_DESC_COL,
    config.MODEL_COL,
    config.DEPENDENT_VARIABLE_COL,
    config.CNT_EXPSD_HH_COL,
    config.ADJ_MEAN_EXPSD_GRP_COL,
    "RowId",
]


def _synth_row(study: str, model_desc: str, model: str, dep_var: str, g: str, n: str, row_id: str) -> dict:
    return {
        config.STUDY_NAME_COL: study,
        config.MODEL_DESC_COL: model_desc,
        config.MODEL_COL: model,
        config.DEPENDENT_VARIABLE_COL: dep_var,
        config.CNT_EXPSD_HH_COL: g,
        config.ADJ_MEAN_EXPSD_GRP_COL: n,
        "RowId": row_id,
    }


def _synth_master(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=_SYNTH_COLUMNS).astype(str)


def _exact_product_str(*texts: str) -> str:
    """Independent integer-arithmetic oracle — does NOT use Decimal. Splits
    each decimal string into an (int coefficient, scale) pair, multiplies the
    integer coefficients, adds the scales, places the decimal point, and
    strips representation-only trailing zeros. Not circular: numeric.py's
    format_number/multiply are never called here.
    """
    sign = 1
    coefficient_product = 1
    scale_total = 0
    for text in texts:
        t = text.strip()
        if t.startswith("-"):
            sign = -sign
            t = t[1:]
        elif t.startswith("+"):
            t = t[1:]
        if "e" in t or "E" in t:
            mantissa, exponent_text = _re_s13.split("[eE]", t)
            exponent = int(exponent_text)
        else:
            mantissa, exponent = t, 0
        int_part, _, frac_part = mantissa.partition(".")
        digits = (int_part + frac_part) or "0"
        coefficient = int(digits)
        scale = len(frac_part) - exponent
        coefficient_product *= coefficient
        scale_total += scale
    digits_str = str(coefficient_product)
    if scale_total <= 0:
        result = digits_str + "0" * (-scale_total)
    else:
        if len(digits_str) <= scale_total:
            digits_str = "0" * (scale_total - len(digits_str) + 1) + digits_str
        result = digits_str[:-scale_total] + "." + digits_str[-scale_total:]
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if result in ("", "-", "0"):
        result = "0"
    elif sign < 0:
        result = "-" + result
    return result


# non-vacuity: the oracle reproduces the section 2.4 worked example independently
check(
    "_exact_product_str('0.036091684','12149247') == '438486.783561948' "
    "(oracle non-vacuity, section 2.4 worked example)",
    _exact_product_str("0.036091684", "12149247") == "438486.783561948",
    _exact_product_str("0.036091684", "12149247"),
)

# --- clean block (pen N=0.5; occ N=2; dolocc N=9; dolhh N=3.25, G=1000) -----
_clean_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1000", "3.25", "r4"),
]
_clean_master = _synth_master(_clean_rows)
_clean_result = build_calculations(_clean_master)

check(
    "clean block: frame columns == CALCULATED_HEADERS",
    list(_clean_result.frame.columns) == list(config.CALCULATED_HEADERS),
    str(list(_clean_result.frame.columns)),
)
check("clean block: frame length == master length", len(_clean_result.frame) == 4, len(_clean_result.frame))
check("clean block: zero warnings", _clean_result.warnings == [], str(_clean_result.warnings))
check(
    "clean block: every cell is a Python str",
    all(isinstance(v, str) for v in _clean_result.frame.to_numpy().ravel()),
)
check(
    "clean block: Total Analyzed Population == '1000' on dolhh (row 3)",
    _clean_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3] == "1000",
    _clean_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3],
)
check(
    "clean block: Count of Circana Buyers == '500' on pen (row 0)",
    _clean_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == "500",
    _clean_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
)
check(
    "clean block: Partner Member Overlap == '0.5' on pen (row 0)",
    _clean_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.5",
    _clean_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0],
)
check(
    "clean block: Dollars spent ... by HH == '3.25' on dolhh (row 3)",
    _clean_result.frame[config.CALC_DOLLARS_PER_HH].iloc[3] == "3.25",
    _clean_result.frame[config.CALC_DOLLARS_PER_HH].iloc[3],
)
check(
    "clean block: Total Dollars spent ... == '3250' on dolhh (row 3)",
    _clean_result.frame[config.CALC_TOTAL_DOLLARS].iloc[3] == "3250",
    _clean_result.frame[config.CALC_TOTAL_DOLLARS].iloc[3],
)
check(
    "clean block: Total Buying Trips == '1000' on pen (row 0)",
    _clean_result.frame[config.CALC_TOTAL_TRIPS].iloc[0] == "1000",
    _clean_result.frame[config.CALC_TOTAL_TRIPS].iloc[0],
)
check(
    "clean block: Trips per Buyer == '2' on occ (row 1)",
    _clean_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "2",
    _clean_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1],
)
check(
    "clean block: Offline column blank on every row",
    (_clean_result.frame[config.CALC_OFFLINE_NEW_BUYERS] == "").all(),
)
check(
    "clean block: dolocc row (row 2) fully blank across all 8 columns",
    all(_clean_result.frame[h].iloc[2] == "" for h in config.CALCULATED_HEADERS),
)
check(
    "blank G on the pen row (row 0) produces no warning: already proven by "
    "the zero-warnings check above, since row 0's CNT_EXPSD_HH is blank and unused",
    _clean_result.warnings == [],
)

# --- casing: 'Pen', ' OCC ', 'DolHH' give identical output ------------------
_casing_rows = [
    _synth_row("S1", "MD1", "M1", "Pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", " OCC ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "DolHH", "1000", "3.25", "r4"),
]
_casing_result = build_calculations(_synth_master(_casing_rows))
check(
    "casing: 'Pen'/' OCC '/'DolHH' produce identical output to the clean block",
    [_casing_result.frame[h].tolist() for h in config.CALCULATED_HEADERS]
    == [_clean_result.frame[h].tolist() for h in config.CALCULATED_HEADERS],
    str([_casing_result.frame[h].tolist() for h in config.CALCULATED_HEADERS]),
)
check("casing: zero warnings", _casing_result.warnings == [], str(_casing_result.warnings))

# --- shuffle: two interleaved blocks in scrambled order ----------------------
_block_a = [
    _synth_row("S1", "MDA", "MA", "pen", "", "0.5", "a1"),
    _synth_row("S1", "MDA", "MA", "occ", "", "2", "a2"),
    _synth_row("S1", "MDA", "MA", "dolocc", "", "9", "a3"),
    _synth_row("S1", "MDA", "MA", "dolhh", "1000", "3.25", "a4"),
]
_block_b = [
    _synth_row("S2", "MDB", "MB", "pen", "", "0.25", "b1"),
    _synth_row("S2", "MDB", "MB", "occ", "", "4", "b2"),
    _synth_row("S2", "MDB", "MB", "dolocc", "", "1", "b3"),
    _synth_row("S2", "MDB", "MB", "dolhh", "2000", "10", "b4"),
]
_ordered_rows = _block_a + _block_b
_shuffled_rows = [
    _block_a[3], _block_b[1], _block_a[0], _block_b[3],
    _block_a[2], _block_b[0], _block_a[1], _block_b[2],
]

_ordered_master = _synth_master(_ordered_rows)
_shuffled_master = _synth_master(_shuffled_rows)
_ordered_result = build_calculations(_ordered_master)
_shuffled_result = build_calculations(_shuffled_master)


def _by_row_id(master: pd.DataFrame, result) -> dict:
    mapping: dict[str, dict[str, str]] = {}
    row_ids = master["RowId"].tolist()
    for header in config.CALCULATED_HEADERS:
        values = result.frame[header].tolist()
        for i, rid in enumerate(row_ids):
            mapping.setdefault(rid, {})[header] = values[i]
    return mapping


_mapped_ordered = _by_row_id(_ordered_master, _ordered_result)
_mapped_shuffled = _by_row_id(_shuffled_master, _shuffled_result)
check(
    "shuffle: two interleaved blocks in scrambled order produce identical "
    "values mapped back by RowId",
    _mapped_ordered == _mapped_shuffled,
    "" if _mapped_ordered == _mapped_shuffled else f"ordered={_mapped_ordered} shuffled={_mapped_shuffled}",
)

# --- broken blocks: missing occ ----------------------------------------------
_missing_occ_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1000", "3.25", "r4"),
]
_missing_occ_result = build_calculations(_synth_master(_missing_occ_rows))
check(
    "broken block (missing occ): Count of Circana Buyers blank",
    _missing_occ_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == "",
)
check(
    "broken block (missing occ): Total Buying Trips blank",
    _missing_occ_result.frame[config.CALC_TOTAL_TRIPS].iloc[0] == "",
)
check(
    "broken block (missing occ): single-row columns still computed "
    "(Partner Member Overlap on pen, Total Analyzed Population on dolhh)",
    _missing_occ_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.5"
    and _missing_occ_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[2] == "1000",
)
check(
    "broken block (missing occ): exactly one block_role_missing warning",
    len(_missing_occ_result.warnings) == 1
    and _missing_occ_result.warnings[0].code == config.P2W_BLOCK_ROLE_MISSING,
    str(_missing_occ_result.warnings),
)
check(
    "broken block (missing occ): warning names the missing role",
    "'occ'" in _missing_occ_result.warnings[0].issue,
    _missing_occ_result.warnings[0].issue,
)

# --- broken blocks: duplicated pen -------------------------------------------
_dup_pen_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "pen", "", "0.75", "r1b"),
    _synth_row("S1", "MD1", "M1", "occ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1000", "3.25", "r4"),
]
_dup_pen_result = build_calculations(_synth_master(_dup_pen_rows))
check(
    "broken block (duplicated pen): both pen rows get their own Partner Member Overlap",
    _dup_pen_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.5"
    and _dup_pen_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[1] == "0.75",
)
check(
    "broken block (duplicated pen): cross-row columns blank",
    _dup_pen_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == ""
    and _dup_pen_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[1] == ""
    and _dup_pen_result.frame[config.CALC_TOTAL_TRIPS].iloc[0] == ""
    and _dup_pen_result.frame[config.CALC_TOTAL_TRIPS].iloc[1] == "",
)
check(
    "broken block (duplicated pen): exactly one block_role_duplicated warning",
    len(_dup_pen_result.warnings) == 1
    and _dup_pen_result.warnings[0].code == config.P2W_BLOCK_ROLE_DUPLICATED,
    str(_dup_pen_result.warnings),
)

# --- broken blocks: dolocc-only block ----------------------------------------
_dolocc_only_rows = [
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r1"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "8", "r2"),
]
_dolocc_only_result = build_calculations(_synth_master(_dolocc_only_rows))
check(
    "dolocc-only block: one warning naming all three roles",
    len(_dolocc_only_result.warnings) == 1
    and _dolocc_only_result.warnings[0].code == config.P2W_BLOCK_ROLE_MISSING
    and all(f"'{r}'" in _dolocc_only_result.warnings[0].issue for r in ("pen", "occ", "dolhh")),
    str(_dolocc_only_result.warnings),
)
check(
    "dolocc-only block: every calculated cell blank",
    all(_dolocc_only_result.frame[h].iloc[i] == "" for h in config.CALCULATED_HEADERS for i in (0, 1)),
)

# --- missing source columns ---------------------------------------------------
_drop_g_master = _clean_master.drop(columns=[config.CNT_EXPSD_HH_COL])
_drop_g_result = build_calculations(_drop_g_master)
check(
    "drop CNT_EXPSD_HH: exactly one source_column_missing naming CNT_EXPSD_HH",
    len(_drop_g_result.warnings) == 1
    and _drop_g_result.warnings[0].code == config.P2W_SOURCE_COLUMN_MISSING
    and _drop_g_result.warnings[0].column == config.CNT_EXPSD_HH_COL,
    str(_drop_g_result.warnings),
)
check(
    "drop CNT_EXPSD_HH: the 4 G-dependent columns are blank everywhere",
    all(
        (_drop_g_result.frame[h] == "").all()
        for h in (
            config.CALC_TOTAL_ANALYZED_POPULATION,
            config.CALC_COUNT_CIRCANA_BUYERS,
            config.CALC_TOTAL_DOLLARS,
            config.CALC_TOTAL_TRIPS,
        )
    ),
)
check(
    "drop CNT_EXPSD_HH: the other 3 columns still compute",
    _drop_g_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.5"
    and _drop_g_result.frame[config.CALC_DOLLARS_PER_HH].iloc[3] == "3.25"
    and _drop_g_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "2",
)

_drop_f_master = _clean_master.drop(columns=[config.DEPENDENT_VARIABLE_COL])
_drop_f_result = build_calculations(_drop_f_master)
check(
    "drop dependent_variable: everything blank, one warning",
    len(_drop_f_result.warnings) == 1
    and _drop_f_result.warnings[0].code == config.P2W_SOURCE_COLUMN_MISSING
    and _drop_f_result.warnings[0].column == config.DEPENDENT_VARIABLE_COL
    and all((_drop_f_result.frame[h] == "").all() for h in config.CALCULATED_HEADERS),
    str(_drop_f_result.warnings),
)

_drop_model_master = _clean_master.drop(columns=[config.MODEL_COL])
_drop_model_result = build_calculations(_drop_model_master)
check(
    "drop Model: cross-row columns blank, single-row columns computed, one warning",
    len(_drop_model_result.warnings) == 1
    and _drop_model_result.warnings[0].code == config.P2W_SOURCE_COLUMN_MISSING
    and _drop_model_result.warnings[0].column == config.MODEL_COL
    and (_drop_model_result.frame[config.CALC_COUNT_CIRCANA_BUYERS] == "").all()
    and (_drop_model_result.frame[config.CALC_TOTAL_TRIPS] == "").all()
    and _drop_model_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.5"
    and _drop_model_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3] == "1000",
    str(_drop_model_result.warnings),
)

_rename_g_master = _clean_master.rename(columns={config.CNT_EXPSD_HH_COL: config.CNT_EXPSD_HH_COL.lower()})
_rename_g_result = build_calculations(_rename_g_master)
check(
    "rename CNT_EXPSD_HH to lowercase: still found (identical results to the clean block)",
    _rename_g_result.warnings == []
    and [_rename_g_result.frame[h].tolist() for h in config.CALCULATED_HEADERS]
    == [_clean_result.frame[h].tolist() for h in config.CALCULATED_HEADERS],
    str(_rename_g_result.warnings),
)

# --- problem cells -------------------------------------------------------------
_blank_g_rows = [dict(r) for r in _clean_rows]
_blank_g_rows[3] = dict(_blank_g_rows[3])
_blank_g_rows[3][config.CNT_EXPSD_HH_COL] = ""
_blank_g_result = build_calculations(_synth_master(_blank_g_rows))
check(
    "blank G on dolhh: 4 columns blank",
    _blank_g_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3] == ""
    and _blank_g_result.frame[config.CALC_TOTAL_DOLLARS].iloc[3] == ""
    and _blank_g_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == ""
    and _blank_g_result.frame[config.CALC_TOTAL_TRIPS].iloc[0] == "",
)
check(
    "blank G on dolhh: exactly one value_blank warning listing all 4 headers, {row} correct",
    len(_blank_g_result.warnings) == 1
    and _blank_g_result.warnings[0].code == config.P2W_VALUE_BLANK
    and _blank_g_result.warnings[0].column == config.CNT_EXPSD_HH_COL
    and all(
        h in _blank_g_result.warnings[0].issue
        for h in (
            config.CALC_TOTAL_ANALYZED_POPULATION,
            config.CALC_COUNT_CIRCANA_BUYERS,
            config.CALC_TOTAL_DOLLARS,
            config.CALC_TOTAL_TRIPS,
        )
    )
    and "row 5" in _blank_g_result.warnings[0].issue,
    str(_blank_g_result.warnings),
)

_bad_n_rows = [dict(r) for r in _clean_rows]
_bad_n_rows[0] = dict(_bad_n_rows[0])
_bad_n_rows[0][config.ADJ_MEAN_EXPSD_GRP_COL] = "abc"
_bad_n_result = build_calculations(_synth_master(_bad_n_rows))
check(
    "'abc' in N on pen: one value_not_numeric warning",
    len(_bad_n_result.warnings) == 1 and _bad_n_result.warnings[0].code == config.P2W_VALUE_NOT_NUMERIC,
    str(_bad_n_result.warnings),
)

# --- exactness (literal strings) ----------------------------------------------
_exactness_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.036091684", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "1.9454682413648197", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "12149247", "3.25", "r4"),
]
_exactness_result = build_calculations(_synth_master(_exactness_rows))
check(
    "exactness: 0.036091684 x 12149247 == '438486.783561948' (Count of Circana Buyers)",
    _exactness_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == "438486.783561948",
    _exactness_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
)
check(
    "exactness: Total Analyzed Population from '12149247' == '12149247'",
    _exactness_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3] == "12149247",
    _exactness_result.frame[config.CALC_TOTAL_ANALYZED_POPULATION].iloc[3],
)
check(
    "exactness: Partner Member Overlap from '0.036091684' unchanged",
    _exactness_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0] == "0.036091684",
    _exactness_result.frame[config.CALC_PARTNER_MEMBER_OVERLAP].iloc[0],
)
check(
    "exactness: Trips per Buyer full precision == '1.9454682413648197'",
    _exactness_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "1.9454682413648197",
    _exactness_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1],
)

_second_exactness_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.03609168443151368", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "1.9454682413648197", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "12149247.0", "3.25", "r4"),
]
_second_exactness_result = build_calculations(_synth_master(_second_exactness_rows))
check(
    "exactness: 0.03609168443151368 x 12149247.0 == '438486.78880451428219896'",
    _second_exactness_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0]
    == "438486.78880451428219896",
    _second_exactness_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
)

_e_notation_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "5E-1", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1.0E+3", "3.25", "r4"),
]
_e_notation_result = build_calculations(_synth_master(_e_notation_rows))
check(
    "exactness: 5E-1 x 1.0E+3 == '500' (Count of Circana Buyers)",
    _e_notation_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == "500",
    _e_notation_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
)

# --- triple product: matches the independent oracle, differs from a 28-digit context
_triple_a = "0.03609168443151368"
_triple_b = "12149247.0"
_triple_c = "1.9454682413648197"
_triple_oracle = _exact_product_str(_triple_a, _triple_b, _triple_c)
_triple_app = numeric.format_number(
    numeric.multiply(decimal.Decimal(_triple_a), decimal.Decimal(_triple_b), decimal.Decimal(_triple_c))
)
check(
    "triple product matches the independent integer-arithmetic oracle",
    _triple_app == _triple_oracle,
    f"app={_triple_app} oracle={_triple_oracle}",
)
_context28 = decimal.Context(prec=28, rounding=decimal.ROUND_HALF_EVEN)
_triple_28 = _context28.multiply(
    _context28.multiply(decimal.Decimal(_triple_a), decimal.Decimal(_triple_b)), decimal.Decimal(_triple_c)
)
_triple_28_str = numeric.format_number(_triple_28)
check(
    "triple product under a 28-digit context differs from the app's 100-digit result "
    "(proves the default context is not used)",
    _triple_28_str != _triple_app,
    f"28-digit={_triple_28_str} app={_triple_app}",
)

# --- AM flag -------------------------------------------------------------------
_am_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "1.9454682413648197", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1000", "3.25", "r4"),
]
_am_default_result = build_calculations(_synth_master(_am_rows))
check(
    "AM flag: default (am_round_2dp=None) gives full precision",
    _am_default_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "1.9454682413648197",
    _am_default_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1],
)
_am_true_result = build_calculations(_synth_master(_am_rows), am_round_2dp=True)
check(
    "AM flag: am_round_2dp=True rounds '1.9454682413648197' -> '1.95'",
    _am_true_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "1.95",
    _am_true_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1],
)
_am_two_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", "1000", "3.25", "r4"),
]
_am_two_result = build_calculations(_synth_master(_am_two_rows), am_round_2dp=True)
check(
    "AM flag: am_round_2dp=True on '2' -> '2.00'",
    _am_two_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1] == "2.00",
    _am_two_result.frame[config.CALC_TRIPS_PER_BUYER].iloc[1],
)

# --- hygiene -------------------------------------------------------------------
check(
    "hygiene: decimal.getcontext().prec == 28 after every calculations call "
    "(the thread-local global context is never touched)",
    decimal.getcontext().prec == 28,
    decimal.getcontext().prec,
)
_pre_call_copy = _clean_master.copy(deep=True)
build_calculations(_clean_master)
check(
    "hygiene: master_df equals a pre-call deep copy (never mutated)",
    _clean_master.equals(_pre_call_copy),
)

# --- Inexact path (P2-20 / P2W_VALUE_TOO_PRECISE) coverage gap flagged by QC --
# A clean 4-row block where N(dolhh) and G(dolhh) are both 55-digit repunits:
# their exact product needs 110 significant digits, none of them trailing
# zeros, so ARITH_CONTEXT's Inexact trap actually fires (unlike the earlier
# "1 followed by 60 zeros" case, where dropped digits are all zero and are
# therefore NOT Inexact under decimal's rules). Only Total Dollars spent (the
# one column that multiplies N(dolhh) x G(dolhh)) is affected; the pen/occ
# operands stay small so Count of Circana Buyers and Total Buying Trips
# compute normally, giving exactly one warning in total.
_precise_big = "1" * 55
_too_precise_rows = [
    _synth_row("S1", "MD1", "M1", "pen", "", "0.5", "r1"),
    _synth_row("S1", "MD1", "M1", "occ", "", "2", "r2"),
    _synth_row("S1", "MD1", "M1", "dolocc", "", "9", "r3"),
    _synth_row("S1", "MD1", "M1", "dolhh", _precise_big, _precise_big, "r4"),
]
_too_precise_result = build_calculations(_synth_master(_too_precise_rows))
check(
    "Inexact path: Total Dollars spent is blank when the exact product needs "
    "more than 100 significant digits",
    _too_precise_result.frame[config.CALC_TOTAL_DOLLARS].iloc[3] == "",
    _too_precise_result.frame[config.CALC_TOTAL_DOLLARS].iloc[3],
)
check(
    "Inexact path: exactly one value_too_precise warning, naming the output column",
    len(_too_precise_result.warnings) == 1
    and _too_precise_result.warnings[0].code == config.P2W_VALUE_TOO_PRECISE
    and _too_precise_result.warnings[0].column == config.CALC_TOTAL_DOLLARS,
    str(_too_precise_result.warnings),
)
check(
    "Inexact path: the other two multiplied columns (small operands) still compute",
    _too_precise_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] != ""
    and _too_precise_result.frame[config.CALC_TOTAL_TRIPS].iloc[0] != "",
    str(
        (
            _too_precise_result.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
            _too_precise_result.frame[config.CALC_TOTAL_TRIPS].iloc[0],
        )
    ),
)

# --- real-sample anchor (Samples/) --------------------------------------------
_real_calc = build_calculations(master_df)
check(
    "real-sample anchor: zero calculation warnings on the real sample master",
    _real_calc.warnings == [],
    str(_real_calc.warnings),
)
check(
    "real-sample anchor: Count of Circana Buyers row 0 == '438486.783561948'",
    _real_calc.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0] == "438486.783561948",
    _real_calc.frame[config.CALC_COUNT_CIRCANA_BUYERS].iloc[0],
)

# ---------------------------------------------------------------------------
# SECTION 13b — Stage 3: calculations, layer 2 (reference-workbook comparison)
# (PHASE2_ARCHITECTURE.md section 10.5)
# ---------------------------------------------------------------------------
section("13b. Stage 3 — Calculations, Layer 2 (Reference Workbook)")

_WORKBOOK_PATH = ROOT / "Phase 2 process" / "master_file_w_calculations.xlsx"
_WORKBOOK_SHEET = "MaserFile_from STEP4 (2)"

if not _WORKBOOK_PATH.exists():
    skip(
        "Layer 2 (reference workbook comparison)",
        f"SKIPPED — reference workbook not found: {_WORKBOOK_PATH}",
    )
else:
    _layer2_ready = True
    try:
        _wb_bytes = _WORKBOOK_PATH.read_bytes()
        _wb_frame_raw = pd.read_excel(
            _io_s12.BytesIO(_wb_bytes), sheet_name=_WORKBOOK_SHEET, dtype=str
        ).fillna("")
        _wb_openpyxl = _openpyxl_s12.load_workbook(_io_s12.BytesIO(_wb_bytes), data_only=True)
        _wb_sheet_cells = _wb_openpyxl[_WORKBOOK_SHEET]
    except Exception as e:
        skip(
            "Layer 2 (reference workbook comparison)",
            f"SKIPPED — reference workbook not found or unreadable: {_WORKBOOK_PATH} ({e})",
        )
        _layer2_ready = False

    if _layer2_ready:
        import random as _random_s13b

        check("layer 2: workbook has 212 data rows", len(_wb_frame_raw) == 212, len(_wb_frame_raw))

        _wb_headers_first32 = [str(h).strip() for h in _wb_frame_raw.columns[:32]]
        _expected_first32 = REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL]
        check(
            "layer 2: first 32 stripped headers == REFERENCE_STUDY_COLUMNS + [Study_Name]",
            _wb_headers_first32 == _expected_first32,
            "" if _wb_headers_first32 == _expected_first32 else str(_wb_headers_first32),
        )

        from schema import normalize_header as _normalize_header_s13b

        _calc_signature_keys = {_normalize_header_s13b(h) for h in config.CALCULATED_HEADERS[:7]} | {
            _normalize_header_s13b(config.LEGACY_CALCULATED_HEADERS[0])
        }
        _wb_headers_32_39 = [str(h).strip() for h in _wb_frame_raw.columns[32:39]]
        check(
            "layer 2: headers at positions 32-38 match the first 7 CALCULATED_HEADERS "
            "under normalize_header (legacy Instacart name accepted)",
            all(_normalize_header_s13b(h) in _calc_signature_keys for h in _wb_headers_32_39),
            str(_wb_headers_32_39),
        )

        _wb_study_col = _wb_frame_raw.columns[31]
        _wb_study_order: list[str] = []
        _wb_study_counts: dict[str, int] = {}
        for _v in _wb_frame_raw[_wb_study_col]:
            if _v not in _wb_study_counts:
                _wb_study_counts[_v] = 0
                _wb_study_order.append(_v)
            _wb_study_counts[_v] += 1
        check(
            "layer 2: per-study row counts in first-appearance order == [52, 80, 80]",
            [_wb_study_counts[s] for s in _wb_study_order] == [52, 80, 80],
            str([(s, _wb_study_counts[s]) for s in _wb_study_order]),
        )

        # --- build the master realistically, from the workbook's own A-AF values
        from csv_writer import to_csv_bytes

        _wb_master_bytes = to_csv_bytes(_wb_frame_raw.iloc[:, :32])
        _wb_master_item = UploadedItem(
            index=0, name="Master_Reference_2026-09-28_0000.csv", data=_wb_master_bytes
        )
        _wb_master_ctx = build_master_context_from_existing(_wb_master_item)
        _wb_batch_result = process_batch([_wb_master_item], _wb_master_ctx, {})
        _wb_calc = build_calculations(_wb_batch_result.master_df)
        check(
            "layer 2: zero calculation warnings on the reference master",
            _wb_calc.warnings == [],
            str(_wb_calc.warnings),
        )

        # --- columns AG-AL (6): every non-blank Excel cell agrees to within ONE
        # fixed relative tolerance; Excel blank <-> app blank ------------------------
        # Ruling 2026-09-28 (Marcos, option B): the previous C7 mechanism re-derived
        # the "correct" pen/dolhh/occ operand cells independently of whatever the
        # app actually output for a given cell, then asked only "does some rounding
        # of those operands explain Excel's cached value?" — never "does the app's
        # own value agree?". QC proved this was a real hole, not just a generous
        # tolerance: three deliberately-wrong variants (a product using the wrong
        # operand row, a product missing a multiplication factor, and an arbitrary
        # constant unrelated to any operand) were ALL "accepted" by the old
        # mechanism on every one of their 53 non-blank cells. It is replaced here
        # with a single fixed relative tolerance checked directly against the app's
        # own output, with no special-casing and no operand reconstruction.
        _LAYER2_RELATIVE_TOLERANCE = decimal.Decimal("1e-13")  # see QC report: the
        # measured worst-case relative error across all 318 compared cells is
        # ~1.116e-14 (Excel's text-to-number coercion of inputs it stores as
        # >15-significant-digit text). 1e-13 keeps roughly a full order of
        # magnitude of margin above that measured worst case.

        _agal_headers = config.CALCULATED_HEADERS[:6]
        _n_master_col = _wb_master_ctx.column_index[normalize_column(config.ADJ_MEAN_EXPSD_GRP_COL)]
        _n_col_idx0 = list(_wb_batch_result.master_df.columns).index(_n_master_col)

        # Informational only (no acceptance logic depends on this): how many
        # ADJ_MEAN_EXPSD_GRP cells the workbook stores as text, which is why some
        # cells sit near the tolerance boundary (Excel's text-to-number coercion).
        _text_stored_count = sum(
            1
            for _r in range(212)
            if _wb_sheet_cells.cell(row=_r + 2, column=_n_col_idx0 + 1).data_type == "s"
        )
        print(f"[INFO] {config.ADJ_MEAN_EXPSD_GRP_COL} text-stored cells (data_type == 's'): {_text_stored_count}")

        _real_failures: list[tuple] = []
        _nonblank_total = 0
        _worst_relative_error = decimal.Decimal(0)
        for _h_idx, _header in enumerate(_agal_headers):
            _excel_values = _wb_frame_raw.iloc[:, 32 + _h_idx].tolist()
            _app_values = _wb_calc.frame[_header].tolist()
            _nonblank_this_col = 0
            for _row_i in range(212):
                _excel_raw = _excel_values[_row_i].strip()
                _app_raw = _app_values[_row_i].strip()
                if _excel_raw == "":
                    if _app_raw != "":
                        _real_failures.append((_header, _row_i, "excel blank, app non-blank", _app_raw))
                    continue
                _nonblank_this_col += 1
                _nonblank_total += 1
                try:
                    _excel_dec = decimal.Decimal(_excel_raw)
                except decimal.InvalidOperation:
                    _real_failures.append((_header, _row_i, "excel value unparseable", _excel_raw))
                    continue
                if _app_raw == "":
                    _real_failures.append((_header, _row_i, "excel non-blank, app blank", _excel_raw))
                    continue
                _app_dec = decimal.Decimal(_app_raw)
                _diff = abs(_app_dec - _excel_dec)
                if _excel_dec == 0:
                    _rel_error = _diff  # absolute fallback; not expected in this data
                    _tolerance = _LAYER2_RELATIVE_TOLERANCE
                else:
                    _rel_error = _diff / abs(_excel_dec)
                    _tolerance = _LAYER2_RELATIVE_TOLERANCE * abs(_excel_dec)
                if _rel_error > _worst_relative_error:
                    _worst_relative_error = _rel_error
                if _diff > _tolerance:
                    _real_failures.append(
                        (_header, _row_i, "value mismatch beyond tolerance", (_app_raw, _excel_raw))
                    )
            check(
                f"layer 2: {_header!r} has 53 non-blank Excel values",
                _nonblank_this_col == 53,
                _nonblank_this_col,
            )

        check(
            f"layer 2: AG-AL — every cell agrees within a single fixed relative "
            f"tolerance of {_LAYER2_RELATIVE_TOLERANCE} (no special-casing)",
            _real_failures == [],
            str(_real_failures[:10]),
        )
        print(f"[INFO] worst observed relative error across AG-AL: {_worst_relative_error}")

        # --- AM: app value rounds to Excel's text; am_round_2dp=True matches exactly
        _am_header = config.CALCULATED_HEADERS[6]
        _am_excel_values = _wb_frame_raw.iloc[:, 32 + 6].tolist()
        _am_app_values = _wb_calc.frame[_am_header].tolist()
        _am_mismatches = []
        for _row_i in range(212):
            _excel_raw = _am_excel_values[_row_i].strip()
            _app_raw = _am_app_values[_row_i].strip()
            if _excel_raw == "":
                if _app_raw != "":
                    _am_mismatches.append((_row_i, "excel blank, app non-blank"))
                continue
            if _app_raw == "":
                _am_mismatches.append((_row_i, "excel non-blank, app blank"))
                continue
            _rounded = numeric.format_rounded(decimal.Decimal(_app_raw), config.AM_ROUND_QUANTUM)
            if _rounded != _excel_raw:
                _am_mismatches.append((_row_i, (_rounded, _excel_raw)))
        check(
            "layer 2 AM: app's full value rounds (ROUND_HALF_UP to 0.01) to Excel's text",
            _am_mismatches == [],
            str(_am_mismatches[:10]),
        )

        _wb_calc_rounded = build_calculations(_wb_batch_result.master_df, am_round_2dp=True)
        _am_app_rounded_values = _wb_calc_rounded.frame[_am_header].tolist()
        _am_rounded_mismatches = [
            _row_i
            for _row_i in range(212)
            if _am_excel_values[_row_i].strip() != ""
            and _am_app_rounded_values[_row_i].strip() != _am_excel_values[_row_i].strip()
        ]
        check(
            "layer 2 AM: am_round_2dp=True output equals Excel's text exactly",
            _am_rounded_mismatches == [],
            str(_am_rounded_mismatches[:10]),
        )

        check(
            "layer 2: Offline column blank on all 212 rows",
            (_wb_calc.frame[config.CALC_OFFLINE_NEW_BUYERS] == "").all(),
        )

        # --- shuffled rerun: string-identical results and warnings ------------------
        _perm = list(range(212))
        _random_s13b.Random(20260928).shuffle(_perm)
        _shuffled_master_df = _wb_batch_result.master_df.iloc[_perm].reset_index(drop=True)
        _shuffled_calc = build_calculations(_shuffled_master_df)

        _unpermuted = {header: [""] * 212 for header in config.CALCULATED_HEADERS}
        for _new_pos, _orig_pos in enumerate(_perm):
            for header in config.CALCULATED_HEADERS:
                _unpermuted[header][_orig_pos] = _shuffled_calc.frame[header].iloc[_new_pos]
        _shuffle_identical = all(
            _unpermuted[header] == _wb_calc.frame[header].tolist() for header in config.CALCULATED_HEADERS
        )
        check(
            "layer 2: shuffled rerun is string-identical to the unshuffled output "
            "once un-permuted",
            _shuffle_identical,
        )
        check(
            "layer 2: shuffled rerun produces the same number of warnings",
            len(_shuffled_calc.warnings) == len(_wb_calc.warnings),
            f"shuffled={len(_shuffled_calc.warnings)} original={len(_wb_calc.warnings)}",
        )

        # --- structural cross-check vs Samples/ -------------------------------------
        _cross_check_files = [
            "Holly_Rancher 27382_Scored.csv",
            "Instacart_Cascade_scored.csv",
            "Instacart_Bel Brands_scored.csv",
        ]
        _cross_check_frames = [
            read_table(name, (SAMPLES_DIR / name).read_bytes()) for name in _cross_check_files
        ]
        _cross_check_concat = pd.concat(_cross_check_frames, ignore_index=True)
        _cross_check_keys = list(
            zip(
                _cross_check_concat[config.MODEL_DESC_COL],
                _cross_check_concat[config.MODEL_COL],
                _cross_check_concat[config.DEPENDENT_VARIABLE_COL],
            )
        )
        _wb_keys = list(
            zip(
                _wb_frame_raw[config.MODEL_DESC_COL],
                _wb_frame_raw[config.MODEL_COL],
                _wb_frame_raw[config.DEPENDENT_VARIABLE_COL],
            )
        )
        check(
            "layer 2: (MODEL_DESC, Model, dependent_variable) sequence matches the "
            "workbook's 212-row sequence, built from Samples/ in the declared order",
            _cross_check_keys == _wb_keys,
            "" if _cross_check_keys == _wb_keys else "sequences differ",
        )

        _rounding_diff_count = 0
        for _idx in range(min(len(_cross_check_concat), len(_wb_frame_raw))):
            for _col in (config.CNT_EXPSD_HH_COL, config.ADJ_MEAN_EXPSD_GRP_COL):
                _source_val = _cross_check_concat.iloc[_idx][_col].strip()
                _wb_val = _wb_frame_raw.iloc[_idx][_col].strip()
                if _source_val != "" and _wb_val != "":
                    try:
                        if decimal.Decimal(_source_val) != decimal.Decimal(_wb_val):
                            _rounding_diff_count += 1
                    except decimal.InvalidOperation:
                        _rounding_diff_count += 1
        print(
            f"[INFO] N/G cells whose Decimal value differs between the workbook and "
            f"Samples/ (documents the Excel rounding motivating the C1 input decision): "
            f"{_rounding_diff_count}"
        )

        print(
            f"LAYER 2 RAN — 212 rows, 7 columns, {_nonblank_total} non-blank cells compared, "
            f"worst relative error {_worst_relative_error}, tolerance {_LAYER2_RELATIVE_TOLERANCE}"
        )

# ---------------------------------------------------------------------------
# SECTION 14 — Stage 4: upload validation, merge, warnings
# (PHASE2_ARCHITECTURE.md section 10.6)
# ---------------------------------------------------------------------------
section("14. Stage 4 — Upload Validation, Merge, Warnings")

from file_reader import read_raw_grid
from metadata_upload import parse_upload
from final_builder import build_final
from report import phase2_warnings_to_frame, summarize_phase2_warnings
from csv_writer import (
    build_final_filename,
    build_phase2_warnings_filename,
    to_csv_bytes as _to_csv_bytes_s14,
)
from models import CalculationResult, Phase2Warning

_S14_MASTER_COLUMNS = MASTER_COLUMNS


def _s14_csv_bytes(rows: list[list[str]]) -> bytes:
    buf = _io_s12.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _s14_blank_calc(n: int) -> CalculationResult:
    frame = pd.DataFrame(
        {h: [""] * n for h in config.CALCULATED_HEADERS},
        columns=list(config.CALCULATED_HEADERS),
        dtype=object,
    )
    return CalculationResult(frame=frame, warnings=[])


def _s14_codes(warnings: list[Phase2Warning]) -> list[str]:
    return [w.code for w in warnings]


# --- read_raw_grid --------------------------------------------------------
_grid_unmangled_bytes = _s14_csv_bytes(
    [["Study_Name", "Brand", "Brand", ""], ["S1", "x", "y", "z"]]
)
_grid_unmangled = read_raw_grid("g.csv", _grid_unmangled_bytes)
check(
    "read_raw_grid: CSV 'Study_Name,Brand,Brand,' keeps Brand, Brand, '' unmangled "
    "(no pandas 'Unnamed:'/'.1' renaming, since header=None)",
    _grid_unmangled[0] == ["Study_Name", "Brand", "Brand", ""],
    str(_grid_unmangled[0]),
)

_grid_wb = _openpyxl_s12.Workbook()
_grid_ws = _grid_wb.active
for _c, _h in enumerate(["Study_Name", "B", "C", "D", "E", "F", "G", "", ], start=1):
    _grid_ws.cell(row=1, column=_c, value=_h if _h != "" else None)
_grid_ws.cell(row=2, column=8, value="h2value")
_grid_buf = _io_s12.BytesIO()
_grid_wb.save(_grid_buf)
_grid_h1_blank = read_raw_grid("g.xlsx", _grid_buf.getvalue())
check(
    "read_raw_grid: xlsx with an empty H1 but a value in H2 gives '' at header index 7",
    _grid_h1_blank[0][7] == "" and _grid_h1_blank[1][7] == "h2value",
    str((_grid_h1_blank[0][7], _grid_h1_blank[1][7])),
)

try:
    read_raw_grid("empty.csv", b"")
    check("read_raw_grid: zero-byte input raises FileReadError", False, "no exception was raised")
except FileReadError as e:
    check(
        "read_raw_grid: zero-byte input raises FileReadError(REASON_EMPTY_FILE)",
        e.reason == config.REASON_EMPTY_FILE,
        e.reason,
    )

# --- refusals (accepted is False, exact message) --------------------------
_no_study_name_upload = parse_upload(
    BOUNTY_FILE.name, BOUNTY_FILE.read_bytes(), _S14_MASTER_COLUMNS
)
check(
    "refusal: a raw study file (no Study_Name column) gives MSG_WRONG_FILE",
    not _no_study_name_upload.accepted and _no_study_name_upload.refusal_message == config.MSG_WRONG_FILE,
    _no_study_name_upload.refusal_message,
)

_real_master_upload = parse_upload(
    MASTER_FILE_NAME, (SAMPLES_DIR / MASTER_FILE_NAME).read_bytes(), _S14_MASTER_COLUMNS
)
check(
    "refusal: the real master CSV gives MSG_UPLOAD_IS_MASTER",
    not _real_master_upload.accepted and _real_master_upload.refusal_message == config.MSG_UPLOAD_IS_MASTER,
    _real_master_upload.refusal_message,
)

_synthetic_after_formulas_df = master_df.copy()
for _h in config.CALCULATED_HEADERS:
    _synthetic_after_formulas_df[_h] = ""
_synthetic_after_formulas_bytes = _to_csv_bytes_s14(_synthetic_after_formulas_df)
_synthetic_after_formulas_upload = parse_upload(
    "after_formulas_master_Instacart_2026-09-28_1200.csv",
    _synthetic_after_formulas_bytes,
    _S14_MASTER_COLUMNS,
)
check(
    "refusal: a synthetic after_formulas_master gives MSG_UPLOAD_IS_MASTER",
    not _synthetic_after_formulas_upload.accepted
    and _synthetic_after_formulas_upload.refusal_message == config.MSG_UPLOAD_IS_MASTER,
    _synthetic_after_formulas_upload.refusal_message,
)

_garbage_upload = parse_upload("garbage.xlsx", b"\x00\x01\x02not a zip file", _S14_MASTER_COLUMNS)
check(
    "refusal: unreadable garbage bytes give the MSG_UPLOAD_UNREADABLE prefix",
    not _garbage_upload.accepted
    and _garbage_upload.refusal_message.startswith(config.MSG_UPLOAD_UNREADABLE.split("{detail}")[0]),
    _garbage_upload.refusal_message,
)

_zero_byte_upload = parse_upload("empty.csv", b"", _S14_MASTER_COLUMNS)
check(
    "refusal: zero-byte upload gives the MSG_UPLOAD_UNREADABLE prefix",
    not _zero_byte_upload.accepted
    and _zero_byte_upload.refusal_message.startswith(config.MSG_UPLOAD_UNREADABLE.split("{detail}")[0]),
    _zero_byte_upload.refusal_message,
)

_header_only_no_study_upload = parse_upload(
    "headeronly.csv", _s14_csv_bytes([["A", "B", "C"]]), _S14_MASTER_COLUMNS
)
check(
    "refusal: header-only CSV without Study_Name gives MSG_WRONG_FILE",
    not _header_only_no_study_upload.accepted
    and _header_only_no_study_upload.refusal_message == config.MSG_WRONG_FILE,
    _header_only_no_study_upload.refusal_message,
)

# --- P12: trimmed, case-insensitive matching -------------------------------
_p12_master_df = pd.DataFrame({config.STUDY_NAME_COL: ["Instacart_Cascade"]}, dtype=object).astype(str)
_p12_calc = _s14_blank_calc(1)
_p12_upload_bytes = _s14_csv_bytes(
    [
        list(config.TEMPLATE_HEADERS),
        [" instacart_cascade ", "3.49", "45", "0.25", "150000", "12500000", "Featured"],
    ]
)
_p12_upload = parse_upload("p12.csv", _p12_upload_bytes, list(_p12_master_df.columns))
_p12_final = build_final(_p12_master_df, _p12_calc, _p12_upload)
check(
    "P12: ' instacart_cascade ' matches 'Instacart_Cascade' (trimmed, case-insensitive)",
    _p12_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[0] == "3.49"
    and config.P2W_STUDY_NOT_IN_UPLOAD not in _s14_codes(_p12_final.warnings)
    and config.P2W_STUDY_NOT_IN_MASTER not in _s14_codes(_p12_final.warnings),
    str(_p12_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[0]),
)

# --- P13 matrix -------------------------------------------------------------
_p13_master_df = pd.DataFrame(
    {config.STUDY_NAME_COL: ["NotInUpload", "Duplicated", "OneFilledOneBlank", "AllBlankRow"]},
    dtype=object,
).astype(str)
_p13_calc = _s14_blank_calc(4)
_p13_upload_bytes = _s14_csv_bytes(
    [
        list(config.TEMPLATE_HEADERS),
        ["Duplicated", "1", "1", "0.1", "1", "1", "A"],
        ["Duplicated", "2", "2", "0.2", "2", "2", "B"],
        ["OneFilledOneBlank", "5", "5", "0.5", "5", "5", "C"],
        ["OneFilledOneBlank", "", "", "", "", "", ""],
        ["AllBlankRow", "", "", "", "", "", ""],
        ["UploadOnly", "9", "9", "0.9", "9", "9", "D"],
    ]
)
_p13_upload = parse_upload("p13.csv", _p13_upload_bytes, list(_p13_master_df.columns))
_p13_final = build_final(_p13_master_df, _p13_calc, _p13_upload)


def _p13_warnings_for(study: str) -> list[Phase2Warning]:
    return [w for w in _p13_final.warnings if w.study == study]


check(
    "P13: study not in upload -> blank + study_not_in_upload",
    _p13_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[0] == ""
    and any(w.code == config.P2W_STUDY_NOT_IN_UPLOAD for w in _p13_warnings_for("NotInUpload")),
    str(_p13_warnings_for("NotInUpload")),
)
check(
    "P13: upload-only study (not in master) -> study_not_in_master",
    any(w.code == config.P2W_STUDY_NOT_IN_MASTER for w in _p13_warnings_for("UploadOnly")),
    str(_p13_warnings_for("UploadOnly")),
)
_p13_dup_warning = next(
    (w for w in _p13_warnings_for("Duplicated") if w.code == config.P2W_STUDY_DUPLICATED), None
)
check(
    "P13: two filled rows -> blank + study_duplicated with row numbers",
    _p13_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[1] == ""
    and _p13_dup_warning is not None
    and "2" in _p13_dup_warning.issue
    and "3" in _p13_dup_warning.issue,
    str(_p13_dup_warning),
)
check(
    "P13: one filled row + one blank row -> merged, no warning",
    _p13_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[2] == "5"
    and _p13_warnings_for("OneFilledOneBlank") == [],
    str((_p13_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[2], _p13_warnings_for("OneFilledOneBlank"))),
)
check(
    "P13: named all-blank row -> blank, no warning",
    _p13_final.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[3] == ""
    and _p13_warnings_for("AllBlankRow") == [],
    str(_p13_warnings_for("AllBlankRow")),
)

# --- P14: user-added columns -------------------------------------------------
_p14_master_df = pd.DataFrame({config.STUDY_NAME_COL: ["S1"]}, dtype=object).astype(str)
_p14_headers = list(config.TEMPLATE_HEADERS) + [
    "",              # H: blank header, values below -> upload_blank_header
    "Extra1",        # I: accepted extra
    "Extra2",        # J: accepted extra
    "ThisHeaderIsWayTooLong",  # K: 22 chars -> upload_extra_too_long, still merged
    "Brand",         # L: duplicate with M -> upload_extra_duplicated
    "brand",         # M
    "Channels",      # N: reserved (a master column) -> upload_extra_reserved
    config.CALC_COUNT_CIRCANA_BUYERS,  # O: reserved (a calculated header)
]
_p14_row = ["S1", "3.49", "45", "0.25", "150000", "12500000", "Featured"] + [
    "blankheaderval", "e1", "e2", "toolong", "b1", "b2", "chan", "cnt"
]
_p14_upload_bytes = _s14_csv_bytes([_p14_headers, _p14_row])
_p14_upload = parse_upload("p14.csv", _p14_upload_bytes, list(_p14_master_df.columns) + ["Channels"])
_p14_codes = _s14_codes(_p14_upload.warnings)
check(
    "P14: blank header with values -> upload_blank_header",
    config.P2W_UPLOAD_BLANK_HEADER in _p14_codes,
    str(_p14_upload.warnings),
)
check(
    "P14: accepted extras (Extra1, Extra2) merged after the fixed six, in upload order",
    _p14_upload.merge_columns[:6] == list(config.TEMPLATE_VALUE_HEADERS)
    and "Extra1" in _p14_upload.merge_columns
    and "Extra2" in _p14_upload.merge_columns
    and _p14_upload.merge_columns.index("Extra1") < _p14_upload.merge_columns.index("Extra2"),
    str(_p14_upload.merge_columns),
)
check(
    "P14: 22-character header -> upload_extra_too_long, still merged",
    config.P2W_UPLOAD_EXTRA_TOO_LONG in _p14_codes
    and "ThisHeaderIsWayTooLong" in _p14_upload.merge_columns,
    str(_p14_upload.merge_columns),
)
check(
    "P14: duplicate extras (Brand/brand) -> both ignored, upload_extra_duplicated",
    config.P2W_UPLOAD_EXTRA_DUPLICATED in _p14_codes
    and "Brand" not in _p14_upload.merge_columns
    and "brand" not in _p14_upload.merge_columns,
    str(_p14_upload.merge_columns),
)
check(
    "P14: 'Channels' (a master column) -> upload_extra_reserved",
    any(
        w.code == config.P2W_UPLOAD_EXTRA_RESERVED and w.column == "Channels"
        for w in _p14_upload.warnings
    ),
    str(_p14_upload.warnings),
)
check(
    "P14: 'Count of Circana Buyers' (a calculated header) -> upload_extra_reserved",
    any(
        w.code == config.P2W_UPLOAD_EXTRA_RESERVED and w.column == config.CALC_COUNT_CIRCANA_BUYERS
        for w in _p14_upload.warnings
    ),
    str(_p14_upload.warnings),
)

_p14_unexpected_bytes = _s14_csv_bytes(
    [
        [config.STUDY_NAME_COL, "Avg_Brand_Price", "UnknownHeader", "Pct_HH_Buying",
         "Tot_Camp_Cost", "Tot_Camp_Impr", "Read_Type"],
        ["S1", "3.49", "x", "0.25", "150000", "12500000", "Featured"],
    ]
)
_p14_unexpected_upload = parse_upload("p14b.csv", _p14_unexpected_bytes, list(_p14_master_df.columns))
check(
    "P14: unknown header in column C -> upload_unexpected_column",
    any(
        w.code == config.P2W_UPLOAD_UNEXPECTED_COLUMN and w.column == "UnknownHeader"
        for w in _p14_unexpected_upload.warnings
    ),
    str(_p14_unexpected_upload.warnings),
)

# --- P15: fixed column missing/renamed/duplicated/moved --------------------
_p15_headers = [
    config.STUDY_NAME_COL, "Avg Price", "Avg_Purch_Cycle", "Pct_HH_Buying",
    "Tot_Camp_Cost", "Tot_Camp_Impr", "Tot_Camp_Cost", "Extra", config.TEMPLATE_READ_TYPE,
]
_p15_row = ["S1", "3.49", "45", "0.25", "1", "12500000", "2", "e", "Featured"]
_p15_upload = parse_upload(
    "p15.csv", _s14_csv_bytes([_p15_headers, _p15_row]), list(_p14_master_df.columns)
)
check(
    "P15: 'Avg Price' in B -> upload_fixed_missing (Avg_Brand_Price) + upload_unexpected_column",
    any(
        w.code == config.P2W_UPLOAD_FIXED_MISSING and w.column == config.TEMPLATE_AVG_BRAND_PRICE
        for w in _p15_upload.warnings
    )
    and any(
        w.code == config.P2W_UPLOAD_UNEXPECTED_COLUMN and w.column == "Avg Price"
        for w in _p15_upload.warnings
    ),
    str(_p15_upload.warnings),
)
check(
    "P15: Read_Type moved to column I is matched by name",
    config.TEMPLATE_READ_TYPE in _p15_upload.present_fixed,
    str(_p15_upload.present_fixed),
)
check(
    "P15: two Tot_Camp_Cost columns -> upload_fixed_duplicated, blank",
    any(
        w.code == config.P2W_UPLOAD_FIXED_DUPLICATED and w.column == config.TEMPLATE_TOT_CAMP_COST
        for w in _p15_upload.warnings
    )
    and config.TEMPLATE_TOT_CAMP_COST not in _p15_upload.present_fixed,
    str(_p15_upload.warnings),
)

# --- Two Study_Name columns --------------------------------------------------
_two_study_headers = [config.STUDY_NAME_COL, "Avg_Brand_Price", config.STUDY_NAME_COL]
_two_study_upload = parse_upload(
    "twostudy.csv",
    _s14_csv_bytes([_two_study_headers, ["S1", "3.49", "S1dup"]]),
    list(_p14_master_df.columns),
)
check(
    "two Study_Name columns: leftmost used + upload_second_study_name warning",
    _two_study_upload.accepted
    and list(_two_study_upload.rows_by_study.keys()) == ["s1"]
    and any(w.code == config.P2W_UPLOAD_SECOND_STUDY_NAME for w in _two_study_upload.warnings),
    str((_two_study_upload.rows_by_study, _two_study_upload.warnings)),
)

# --- P16/P17: value check ----------------------------------------------------
_p1617_accept = ["3.49", "-2", "1500000", "1.2E+06", "0.25", ".5", "5.", "1e-07", " 3.49 "]
_p1617_warn = ["1,500", "$3.49", "25%", "abc", "+5", "1.2.3", "3,49", "NaN", "inf", "1 000"]

for _i, _val in enumerate(_p1617_accept + _p1617_warn):
    _study = f"P1617_{_i}"
    _m_df = pd.DataFrame({config.STUDY_NAME_COL: [_study]}, dtype=object).astype(str)
    _c = _s14_blank_calc(1)
    _u = parse_upload(
        "v.csv",
        _s14_csv_bytes([list(config.TEMPLATE_HEADERS), [_study, _val, "1", "0.1", "1", "1", "x"]]),
        list(_m_df.columns),
    )
    _f = build_final(_m_df, _c, _u)
    _expect_warning = _val in _p1617_warn
    _has_warning = any(w.code == config.P2W_VALUE_NOT_PLAIN_NUMBER for w in _f.warnings)
    check(
        f"P16/P17: {_val!r} on Avg_Brand_Price -> "
        f"{'warns' if _expect_warning else 'accepts'}, merged as typed either way",
        _has_warning == _expect_warning
        and _f.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[0] == _val,
        str((_has_warning, _f.frame[config.TEMPLATE_AVG_BRAND_PRICE].iloc[0])),
    )

_p1617_readtype_extra_df = pd.DataFrame({config.STUDY_NAME_COL: ["S1"]}, dtype=object).astype(str)
_p1617_readtype_extra_upload = parse_upload(
    "rt.csv",
    _s14_csv_bytes(
        [
            list(config.TEMPLATE_HEADERS) + ["Extra"],
            ["S1", "1", "1", "0.1", "1", "1", "abc", "abc"],
        ]
    ),
    list(_p1617_readtype_extra_df.columns),
)
_p1617_readtype_extra_final = build_final(
    _p1617_readtype_extra_df, _s14_blank_calc(1), _p1617_readtype_extra_upload
)
check(
    "P16/P17: Read_Type='abc' and an extra='abc' never checked -> no value_not_plain_number",
    config.P2W_VALUE_NOT_PLAIN_NUMBER not in _s14_codes(_p1617_readtype_extra_final.warnings),
    str(_p1617_readtype_extra_final.warnings),
)

_p1617_off_df = pd.DataFrame({config.STUDY_NAME_COL: ["S1"]}, dtype=object).astype(str)
_p1617_off_upload = parse_upload(
    "off.csv",
    _s14_csv_bytes([list(config.TEMPLATE_HEADERS), ["S1", "abc", "1", "0.1", "1", "1", "x"]]),
    list(_p1617_off_df.columns),
)
_p1617_off_final = build_final(
    _p1617_off_df, _s14_blank_calc(1), _p1617_off_upload, value_check=False
)
check(
    "P16/P17: value_check=False -> no value_not_plain_number warnings at all",
    config.P2W_VALUE_NOT_PLAIN_NUMBER not in _s14_codes(_p1617_off_final.warnings),
    str(_p1617_off_final.warnings),
)

# --- P18: percentages --------------------------------------------------------
from template_builder import build_template_bytes as _build_template_bytes_s14

_p18_template_bytes = _build_template_bytes_s14(["S1"])
_p18_wb = _openpyxl_s12.load_workbook(_io_s12.BytesIO(_p18_template_bytes))
_p18_ws = _p18_wb[config.TEMPLATE_SHEET_TITLE]
_p18_ws["B2"] = "3.49"
_p18_ws["C2"] = "45"
_p18_ws["D2"] = 0.25
_p18_ws["E2"] = "150000"
_p18_ws["F2"] = "12500000"
_p18_ws["G2"] = "Featured"
_p18_buf = _io_s12.BytesIO()
_p18_wb.save(_p18_buf)
_p18_df = pd.DataFrame({config.STUDY_NAME_COL: ["S1"]}, dtype=object).astype(str)
_p18_upload = parse_upload("p18.xlsx", _p18_buf.getvalue(), list(_p18_df.columns))
_p18_final = build_final(_p18_df, _s14_blank_calc(1), _p18_upload)
check(
    "P18: xlsx D2=0.25 (numeric, percent format) merges '0.25'",
    _p18_final.frame[config.TEMPLATE_PCT_HH_BUYING].iloc[0] == "0.25",
    _p18_final.frame[config.TEMPLATE_PCT_HH_BUYING].iloc[0],
)

_p18_csv_upload = parse_upload(
    "p18.csv",
    _s14_csv_bytes([list(config.TEMPLATE_HEADERS), ["S1", "3.49", "45", "25%", "150000", "12500000", "Featured"]]),
    list(_p18_df.columns),
)
_p18_csv_final = build_final(_p18_df, _s14_blank_calc(1), _p18_csv_upload)
check(
    "P18: CSV '25%' is warned and merged as typed ('25%')",
    _p18_csv_final.frame[config.TEMPLATE_PCT_HH_BUYING].iloc[0] == "25%"
    and any(
        w.code == config.P2W_VALUE_NOT_PLAIN_NUMBER and w.column == config.TEMPLATE_PCT_HH_BUYING
        for w in _p18_csv_final.warnings
    ),
    str((_p18_csv_final.frame[config.TEMPLATE_PCT_HH_BUYING].iloc[0], _p18_csv_final.warnings)),
)

# --- Zero match ---------------------------------------------------------------
_zero_match_master_df = pd.DataFrame({config.STUDY_NAME_COL: ["RealStudyA", "RealStudyB"]}, dtype=object).astype(str)
_zero_match_upload = parse_upload(
    "zm.csv",
    _s14_csv_bytes(
        [
            list(config.TEMPLATE_HEADERS),
            ["OtherProjectStudy1", "1", "1", "0.1", "1", "1", "x"],
            ["OtherProjectStudy2", "2", "2", "0.2", "2", "2", "y"],
        ]
    ),
    list(_zero_match_master_df.columns),
)
_zero_match_final = build_final(_zero_match_master_df, _s14_blank_calc(2), _zero_match_upload)
check(
    "zero match: zero_match True, upload_study_count correct",
    _zero_match_final.zero_match is True and _zero_match_final.upload_study_count == 2,
    f"zero_match={_zero_match_final.zero_match} upload_study_count={_zero_match_final.upload_study_count}",
)
_zero_match_upload_warning_codes = [
    w.code for w in _zero_match_final.warnings if w.code != config.P2W_STUDY_NOT_IN_UPLOAD
]
check(
    "zero match: upload_zero_match is first among the upload warnings",
    _zero_match_upload_warning_codes[0] == config.P2W_UPLOAD_ZERO_MATCH
    if _zero_match_upload_warning_codes
    else False,
    str(_zero_match_upload_warning_codes),
)

# --- P26/P27 on the full-batch master (Section 6, 732 rows) ------------------
_full_batch_calc = build_calculations(full_batch_result.master_df)
_full_batch_studies = list_template_studies(full_batch_result.master_df)
_full_batch_template_bytes = build_template_bytes(_full_batch_studies)
_full_batch_upload = parse_upload(
    "full.xlsx", _full_batch_template_bytes, list(full_batch_result.master_df.columns)
)
_full_batch_final = build_final(full_batch_result.master_df, _full_batch_calc, _full_batch_upload)

check(
    "P26: final columns == master + CALCULATED_HEADERS + fixed six + extras",
    list(_full_batch_final.frame.columns)
    == list(full_batch_result.master_df.columns)
    + list(config.CALCULATED_HEADERS)
    + _full_batch_upload.merge_columns,
    str(list(_full_batch_final.frame.columns)),
)
check(
    "P26: Study_Name appears exactly once in the final columns",
    list(_full_batch_final.frame.columns).count(config.STUDY_NAME_COL) == 1,
)
check(
    "P26: length and order identical to the master",
    len(_full_batch_final.frame) == len(full_batch_result.master_df)
    and _full_batch_final.frame[config.STUDY_NAME_COL].tolist()
    == full_batch_result.master_df[config.STUDY_NAME_COL].tolist(),
)
check(
    "P26: every master cell is string-identical in the final frame",
    all(
        _full_batch_final.frame[col].tolist() == full_batch_result.master_df[col].tolist()
        for col in full_batch_result.master_df.columns
    ),
)
_p27_ok = True
_p27_detail = ""
for _study in _full_batch_studies:
    _mask = _full_batch_final.frame[config.STUDY_NAME_COL] == _study
    for _col in config.TEMPLATE_VALUE_HEADERS:
        _values = _full_batch_final.frame.loc[_mask, _col].unique().tolist()
        if len(_values) > 1:
            _p27_ok = False
            _p27_detail = f"{_study}/{_col}: {_values}"
            break
    if not _p27_ok:
        break
check("P27: each study's values are identical (repeated) on every one of its rows", _p27_ok, _p27_detail)

# --- P29 proxy: always derived from the current master + current upload -----
_p29_base_bytes = _to_csv_bytes_s14(_full_batch_final.frame.iloc[:, : len(full_batch_result.master_df.columns)])
_p29_new_row = full_batch_result.master_df.iloc[[0]].copy()
_p29_new_row[config.STUDY_NAME_COL] = "BrandNewStudy"
_p29_new_master_df = pd.concat(
    [full_batch_result.master_df, _p29_new_row], ignore_index=True
).reindex(columns=full_batch_result.master_df.columns)
_p29_new_calc = build_calculations(_p29_new_master_df)
_p29_new_final = build_final(_p29_new_master_df, _p29_new_calc, _full_batch_upload)
check(
    "P29 proxy: a new study not in the retained upload gets study_not_in_upload",
    any(
        w.code == config.P2W_STUDY_NOT_IN_UPLOAD and w.study == "BrandNewStudy"
        for w in _p29_new_final.warnings
    ),
    str([w for w in _p29_new_final.warnings if w.study == "BrandNewStudy"]),
)
check(
    "P29 proxy: the new master's extra row is reflected in the final frame",
    len(_p29_new_final.frame) == len(full_batch_result.master_df) + 1,
    len(_p29_new_final.frame),
)
_p29_repeat_a = build_final(full_batch_result.master_df, _full_batch_calc, _full_batch_upload)
_p29_repeat_b = build_final(full_batch_result.master_df, _full_batch_calc, _full_batch_upload)
check(
    "P29 proxy: two calls with identical inputs give byte-identical to_csv_bytes",
    _to_csv_bytes_s14(_p29_repeat_a.frame) == _to_csv_bytes_s14(_p29_repeat_b.frame),
)

# --- report.py additions ------------------------------------------------------
_report_empty_frame = phase2_warnings_to_frame([])
check(
    "phase2_warnings_to_frame([]) keeps PHASE2_WARNING_COLUMNS, zero rows",
    list(_report_empty_frame.columns) == config.PHASE2_WARNING_COLUMNS and len(_report_empty_frame) == 0,
    str(list(_report_empty_frame.columns)),
)
_report_frame = phase2_warnings_to_frame(_p13_final.warnings)
check(
    "phase2_warnings_to_frame columns == PHASE2_WARNING_COLUMNS, one row per warning "
    "(non-vacuous: _p13_final carries real warnings)",
    list(_report_frame.columns) == config.PHASE2_WARNING_COLUMNS
    and len(_report_frame) == len(_p13_final.warnings)
    and len(_p13_final.warnings) > 0,
    f"columns={list(_report_frame.columns)} n_warnings={len(_p13_final.warnings)}",
)
check(
    "summarize_phase2_warnings: '' when there are no warnings",
    summarize_phase2_warnings(_p12_final) == "" if _p12_final.warnings == [] else True,
    summarize_phase2_warnings(_p12_final),
)
_summary_expected = config.MSG_WARNINGS_SUMMARY.format(
    total=len(_p13_final.warnings),
    calc=_p13_final.calculation_warning_count,
    upload=_p13_final.upload_warning_count,
)
check(
    "summarize_phase2_warnings: exact string on a warnings-bearing result",
    summarize_phase2_warnings(_p13_final) == _summary_expected
    and len(_p13_final.warnings) > 0,
    summarize_phase2_warnings(_p13_final),
)

_fixed_now_s14 = _datetime_s12(2026, 9, 28, 14, 30)
check(
    "build_final_filename('Instacart', fixed_now) exact pattern",
    build_final_filename("Instacart", _fixed_now_s14)
    == "after_formulas_master_Instacart_2026-09-28_1430.csv",
    build_final_filename("Instacart", _fixed_now_s14),
)
check(
    "build_phase2_warnings_filename('Instacart', fixed_now) exact pattern",
    build_phase2_warnings_filename("Instacart", _fixed_now_s14)
    == "phase2_warnings_Instacart_2026-09-28_1430.csv",
    build_phase2_warnings_filename("Instacart", _fixed_now_s14),
)

# --- end-to-end precision -----------------------------------------------------
_e2e_calc = build_calculations(precision_result.master_df)
_e2e_studies = list_template_studies(precision_result.master_df)
_e2e_template_bytes = build_template_bytes(_e2e_studies)
_e2e_upload = parse_upload("e2e.xlsx", _e2e_template_bytes, list(precision_result.master_df.columns))
_e2e_final = build_final(precision_result.master_df, _e2e_calc, _e2e_upload)
_e2e_bytes = _to_csv_bytes_s14(_e2e_final.frame)
check(
    "end-to-end precision: to_csv_bytes(final.frame) starts with the UTF-8 BOM",
    _e2e_bytes[:3] == b"\xef\xbb\xbf",
    repr(_e2e_bytes[:3]),
)
_e2e_text = _e2e_bytes.decode(config.OUTPUT_ENCODING)
_e2e_rows = list(csv.DictReader(_io_s12.StringIO(_e2e_text)))
_e2e_master_csv_rows = list(
    csv.DictReader(_io_s12.StringIO(_to_csv_bytes_s14(precision_result.master_df).decode(config.OUTPUT_ENCODING)))
)
_e2e_mismatches = []
for _i, (_src, _out) in enumerate(zip(_e2e_master_csv_rows, _e2e_rows)):
    for _col in precision_result.master_df.columns:
        if _src[_col] != _out[_col]:
            _e2e_mismatches.append((_i, _col, _src[_col], _out[_col]))
check(
    "end-to-end precision: every master column is identical to the master's own CSV fields, "
    "re-parsed with the stdlib csv module",
    _e2e_mismatches == [],
    f"{len(_e2e_mismatches)} mismatches, first: {_e2e_mismatches[0]}" if _e2e_mismatches else "",
)
check(
    "end-to-end precision: the literal '0.19163628728414203' survives (Bounty, via process_batch)",
    any("0.19163628728414203" in row.values() for row in _e2e_rows),
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = _passed + _failed
print(f"\n{'='*60}")
print(f"  RESULT: {_passed}/{total} checks passed  |  {_failed} failed  |  {_skipped} skipped")
print(f"{'='*60}\n")

if _failed > 0:
    sys.exit(1)
