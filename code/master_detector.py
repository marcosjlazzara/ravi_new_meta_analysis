"""
master_detector.py — Finds and validates the master file, and builds the
MasterContext that becomes the schema authority for the rest of the run.
No streamlit import, no filesystem writes, zero arithmetic.

See ARCHITECTURE.md section 3 for the master detection contract:
a file is a candidate iff Path(name).stem.lower().startswith("master_"); a
candidate is valid iff it is also readable and its normalized column index
contains "study_name".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import pandas as pd

import config
from file_reader import FileReadError, read_table
from models import MasterCandidate, MasterContext, UploadedItem
from schema import SchemaError, build_column_index, find_phase2_output_headers, normalize_column

_TIMESTAMP_SUFFIX_RE = re.compile(config.MASTER_TIMESTAMP_SUFFIX_RE)
_STUDY_NAME_KEY = normalize_column(config.STUDY_NAME_COL)


def find_master_candidates(items: Sequence[UploadedItem]) -> list[MasterCandidate]:
    """Every item whose stem.lower().startswith(config.MASTER_FILENAME_PREFIX).

    Each candidate is read to populate readable / has_study_name / error /
    is_phase2_output. This function must never raise — a candidate that
    fails to read (bad bytes, unrecognised extension, duplicate columns,
    anything) becomes readable=False with the error captured, rather than
    propagating.
    """
    candidates: list[MasterCandidate] = []
    for item in items:
        if not item.stem.lower().startswith(config.MASTER_FILENAME_PREFIX):
            continue

        readable = False
        has_study_name = False
        is_phase2_output = False
        error = ""
        try:
            df = read_table(item.name, item.data)
            column_index = build_column_index(list(df.columns))
            readable = True
            has_study_name = _STUDY_NAME_KEY in column_index
            # P3: a Master_-prefixed file carrying calculated/merged columns is
            # not a valid master — see MasterCandidate.is_valid.
            is_phase2_output = bool(find_phase2_output_headers(list(df.columns)))
        except Exception as e:  # noqa: BLE001 — must never raise, capture everything
            error = str(e)

        candidates.append(
            MasterCandidate(
                index=item.index,
                name=item.name,
                readable=readable,
                has_study_name=has_study_name,
                error=error,
                is_phase2_output=is_phase2_output,
            )
        )
    return candidates


def first_master_slot_allowed(candidates: Sequence[MasterCandidate]) -> bool:
    """False if any candidate is_phase2_output. app.py consults this only when
    there are zero valid candidates: a Phase 2 output offered as the master
    keeps Run disabled until a proper master is supplied (P3), rather than
    silently falling through to the first-master slot.
    """
    return not any(c.is_phase2_output for c in candidates)


def _refuse_phase2_output(frame: pd.DataFrame) -> None:
    """Raise SchemaError(REASON_PHASE2_OUTPUT) if `frame`'s columns carry any
    Phase 2 signature header. Called immediately after read_table in both
    master-context builders — the second line of defence against an
    after_formulas_master (or a studyname_master) picked as the master.
    """
    hits = find_phase2_output_headers(list(frame.columns))
    if hits:
        raise SchemaError(config.REASON_PHASE2_OUTPUT, config.MSG_PHASE2_OUTPUT)


def parse_master_base_name(filename: str) -> str:
    """'Master_File_Instacart_2026-09-07_1430.csv' -> 'Instacart'
       'Master_Instacart_2026-09-07_1430.csv'      -> 'Instacart'
       'Master_Instacart.csv'                 -> 'Instacart'
       'master_A_B_2026-09-07_1430.csv'       -> 'A_B'

    Strip the extension, strip the prefix case-insensitively, then apply
    config.MASTER_TIMESTAMP_SUFFIX_RE and take group 'name' if it matches,
    else keep the whole remainder.
    """
    stem = Path(filename).stem
    # Longest prefix first: an output master is named "Master_File_<name>_<ts>",
    # so stripping only "Master_" would leave "File_<name>" and the literal
    # "File_" would accumulate on every re-upload.
    if stem.lower().startswith(config.MASTER_OUTPUT_FILENAME_PREFIX):
        remainder = stem[len(config.MASTER_OUTPUT_FILENAME_PREFIX):]
    elif stem.lower().startswith(config.MASTER_FILENAME_PREFIX):
        remainder = stem[len(config.MASTER_FILENAME_PREFIX):]
    else:
        remainder = stem

    match = _TIMESTAMP_SUFFIX_RE.match(remainder)
    if match:
        return match.group("name")
    return remainder


def sanitize_base_name(name: str) -> str:
    """Strip; replace each char in config.ILLEGAL_FILENAME_CHARS with
    config.FILENAME_REPLACEMENT_CHAR; collapse repeats of the replacement
    char; strip trailing dots and spaces.
    """
    cleaned = name.strip()
    for char in config.ILLEGAL_FILENAME_CHARS:
        cleaned = cleaned.replace(char, config.FILENAME_REPLACEMENT_CHAR)

    replacement = config.FILENAME_REPLACEMENT_CHAR
    collapse_re = re.compile(re.escape(replacement) + "{2,}")
    cleaned = collapse_re.sub(replacement, cleaned)

    cleaned = cleaned.rstrip(". ")
    return cleaned


def build_master_context_from_existing(item: UploadedItem) -> MasterContext:
    """Resume path. base_name = parse_master_base_name(item.name). columns =
    the file's verbatim columns in file order. created_this_run = False.

    Raises FileReadError / SchemaError on failure — the caller (app.py)
    surfaces it; this is the one place a failure is allowed to halt the run,
    per ARCHITECTURE.md section 9 ("without a master there is no schema to
    validate against").
    """
    frame = read_table(item.name, item.data)
    _refuse_phase2_output(frame)  # P3: second line of defence against an after_formulas_master
    # DESIGN DEFAULT — pending confirmation, see spec section 8, item 7
    # columns is taken verbatim in file order and never reordered here — an
    # inherited master's Study_Name position (wherever the uploaded file put
    # it) is left exactly as-is. Master order wins; "append Study_Name last"
    # is a rule that only applies to a NEWLY created master column, in
    # build_master_context_from_first_file above, not to this resume path.
    # Not reordering IS the decision — there is deliberately no reorder call.
    columns = list(frame.columns)
    column_index = build_column_index(columns)
    base_name = parse_master_base_name(item.name)
    existing_study_names = collect_existing_study_names(frame, config.STUDY_NAME_COL)

    return MasterContext(
        frame=frame,
        columns=columns,
        column_index=column_index,
        base_name=base_name,
        source_file=item.name,
        source_index=item.index,
        existing_study_names=existing_study_names,
        created_this_run=False,
    )


def build_master_context_from_first_file(item: UploadedItem, base_name: str) -> MasterContext:
    """First-master path. If config.STUDY_NAME_COL (normalized) is absent,
    append it LAST and set every row to item.stem. If already present,
    leave the column and its values exactly as they are and do not move it.
    base_name = sanitize_base_name(base_name). created_this_run = True.
    """
    frame = read_table(item.name, item.data)
    _refuse_phase2_output(frame)  # P3: second line of defence against an after_formulas_master
    column_index = build_column_index(list(frame.columns))

    if _STUDY_NAME_KEY not in column_index:
        frame = frame.copy()
        frame[config.STUDY_NAME_COL] = item.stem
    else:
        # DESIGN DEFAULT — pending confirmation, see spec section 8, item 2
        # The uploaded first-master file already carries Study_Name (e.g. the
        # real Holly_Rancher sample). Leave the column and its values exactly
        # as-is and do not move it — overwriting would destroy real data.
        pass

    columns = list(frame.columns)
    column_index = build_column_index(columns)
    sanitized_base_name = sanitize_base_name(base_name)
    existing_study_names = collect_existing_study_names(frame, config.STUDY_NAME_COL)

    return MasterContext(
        frame=frame,
        columns=columns,
        column_index=column_index,
        base_name=sanitized_base_name,
        source_file="",
        source_index=item.index,
        existing_study_names=existing_study_names,
        created_this_run=True,
    )


def collect_existing_study_names(frame: pd.DataFrame, study_name_column: str) -> set[str]:
    """Normalized (strip + casefold) non-blank values."""
    if study_name_column not in frame.columns:
        return set()

    names: set[str] = set()
    for value in frame[study_name_column]:
        normalized = str(value).strip().casefold()
        if normalized:
            names.add(normalized)
    return names
