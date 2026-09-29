"""
report.py — BatchResult -> the on-screen outcomes table, the downloadable
exception report, and the summary metrics dict. No streamlit import, no
filesystem writes, zero arithmetic beyond counting.

missing_cols / extra_cols are Python lists on FileOutcome; both frame
builders here join them with config.LIST_JOIN_SEPARATOR so every cell in
every DataFrame this module produces is a scalar str, consistent with the
precision contract in ARCHITECTURE.md section 5 (a raw list in a CSV cell
would render as "['A', 'B']", which is not a value anyone asked for).
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

import config
from models import BatchResult, FileOutcome, FinalResult, Phase2Warning


def _join(values: list[str]) -> str:
    return config.LIST_JOIN_SEPARATOR.join(values)


def outcomes_to_frame(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """All outcomes, for the on-screen table: file, status, reason,
    study_name, rows, missing_cols, extra_cols (lists joined with
    config.LIST_JOIN_SEPARATOR).
    """
    return pd.DataFrame(
        {
            "file": [o.file for o in outcomes],
            "status": [o.status for o in outcomes],
            "reason": [o.reason for o in outcomes],
            "study_name": [o.study_name for o in outcomes],
            "rows": [o.rows for o in outcomes],
            "missing_cols": [_join(o.missing_cols) for o in outcomes],
            "extra_cols": [_join(o.extra_cols) for o in outcomes],
        },
        columns=["file", "status", "reason", "study_name", "rows", "missing_cols", "extra_cols"],
    )


def build_exception_report(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """Only outcomes where status != STATUS_APPENDED. Exactly
    config.EXCEPTION_REPORT_COLUMNS, in that order. Returns an empty frame
    WITH those columns when there are no exceptions.
    """
    exceptions = [o for o in outcomes if o.status != config.STATUS_APPENDED]
    frame = pd.DataFrame(
        {
            "file": [o.file for o in exceptions],
            "status": [o.status for o in exceptions],
            "reason": [o.reason for o in exceptions],
            "missing_cols": [_join(o.missing_cols) for o in exceptions],
            "extra_cols": [_join(o.extra_cols) for o in exceptions],
        },
        columns=config.EXCEPTION_REPORT_COLUMNS,
    )
    return frame


def rejected_files_message(outcomes: Sequence[FileOutcome]) -> str:
    """Q16 banner text: "" when no outcome is rejected; otherwise
    MSG_FILES_REJECTED_ONE / _MANY listing every rejected file as
    "`name` (reason)", in outcome order. The count uses the same rule as
    BatchResult.rejected, so it always matches the "Files rejected" metric.
    """
    rejected = [o for o in outcomes if o.status == config.STATUS_REJECTED]
    if not rejected:
        return ""
    files = ", ".join(f"`{o.file}` ({o.reason})" for o in rejected)
    if len(rejected) == 1:
        return config.MSG_FILES_REJECTED_ONE.format(files=files)
    return config.MSG_FILES_REJECTED_MANY.format(n=len(rejected), files=files)


def summarize(result: BatchResult) -> dict[str, int]:
    """Keys, in display order:
      'Total files processed', 'Files successfully appended',
      'Files skipped (already in master)', 'Files rejected',
      'Records appended this run', 'Total records in master'.

    Items 5/6 show both interpretations of "total records consolidated"
    (rows added this run, and rows in the final master).
    # DESIGN DEFAULT — confirmed 2026-09-29, see spec section 8, item 1
    """
    return {
        "Total files processed": result.total_files,
        "Files successfully appended": result.appended,
        "Files skipped (already in master)": result.skipped,
        "Files rejected": result.rejected,
        "Records appended this run": result.rows_appended,
        "Total records in master": result.total_records,
    }


# =============================================================================
# PHASE 2 — the P30 warnings panel: the expandable table and its summary line.
# (PHASE2_ARCHITECTURE.md section 1.12.) The `code` field of Phase2Warning is
# never output here — codes are for tests only.
# =============================================================================


def phase2_warnings_to_frame(warnings: Sequence[Phase2Warning]) -> pd.DataFrame:
    """Exactly config.PHASE2_WARNING_COLUMNS (Study, Model, Column, Issue), in
    order, one row per warning, dtype=object. Empty frame WITH those columns
    when there are none.
    """
    study_key, model_key, column_key, issue_key = config.PHASE2_WARNING_COLUMNS
    return pd.DataFrame(
        {
            study_key: [w.study for w in warnings],
            model_key: [w.model for w in warnings],
            column_key: [w.column for w in warnings],
            issue_key: [w.issue for w in warnings],
        },
        columns=config.PHASE2_WARNING_COLUMNS,
        dtype=object,
    )


def summarize_phase2_warnings(result: FinalResult) -> str:
    """"" when no warnings; else config.MSG_WARNINGS_SUMMARY formatted with
    total/calc/upload.
    """
    total = len(result.warnings)
    if total == 0:
        return ""
    return config.MSG_WARNINGS_SUMMARY.format(
        total=total,
        calc=result.calculation_warning_count,
        upload=result.upload_warning_count,
    )
