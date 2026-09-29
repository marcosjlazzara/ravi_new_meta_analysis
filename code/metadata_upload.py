"""
metadata_upload.py — Completed-template bytes -> ParsedUpload.

PHASE2_ARCHITECTURE.md sections 1.10 and 7.1-7.3 (P10-P18, P26-P27's inputs).
parse_upload() never raises: every refusal (P11) comes back as
accepted=False with a refusal_message, never an exception. No streamlit
import, no filesystem writes, zero arithmetic beyond counting/joining.
"""

from __future__ import annotations

from typing import Sequence

import config
from file_reader import FileReadError, read_raw_grid
from models import ParsedUpload, Phase2Warning, UploadRow
from schema import column_letter, normalize_header

_STUDY_NAME_KEY = normalize_header(config.STUDY_NAME_COL)
_FIXED_KEYS: tuple[str, ...] = tuple(normalize_header(h) for h in config.TEMPLATE_VALUE_HEADERS)


def _refused(message: str) -> ParsedUpload:
    return ParsedUpload(
        accepted=False,
        refusal_message=message,
        merge_columns=[],
        present_fixed=frozenset(),
        rows_by_study={},
        warnings=[],
    )


def parse_upload(filename: str, data: bytes, master_columns: Sequence[str]) -> ParsedUpload:
    """Section 7.1-7.3. Never raises. Refusals come back as accepted=False."""

    # 1. read_raw_grid -----------------------------------------------------
    try:
        grid = read_raw_grid(filename, data)
    except FileReadError as e:
        detail = e.detail or e.reason
        return _refused(config.MSG_UPLOAD_UNREADABLE.format(detail=detail))

    if not grid:
        return _refused(config.MSG_WRONG_FILE)

    # 2. headers / body -----------------------------------------------------
    headers = [h.strip() for h in grid[0]]
    body = grid[1:]

    # 3. Study_Name column(s) -------------------------------------------------
    study_positions = [j for j, h in enumerate(headers) if normalize_header(h) == _STUDY_NAME_KEY]
    if not study_positions:
        return _refused(config.MSG_WRONG_FILE)

    # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
    # item 10: two Study_Name columns -> the leftmost is used, the rest warned + ignored.
    study_pos = study_positions[0]
    warnings: list[Phase2Warning] = []
    for extra_pos in study_positions[1:]:
        warnings.append(
            Phase2Warning(
                study="",
                model="",
                column=headers[extra_pos],
                issue=config.ISSUE_UPLOAD_SECOND_STUDY_NAME.format(
                    letter=column_letter(extra_pos), first_letter=column_letter(study_pos)
                ),
                code=config.P2W_UPLOAD_SECOND_STUDY_NAME,
            )
        )

    # 4. master-lookalike refusal (P11, ruling C2) ---------------------------
    # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
    # item 8: "contains master columns" means carrying ALL of MASTER_LOOKALIKE_COLUMNS.
    header_keys = {normalize_header(h) for h in headers}
    lookalike_keys = {normalize_header(c) for c in config.MASTER_LOOKALIKE_COLUMNS}
    if lookalike_keys.issubset(header_keys):
        return _refused(config.MSG_UPLOAD_IS_MASTER)

    # 5. header classification (7.2), left to right --------------------------
    # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
    # item 13: the reserved set for extras also includes the calculated headers,
    # the legacy header and TEMPLATE_HEADERS, not just the master's own columns.
    reserved_keys = {normalize_header(c) for c in master_columns}
    reserved_keys |= {normalize_header(h) for h in config.CALCULATED_HEADERS}
    reserved_keys |= {normalize_header(h) for h in config.LEGACY_CALCULATED_HEADERS}
    reserved_keys |= {normalize_header(h) for h in config.TEMPLATE_HEADERS}

    fixed_occurrences: dict[str, list[int]] = {}
    extra_candidates: dict[str, list[tuple[int, str]]] = {}
    ignored_positions = set(study_positions)

    for j, h in enumerate(headers):
        if j in ignored_positions:
            continue
        if h == "":
            if any(j < len(row) and row[j].strip() != "" for row in body):
                warnings.append(
                    Phase2Warning(
                        study="",
                        model="",
                        column="",
                        issue=config.ISSUE_UPLOAD_BLANK_HEADER.format(letter=column_letter(j)),
                        code=config.P2W_UPLOAD_BLANK_HEADER,
                    )
                )
            continue

        key = normalize_header(h)
        if key in _FIXED_KEYS:
            fixed_occurrences.setdefault(key, []).append(j)
            continue
        if j >= config.EXTRAS_START_COL_INDEX:
            extra_candidates.setdefault(key, []).append((j, h))
            continue

        # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
        # item 11: fixed headers are matched by name at any position (checked above,
        # before this branch); an unknown header in columns A-G is ignored + warned.
        warnings.append(
            Phase2Warning(
                study="",
                model="",
                column=h,
                issue=config.ISSUE_UPLOAD_UNEXPECTED_COLUMN.format(letter=column_letter(j)),
                code=config.P2W_UPLOAD_UNEXPECTED_COLUMN,
            )
        )

    # --- fixed headers, in config order --------------------------------------
    present_fixed: set[str] = set()
    fixed_col_position: dict[str, int] = {}
    for fixed_header in config.TEMPLATE_VALUE_HEADERS:
        key = normalize_header(fixed_header)
        positions = fixed_occurrences.get(key, [])
        if len(positions) == 1:
            present_fixed.add(fixed_header)
            fixed_col_position[fixed_header] = positions[0]
        elif len(positions) == 0:
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=fixed_header,
                    issue=config.ISSUE_UPLOAD_FIXED_MISSING,
                    code=config.P2W_UPLOAD_FIXED_MISSING,
                )
            )
        else:
            # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section
            # 11, item 12: a duplicated header (fixed or extra) has ALL its occurrences
            # ignored, with a warning — nobody guesses which copy is right.
            letters = config.LIST_JOIN_SEPARATOR.join(column_letter(p) for p in positions)
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=fixed_header,
                    issue=config.ISSUE_UPLOAD_FIXED_DUPLICATED.format(count=len(positions), letters=letters),
                    code=config.P2W_UPLOAD_FIXED_DUPLICATED,
                )
            )

    # --- extras, grouped by normalized name, first-appearance order ---------
    accepted_extra_position: dict[str, int] = {}
    for key, entries in extra_candidates.items():
        letters = config.LIST_JOIN_SEPARATOR.join(column_letter(p) for p, _ in entries)
        first_header = entries[0][1]
        if key in reserved_keys:
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=first_header,
                    issue=config.ISSUE_UPLOAD_EXTRA_RESERVED.format(letters=letters),
                    code=config.P2W_UPLOAD_EXTRA_RESERVED,
                )
            )
            continue
        if len(entries) > 1:
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=first_header,
                    issue=config.ISSUE_UPLOAD_EXTRA_DUPLICATED.format(count=len(entries), letters=letters),
                    code=config.P2W_UPLOAD_EXTRA_DUPLICATED,
                )
            )
            continue

        pos, header_text = entries[0]
        accepted_extra_position[header_text] = pos
        if len(header_text) > config.EXTRA_HEADER_MAX_LEN:
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=header_text,
                    issue=config.ISSUE_UPLOAD_EXTRA_TOO_LONG.format(length=len(header_text)),
                    code=config.P2W_UPLOAD_EXTRA_TOO_LONG,
                )
            )

    merge_columns = list(config.TEMPLATE_VALUE_HEADERS) + list(accepted_extra_position.keys())
    col_position: dict[str, int] = {**fixed_col_position, **accepted_extra_position}

    # 6. rows (7.3) ------------------------------------------------------------
    rows_by_study: dict[str, list[UploadRow]] = {}
    for r, row in enumerate(body):
        row_number = r + 2
        name = row[study_pos] if study_pos < len(row) else ""
        values = {
            col: (row[pos] if pos < len(row) else "")
            for col, pos in col_position.items()
        }
        # every merge column must be present, "" if not merged in this upload
        values = {col: values.get(col, "") for col in merge_columns}

        # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
        # item 14: a row with values but no study name is ignored with a warning; a
        # row with no study name and no values is ignored silently.
        if name.strip() == "":
            if any(v.strip() != "" for v in values.values()):
                warnings.append(
                    Phase2Warning(
                        study="",
                        model="",
                        column=config.STUDY_NAME_COL,
                        issue=config.ISSUE_UPLOAD_ROW_NO_STUDY.format(row=row_number),
                        code=config.P2W_UPLOAD_ROW_NO_STUDY,
                    )
                )
            continue

        key = name.strip().casefold()
        rows_by_study.setdefault(key, []).append(
            UploadRow(study_name=name, values=values, row_number=row_number)
        )

    # 7. accepted --------------------------------------------------------------
    return ParsedUpload(
        accepted=True,
        refusal_message="",
        merge_columns=merge_columns,
        present_fixed=frozenset(present_fixed),
        rows_by_study=rows_by_study,
        warnings=warnings,
    )
