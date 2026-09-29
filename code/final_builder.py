"""
final_builder.py — master + calculations + ParsedUpload -> FinalResult.

PHASE2_ARCHITECTURE.md sections 1.11 and 7.4 (P12-P13 matching, P16/P17 value
check, P26/P27 layout/merge). build_final() never raises on a DATA problem —
every mismatch becomes a warning, never a halt. The only exceptions it raises
are ValueError (a precondition violation — a programming error, not data) and
RuntimeError (the fail-loud layout asserts in step 6, which should be
unreachable given a correctly built ParsedUpload/CalculationResult).
"""

from __future__ import annotations

import pandas as pd

import config
from models import CalculationResult, FinalResult, ParsedUpload, Phase2Warning
from numeric import is_plain_number
from schema import build_column_index, normalize_column


def build_final(
    master_df: pd.DataFrame,
    calculations: CalculationResult,
    upload: ParsedUpload,
    value_check: bool | None = None,
) -> FinalResult:
    """Section 7.4. Precondition (raises ValueError): upload.accepted and
    len(calculations.frame) == len(master_df). value_check None ->
    config.VALUE_CHECK_ENABLED.
    """
    if not upload.accepted:
        raise ValueError("build_final called with a refused ParsedUpload (accepted=False)")
    if len(calculations.frame) != len(master_df):
        raise ValueError(
            f"calculations.frame length ({len(calculations.frame)}) != "
            f"master_df length ({len(master_df)})"
        )

    value_check_on = config.VALUE_CHECK_ENABLED if value_check is None else value_check

    # 1. Study_Name column, master keys in first-appearance order -------------
    column_index = build_column_index(list(master_df.columns))
    study_col = column_index[normalize_column(config.STUDY_NAME_COL)]
    study_values = master_df[study_col].tolist()

    master_keys_order: list[str] = []
    master_key_display: dict[str, str] = {}
    row_keys: list[str | None] = []
    blank_study_count = 0
    for value in study_values:
        if value.strip() == "":
            blank_study_count += 1
            row_keys.append(None)
            continue
        key = value.strip().casefold()
        row_keys.append(key)
        if key not in master_key_display:
            master_key_display[key] = value
            master_keys_order.append(key)

    warnings: list[Phase2Warning] = list(calculations.warnings)
    calculation_warning_count = len(warnings)

    # 2. matching / zero-match --------------------------------------------------
    master_keys_set = set(master_keys_order)
    upload_keys_set = set(upload.rows_by_study.keys())
    matched = master_keys_set & upload_keys_set
    zero_match = not matched
    upload_study_count = len(upload.rows_by_study)

    if zero_match:
        warnings.append(
            Phase2Warning(
                study="",
                model="",
                column=config.STUDY_NAME_COL,
                issue=config.ISSUE_UPLOAD_ZERO_MATCH.format(n=upload_study_count),
                code=config.P2W_UPLOAD_ZERO_MATCH,
            )
        )

    warnings.extend(upload.warnings)

    # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
    # item 14 (second half): blank-name master rows are excluded from the template
    # (template_builder.list_template_studies) and get blank merged columns here,
    # plus this one summary warning.
    if blank_study_count:
        warnings.append(
            Phase2Warning(
                study="",
                model="",
                column=config.STUDY_NAME_COL,
                issue=config.ISSUE_MASTER_BLANK_STUDY.format(count=blank_study_count),
                code=config.P2W_MASTER_BLANK_STUDY,
            )
        )

    # 3. per-master-study matching, value check --------------------------------
    # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
    # item 16: the P16 value check runs only on values that are actually merged
    # (checked_headers is present_fixed-gated, and the check itself sits inside
    # the single-filled-row branch below, never on a blank or duplicated study).
    checked_headers = [h for h in config.NUMERIC_CHECKED_HEADERS if h in upload.present_fixed]
    values_by_key: dict[str, dict[str, str]] = {}
    for key in master_keys_order:
        display_name = master_key_display[key]
        upload_rows = upload.rows_by_study.get(key, [])
        # DESIGN DEFAULT — confirmed 2026-09-29, see PHASE2_ARCHITECTURE.md section 11,
        # item 15: all-blank upload rows do not count towards P13's "same study twice".
        filled_rows = [r for r in upload_rows if any(v.strip() != "" for v in r.values.values())]

        if not upload_rows:
            warnings.append(
                Phase2Warning(
                    study=display_name,
                    model="",
                    column=config.STUDY_NAME_COL,
                    issue=config.ISSUE_STUDY_NOT_IN_UPLOAD,
                    code=config.P2W_STUDY_NOT_IN_UPLOAD,
                )
            )
        elif not filled_rows:
            pass  # "not filled in yet" — blank merge, no warning (P13)
        elif len(filled_rows) == 1:
            row = filled_rows[0]
            values_by_key[key] = row.values
            if value_check_on:
                for header in checked_headers:
                    value = row.values.get(header, "")
                    if value.strip() != "" and not is_plain_number(value):
                        warnings.append(
                            Phase2Warning(
                                study=display_name,
                                model="",
                                column=header,
                                issue=config.ISSUE_VALUE_NOT_PLAIN_NUMBER.format(value=value),
                                code=config.P2W_VALUE_NOT_PLAIN_NUMBER,
                            )
                        )
        else:
            rows_str = config.LIST_JOIN_SEPARATOR.join(str(r.row_number) for r in filled_rows)
            warnings.append(
                Phase2Warning(
                    study=display_name,
                    model="",
                    column=config.STUDY_NAME_COL,
                    issue=config.ISSUE_STUDY_DUPLICATED.format(count=len(filled_rows), rows=rows_str),
                    code=config.P2W_STUDY_DUPLICATED,
                )
            )

    # 4. upload keys not in the master, in upload order ------------------------
    for key, upload_rows in upload.rows_by_study.items():
        if key in master_keys_set:
            continue
        display_name = upload_rows[0].study_name
        rows_str = config.LIST_JOIN_SEPARATOR.join(str(r.row_number) for r in upload_rows)
        warnings.append(
            Phase2Warning(
                study=display_name,
                model="",
                column=config.STUDY_NAME_COL,
                issue=config.ISSUE_STUDY_NOT_IN_MASTER.format(rows=rows_str),
                code=config.P2W_STUDY_NOT_IN_MASTER,
            )
        )

    # 5. merged frame — values repeated on every row of the study (P27) --------
    merge_columns = upload.merge_columns
    merged_data: dict[str, list[str]] = {col: [] for col in merge_columns}
    for row_key in row_keys:
        row_values = values_by_key.get(row_key, {}) if row_key is not None else {}
        for col in merge_columns:
            merged_data[col].append(row_values.get(col, ""))
    merged = pd.DataFrame(merged_data, columns=merge_columns, dtype=object)

    # 6. concat + fail-loud layout asserts (P26) --------------------------------
    final = pd.concat(
        [master_df.reset_index(drop=True), calculations.frame.reset_index(drop=True), merged],
        axis=1,
    )
    expected_columns = list(master_df.columns) + list(config.CALCULATED_HEADERS) + list(merge_columns)
    if list(final.columns) != expected_columns:
        raise RuntimeError(
            f"build_final layout assertion failed: columns {list(final.columns)} != "
            f"expected {expected_columns}"
        )
    if len(set(final.columns)) != len(final.columns):
        raise RuntimeError(f"build_final layout assertion failed: duplicate column names in {list(final.columns)}")
    if len(final) != len(master_df):
        raise RuntimeError(
            f"build_final layout assertion failed: len(final)={len(final)} != len(master_df)={len(master_df)}"
        )

    upload_warning_count = len(warnings) - calculation_warning_count

    return FinalResult(
        frame=final,
        warnings=warnings,
        calculation_warning_count=calculation_warning_count,
        upload_warning_count=upload_warning_count,
        zero_match=zero_match,
        upload_study_count=upload_study_count,
    )
