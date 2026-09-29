"""
study_processor.py — Per-file validation/append pipeline and the batch loop
that drives it. No streamlit import, no filesystem writes, zero arithmetic.

process_file() never raises: every failure becomes a FileOutcome so the
batch loop in process_batch() can run to completion regardless of how many
individual files are broken. See ARCHITECTURE.md section 1 (study_processor.py)
and section 4 (edge cases) for the contract this module implements.

Check order inside process_file() is FIXED — see the docstring below — and
must not be reordered. In particular tag_study_name() MUST run before
align_to_master(), because align_to_master() has no `optional` escape and
requires the full master column set already present on the frame.
"""

from __future__ import annotations

from typing import AbstractSet, Mapping, Sequence

import pandas as pd

import config
from file_reader import FileReadError, read_table
from models import BatchResult, FileOutcome, MasterContext, UploadedItem
from schema import (
    SchemaError,
    align_to_master,
    build_column_index,
    compare_columns,
    find_phase2_output_headers,
    normalize_column,
    tag_study_name,
)

_STUDY_NAME_KEY = normalize_column(config.STUDY_NAME_COL)


def process_file(
    item: UploadedItem,
    master: MasterContext,
    study_name: str,
    taken_names: set[str],
) -> tuple[pd.DataFrame | None, FileOutcome]:
    """Single-file pipeline. Never raises — every failure becomes a FileOutcome.

    Fixed check order:
      1. blank study_name               -> rejected, REASON_BLANK_STUDY_NAME
      2. read_table                     -> rejected, e.reason (EMPTY_FILE/UNREADABLE)
      3. build_column_index(file cols)  -> rejected, REASON_DUPLICATE_COLUMNS
      3b. find_phase2_output_headers(df.columns) non-empty
                                        -> rejected, REASON_PHASE2_OUTPUT (P3)
      4. compare_columns(optional={study_name normalized})
                                        -> rejected, REASON_COLUMN_MISMATCH + col lists
      5. len(df) == 0                   -> skipped,  REASON_NO_DATA_ROWS
      6. normalized name in taken_names -> skipped,  REASON_ALREADY_IN_MASTER
                                                     or REASON_DUPLICATE_IN_BATCH
      7. tag_study_name -> align_to_master -> appended

    Only step 4 populates missing_cols/extra_cols; every other path leaves
    them []. (Step 3, duplicate columns, deliberately leaves both empty — a
    duplicate-column error has no meaningful missing-vs-extra comparison
    against the master. Step 3b, Phase 2 output, leaves both empty for the
    same reason — a calculated/merged-column file has no useful missing-vs-
    extra comparison either.) `study_name` on the returned FileOutcome is
    always the raw value passed in (whatever was "used or attempted"), even
    when blank.
    """

    def _outcome(
        status: str,
        reason: str,
        missing_cols: list[str] | None = None,
        extra_cols: list[str] | None = None,
        rows: int = 0,
    ) -> FileOutcome:
        return FileOutcome(
            file=item.name,
            index=item.index,
            status=status,
            reason=reason,
            missing_cols=missing_cols or [],
            extra_cols=extra_cols or [],
            study_name=study_name,
            rows=rows,
        )

    # 1. blank study_name
    if not study_name.strip():
        return None, _outcome(config.STATUS_REJECTED, config.REASON_BLANK_STUDY_NAME)

    # 2. read_table
    try:
        df = read_table(item.name, item.data)
    except FileReadError as e:
        return None, _outcome(config.STATUS_REJECTED, e.reason)

    # 3. duplicate columns within the file itself
    try:
        file_column_index = build_column_index(list(df.columns))
    except SchemaError:
        return None, _outcome(config.STATUS_REJECTED, config.REASON_DUPLICATE_COLUMNS)

    # 3b. output fed back as input (P3) — a file carrying calculated/merged
    # columns is rejected with a clear message; the run continues.
    if find_phase2_output_headers(list(df.columns)):
        return None, _outcome(config.STATUS_REJECTED, config.REASON_PHASE2_OUTPUT)

    # 4. column mismatch against the master, exempting Study_Name
    missing, extra = compare_columns(
        master.columns, list(df.columns), optional={config.STUDY_NAME_COL}
    )
    if missing or extra:
        return None, _outcome(
            config.STATUS_REJECTED, config.REASON_COLUMN_MISMATCH, missing, extra
        )

    # 5. valid structure, zero data rows — skipped, does not reserve the name
    if len(df) == 0:
        return None, _outcome(config.STATUS_SKIPPED, config.REASON_NO_DATA_ROWS)

    # 6. duplicate Study_Name — already in master, or seen earlier in this batch
    # DESIGN DEFAULT — pending confirmation, see spec section 8, item 6
    # Duplicate comparison is strip + casefold; taken_names/existing_study_names
    # store the normalized key only for comparison — the FileOutcome.study_name
    # and the value written into the master column stay verbatim (see step 7).
    normalized_name = study_name.strip().casefold()
    if normalized_name in taken_names:
        reason = (
            config.REASON_ALREADY_IN_MASTER
            if normalized_name in master.existing_study_names
            else config.REASON_DUPLICATE_IN_BATCH
        )
        return None, _outcome(config.STATUS_SKIPPED, reason)

    # 7. tag Study_Name (overwriting the file's own column if it has one,
    #    matched by normalized name so casing quirks don't create a
    #    duplicate column) then reorder into master column order.
    tag_column = file_column_index.get(_STUDY_NAME_KEY, config.STUDY_NAME_COL)
    tagged = tag_study_name(df, study_name, tag_column)
    aligned = align_to_master(tagged, master.columns)

    return aligned, _outcome(
        config.STATUS_APPENDED, config.REASON_NONE, rows=len(aligned)
    )


