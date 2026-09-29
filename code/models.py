"""
models.py — Data contracts passed between modules. No behaviour beyond the
documented @property helpers. Nothing here reads a file or touches pandas
beyond typing a DataFrame field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class UploadedItem:
    """One file as handed to the pipeline. app.py builds these from st.file_uploader."""

    index: int      # position in the upload list — the ONLY stable identity key
    name: str       # verbatim filename incl. extension
    data: bytes     # full file bytes, read once by app.py

    @property
    def stem(self) -> str:
        """Filename minus final extension, otherwise verbatim."""
        return Path(self.name).stem

    @property
    def extension(self) -> str:
        """Lowercased, incl. dot."""
        return Path(self.name).suffix.lower()


@dataclass(frozen=True)
class MasterCandidate:
    """A file whose stem starts with 'master_' (case-insensitive)."""

    index: int
    name: str
    readable: bool
    has_study_name: bool
    error: str                       # "" when readable
    is_phase2_output: bool = False   # NEW (P3). Defaulted: every existing construction still works.

    @property
    def is_valid(self) -> bool:
        """readable and has_study_name and not is_phase2_output."""
        return self.readable and self.has_study_name and not self.is_phase2_output


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


# =============================================================================
# PHASE 2 — study metadata & calculations. Not yet consumed outside their own
# stage's module (Stages 2-4 build the producers/consumers) — added now, per
# PHASE2_ARCHITECTURE.md section 1.2, so later stages need no models.py churn.
# =============================================================================


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
