"""
schema.py — The column contract: normalization, comparison, reordering, and
Study_Name tagging. No I/O, no filesystem access, no streamlit import.

Structure authority is always the master (brief decisions 7/9): callers pass
master_columns in and this module never invents or assumes a column name of
its own, other than config.STUDY_NAME_COL used by callers — this module
itself takes column names purely as parameters and never hardcodes any.

Values are never touched here. align_to_master and tag_study_name only
rename, reorder, or set a single tag column — see ARCHITECTURE.md section 5
for the precision contract this module must not violate.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

import pandas as pd

import config

_WHITESPACE_RUN_RE = re.compile(r"\s+")


class SchemaError(Exception):
    """Carries a config.REASON_* token so callers classify without string-sniffing."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def normalize_column(name: str) -> str:
    """Lowercase, strip, collapse internal whitespace runs to one space.

    Implements brief decision 8 (column-name matching is case- and
    whitespace-insensitive).
    """
    return _WHITESPACE_RUN_RE.sub(" ", name.strip()).lower()


def build_column_index(columns: Sequence[str]) -> dict[str, str]:
    """normalized -> verbatim.

    Raises SchemaError(REASON_DUPLICATE_COLUMNS) if two columns normalize to
    the same key.
    """
    index: dict[str, str] = {}
    for column in columns:
        key = normalize_column(column)
        if key in index:
            raise SchemaError(
                config.REASON_DUPLICATE_COLUMNS,
                f"{index[key]!r} and {column!r} both normalize to {key!r}",
            )
        index[key] = column
    return index


def compare_columns(
    master_columns: Sequence[str],
    file_columns: Sequence[str],
    optional: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    """Returns (missing, extra).

    missing: verbatim MASTER names not present in the file, excluding any
             whose normalized form is in `optional`.
    extra:   verbatim FILE names not present in the master.
    Both preserve source order. Purely comparative — no I/O, no mutation.
    """
    optional_keys = {normalize_column(o) for o in optional}
    master_keys = {normalize_column(c) for c in master_columns}
    file_keys = {normalize_column(c) for c in file_columns}

    missing = [
        c for c in master_columns
        if normalize_column(c) not in file_keys and normalize_column(c) not in optional_keys
    ]
    extra = [c for c in file_columns if normalize_column(c) not in master_keys]
    return missing, extra


def tag_study_name(df: pd.DataFrame, study_name: str, column: str) -> pd.DataFrame:
    """Return a copy with `column` set to `study_name` (str) on every row.

    Overwrites the column if present. Never touches other columns.
    """
    result = df.copy()
    result[column] = study_name
    return result


_ZERO_WIDTH_RE = re.compile("[" + re.escape(config.ZERO_WIDTH_CHARS) + "]")


def normalize_header(name: str) -> str:
    """Remove every char in config.ZERO_WIDTH_CHARS, then normalize_column().

    Used by all Phase 2 header matching (P3 signature, upload headers,
    reserved names). normalize_column() alone is not enough here — Ravi's
    original headers end in a zero-width character (U+200B), which
    str.strip() does not remove (finding 2 in PHASE2_ARCHITECTURE.md
    section 0).
    """
    return normalize_column(_ZERO_WIDTH_RE.sub("", name))


def find_phase2_output_headers(columns: Sequence[str]) -> list[str]:
    """Verbatim entries of `columns` whose normalize_header() equals the
    normalize_header() of any config.PHASE2_OUTPUT_SIGNATURE_HEADERS entry,
    in source order. [] means 'not Phase 2 output' (P3).
    """
    signature_keys = {normalize_header(h) for h in config.PHASE2_OUTPUT_SIGNATURE_HEADERS}
    return [c for c in columns if normalize_header(c) in signature_keys]


def column_letter(index: int) -> str:
    """0-based column index -> spreadsheet letters (0 -> 'A', 7 -> 'H', 26 -> 'AA').

    For warning text only — never used for lookup (P24: names, never letters).
    """
    letters = ""
    n = index + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def align_to_master(df: pd.DataFrame, master_columns: Sequence[str]) -> pd.DataFrame:
    """Rename the file's columns to their verbatim master equivalents (matched
    on normalized name) and reindex to master order. Values are NEVER touched.

    Precondition: compare_columns(master_columns, df.columns) returned no
    missing and no extra. Violating it raises SchemaError rather than
    silently producing NaN-filled columns.
    """
    missing, extra = compare_columns(master_columns, list(df.columns))
    if missing or extra:
        raise SchemaError(
            config.REASON_COLUMN_MISMATCH,
            f"align_to_master precondition violated: missing={missing}, extra={extra}",
        )

    master_index = build_column_index(master_columns)
    rename_map = {col: master_index[normalize_column(col)] for col in df.columns}
    renamed = df.rename(columns=rename_map)
    return renamed.reindex(columns=list(master_columns))