def is_run_ready(master: MasterContext | None, study_item_count: int) -> bool:
    """P4. False if master is None; True if study_item_count > 0; otherwise
    True only for an EXISTING master (not master.created_this_run). The
    first-master slot is unchanged: a freshly designated master still needs
    at least one study file to run.
    """
    if master is None:
        return False
    if study_item_count > 0:
        return True
    return not master.created_this_run


def process_batch(
    items: Sequence[UploadedItem],
    master: MasterContext,
    study_names: Mapping[int, str],
    excluded_indices: AbstractSet[int] = frozenset(),
    excluded_outcomes: Sequence[FileOutcome] = (),
) -> BatchResult:
    """Iterate items in upload order, skipping master.source_index and every
    index in excluded_indices.

    `taken` is seeded from master.existing_study_names; after each successful
    append the normalized name is added so a later same-named file in the
    SAME batch is caught as REASON_DUPLICATE_IN_BATCH rather than silently
    appending twice. Appended frames are concatenated onto master.frame with
    pd.concat(..., ignore_index=True) and reindexed to master.columns.
    excluded_outcomes (e.g. unselected master candidates) are merged into
    the outcome list, sorted by index, so they appear in the report.

    A missing key in `study_names` defaults to "" (not item.stem) — the
    stem default described in ARCHITECTURE.md STEP 4 is app.py's
    responsibility; this module stays decoupled from that UI default and
    lets a missing entry surface as REASON_BLANK_STUDY_NAME.
    """
    taken: set[str] = set(master.existing_study_names)
    outcomes: list[FileOutcome] = []
    appended_frames: list[pd.DataFrame] = []

    for item in items:
        if item.index == master.source_index or item.index in excluded_indices:
            continue

        study_name = study_names.get(item.index, "")
        aligned_df, outcome = process_file(item, master, study_name, taken)
        outcomes.append(outcome)

        if outcome.status == config.STATUS_APPENDED and aligned_df is not None:
            appended_frames.append(aligned_df)
            taken.add(study_name.strip().casefold())

    outcomes.extend(excluded_outcomes)
    outcomes.sort(key=lambda o: o.index)

    if appended_frames:
        master_df = pd.concat([master.frame, *appended_frames], ignore_index=True)
    else:
        master_df = master.frame.copy()
    master_df = master_df.reindex(columns=master.columns)

    appended = sum(1 for o in outcomes if o.status == config.STATUS_APPENDED)
    skipped = sum(1 for o in outcomes if o.status == config.STATUS_SKIPPED)
    rejected = sum(1 for o in outcomes if o.status == config.STATUS_REJECTED)
    rows_appended = sum(o.rows for o in outcomes)

    return BatchResult(
        master_df=master_df,
        outcomes=outcomes,
        total_files=len(outcomes),
        appended=appended,
        skipped=skipped,
        rejected=rejected,
        rows_appended=rows_appended,
        total_records=len(master_df),
    )
