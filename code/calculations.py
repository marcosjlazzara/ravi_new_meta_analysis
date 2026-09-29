"""
calculations.py — Master frame -> 8 calculated columns + calculation warnings.

PHASE2_ARCHITECTURE.md section 3 (P20-P25). build_calculations() never raises
on a data problem — every problem becomes blank output cells plus a warning.
The single halt this module could produce (a duplicate normalized column in
master_df) cannot occur in practice: MasterContext is only ever built through
master_detector, which already guarantees unique normalized column names.

This module does NOT import `decimal`. `numeric.py` is the only module that
does (module map, PHASE2_ARCHITECTURE.md section 1); the Inexact signal this
module needs to catch is reached via `numeric.Inexact`, an attribute numeric.py
already exposes because it imports that name from `decimal` itself.
"""

from __future__ import annotations

import pandas as pd

import config
import numeric
from models import CalculationResult, Phase2Warning
from schema import build_column_index, normalize_column

_ROLES: tuple[str, ...] = (config.DEP_VAR_PEN, config.DEP_VAR_OCC, config.DEP_VAR_DOLHH)

# Section 3.1 dependency map: which calculated headers a given source column
# feeds. `dependent_variable` feeds every header except the always-empty
# Offline column (handled as an early-return special case, since without it
# no row role can be determined at all).
_NON_OFFLINE_HEADERS: tuple[str, ...] = tuple(
    h for h in config.CALCULATED_HEADERS if h != config.CALC_OFFLINE_NEW_BUYERS
)
_G_DEPENDENTS: tuple[str, ...] = (
    config.CALC_TOTAL_ANALYZED_POPULATION,
    config.CALC_COUNT_CIRCANA_BUYERS,
    config.CALC_TOTAL_DOLLARS,
    config.CALC_TOTAL_TRIPS,
)
_N_DEPENDENTS: tuple[str, ...] = (
    config.CALC_COUNT_CIRCANA_BUYERS,
    config.CALC_PARTNER_MEMBER_OVERLAP,
    config.CALC_DOLLARS_PER_HH,
    config.CALC_TOTAL_DOLLARS,
    config.CALC_TOTAL_TRIPS,
    config.CALC_TRIPS_PER_BUYER,
)
_BLOCK_DEPENDENTS: tuple[str, ...] = (
    config.CALC_COUNT_CIRCANA_BUYERS,
    config.CALC_TOTAL_TRIPS,
)


def build_calculations(master_df: pd.DataFrame, am_round_2dp: bool | None = None) -> CalculationResult:
    """Section 3. Never raises on data problems. master_df is read-only here
    (never mutated); am_round_2dp None -> config.AM_ROUND_TO_2DP.
    """
    n = len(master_df)
    am_round = config.AM_ROUND_TO_2DP if am_round_2dp is None else am_round_2dp

    out: dict[str, list[str]] = {h: [""] * n for h in config.CALCULATED_HEADERS}
    warnings: list[Phase2Warning] = []

    column_index = build_column_index(list(master_df.columns))

    def _resolve(name: str) -> str | None:
        return column_index.get(normalize_column(name))

    f_col = _resolve(config.DEPENDENT_VARIABLE_COL)
    g_col = _resolve(config.CNT_EXPSD_HH_COL)
    n_col = _resolve(config.ADJ_MEAN_EXPSD_GRP_COL)
    md_col = _resolve(config.MODEL_DESC_COL)
    model_col = _resolve(config.MODEL_COL)
    study_col = _resolve(config.STUDY_NAME_COL)

    # --- section 3.1: missing-source-column warnings, fixed order F,G,N,MD,Model
    for source_name, resolved, dependents in (
        (config.DEPENDENT_VARIABLE_COL, f_col, _NON_OFFLINE_HEADERS),
        (config.CNT_EXPSD_HH_COL, g_col, _G_DEPENDENTS),
        (config.ADJ_MEAN_EXPSD_GRP_COL, n_col, _N_DEPENDENTS),
        (config.MODEL_DESC_COL, md_col, _BLOCK_DEPENDENTS),
        (config.MODEL_COL, model_col, _BLOCK_DEPENDENTS),
    ):
        if resolved is None:
            warnings.append(
                Phase2Warning(
                    study="",
                    model="",
                    column=source_name,
                    issue=config.ISSUE_SOURCE_COLUMN_MISSING.format(
                        headers=config.LIST_JOIN_SEPARATOR.join(dependents)
                    ),
                    code=config.P2W_SOURCE_COLUMN_MISSING,
                )
            )
            if source_name == config.DEPENDENT_VARIABLE_COL:
                # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md
                # section 11, item 1: a needed input that cannot be found makes every
                # dependent output blank. Without dependent_variable no row role can
                # ever be determined, so the whole frame is returned immediately.
                frame = pd.DataFrame(out, columns=list(config.CALCULATED_HEADERS), dtype=object)
                return CalculationResult(frame=frame, warnings=warnings)

    have_g = g_col is not None
    have_n = n_col is not None
    have_block = md_col is not None and model_col is not None

    study_values: list[str] = master_df[study_col].tolist() if study_col is not None else [""] * n

    # --- section 3.2: row roles -------------------------------------------------
    # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11,
    # item 3: dependent_variable is compared after strip + casefold. Unknown values
    # (design default 4) simply get role None, silently — no warning.
    role_raw: list[str] = [master_df.iloc[i][f_col].strip() for i in range(n)]
    roles: list[str | None] = [r.casefold() if r.casefold() in _ROLES else None for r in role_raw]

    def _block_label(row_idx: int) -> str:
        # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item 5
        if not have_block:
            return ""
        return config.BLOCK_LABEL_PATTERN.format(
            model_desc=master_df.iloc[row_idx][md_col].strip(),
            model=master_df.iloc[row_idx][model_col].strip(),
        )

    # --- section 3.5: cell parsing / problem recording --------------------------
    # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11,
    # item 1: a problem cell is keyed by (row, source column); every output header
    # it blanks accumulates onto the SAME warning, which is emitted once, listing
    # every header it blanked.
    _cell_cache: dict[tuple[int, str], tuple[str, object]] = {}
    _cell_headers: dict[tuple[int, str], set[str]] = {}

    def _get_value(row_idx: int, col: str, header: str):
        key = (row_idx, col)
        if key not in _cell_cache:
            raw = master_df.iloc[row_idx][col]
            try:
                parsed = numeric.parse_number(raw)
            except numeric.NotANumber:
                _cell_cache[key] = ("not_numeric", raw.strip()[:40])
            else:
                _cell_cache[key] = ("blank", "") if parsed is None else ("ok", parsed)
        kind, payload = _cell_cache[key]
        if kind == "ok":
            return payload
        _cell_headers.setdefault(key, set()).add(header)
        return None

    precision_issues: list[tuple[int, str]] = []

    def _multiply_or_blank(row_idx: int, header: str, *values) -> str:
        try:
            result = numeric.multiply(*values)
        except numeric.Inexact:
            precision_issues.append((row_idx, header))
            return ""
        return numeric.format_number(result)

    # --- section 3.3: single-row columns ----------------------------------------
    for i in range(n):
        role = roles[i]
        if role == config.DEP_VAR_DOLHH:
            if have_g:
                g_val = _get_value(i, g_col, config.CALC_TOTAL_ANALYZED_POPULATION)
                if g_val is not None:
                    # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md
                    # section 11, item 2: copy columns go through format_number
                    # (normalised text), they are not byte-copied from the source cell.
                    out[config.CALC_TOTAL_ANALYZED_POPULATION][i] = numeric.format_number(g_val)
            if have_n:
                n_val = _get_value(i, n_col, config.CALC_DOLLARS_PER_HH)
                if n_val is not None:
                    out[config.CALC_DOLLARS_PER_HH][i] = numeric.format_number(n_val)
            if have_n and have_g:
                n_val_td = _get_value(i, n_col, config.CALC_TOTAL_DOLLARS)
                g_val_td = _get_value(i, g_col, config.CALC_TOTAL_DOLLARS)
                if n_val_td is not None and g_val_td is not None:
                    out[config.CALC_TOTAL_DOLLARS][i] = _multiply_or_blank(
                        i, config.CALC_TOTAL_DOLLARS, n_val_td, g_val_td
                    )
        elif role == config.DEP_VAR_PEN:
            if have_n:
                n_val = _get_value(i, n_col, config.CALC_PARTNER_MEMBER_OVERLAP)
                if n_val is not None:
                    out[config.CALC_PARTNER_MEMBER_OVERLAP][i] = numeric.format_number(n_val)
        elif role == config.DEP_VAR_OCC:
            if have_n:
                n_val = _get_value(i, n_col, config.CALC_TRIPS_PER_BUYER)
                if n_val is not None:
                    if am_round:
                        out[config.CALC_TRIPS_PER_BUYER][i] = numeric.format_rounded(
                            n_val, config.AM_ROUND_QUANTUM
                        )
                    else:
                        out[config.CALC_TRIPS_PER_BUYER][i] = numeric.format_number(n_val)

    # --- section 3.4: block matching (cross-row columns) ------------------------
    block_warning_records: list[tuple[int, int, Phase2Warning]] = []
    if have_block:
        blocks: dict[tuple[str, str, str], list[int]] = {}
        for i in range(n):
            key = (
                study_values[i].strip(),
                master_df.iloc[i][md_col].strip(),
                master_df.iloc[i][model_col].strip(),
            )
            blocks.setdefault(key, []).append(i)

        for block_rows in blocks.values():
            by_role: dict[str, list[int]] = {r: [] for r in _ROLES}
            for r in block_rows:
                role = roles[r]
                if role is not None:
                    by_role[role].append(r)

            missing_roles = [r for r in _ROLES if not by_role[r]]
            dup_roles = [r for r in _ROLES if len(by_role[r]) > 1]
            anchor_row = block_rows[0]
            block_study = study_values[anchor_row]
            block_model_label = _block_label(anchor_row)
            headers_str = config.LIST_JOIN_SEPARATOR.join(_BLOCK_DEPENDENTS)

            # DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md
            # section 11, item 4: one warning per problem type (missing / duplicated).
            if missing_roles:
                roles_str = ", ".join(f"'{r}'" for r in missing_roles)
                block_warning_records.append((
                    anchor_row,
                    0,
                    Phase2Warning(
                        study=block_study,
                        model=block_model_label,
                        column=f_col,
                        issue=config.ISSUE_BLOCK_ROLE_MISSING.format(roles=roles_str, headers=headers_str),
                        code=config.P2W_BLOCK_ROLE_MISSING,
                    ),
                ))
            if dup_roles:
                roles_str = ", ".join(f"'{r}' ({len(by_role[r])} rows)" for r in dup_roles)
                block_warning_records.append((
                    anchor_row,
                    0,
                    Phase2Warning(
                        study=block_study,
                        model=block_model_label,
                        column=f_col,
                        issue=config.ISSUE_BLOCK_ROLE_DUPLICATED.format(roles=roles_str, headers=headers_str),
                        code=config.P2W_BLOCK_ROLE_DUPLICATED,
                    ),
                ))

            if missing_roles or dup_roles:
                continue

            p = by_role[config.DEP_VAR_PEN][0]
            o = by_role[config.DEP_VAR_OCC][0]
            d = by_role[config.DEP_VAR_DOLHH][0]

            if have_n and have_g:
                n_p_count = _get_value(p, n_col, config.CALC_COUNT_CIRCANA_BUYERS)
                g_d_count = _get_value(d, g_col, config.CALC_COUNT_CIRCANA_BUYERS)
                if n_p_count is not None and g_d_count is not None:
                    out[config.CALC_COUNT_CIRCANA_BUYERS][p] = _multiply_or_blank(
                        p, config.CALC_COUNT_CIRCANA_BUYERS, n_p_count, g_d_count
                    )

                n_p_trips = _get_value(p, n_col, config.CALC_TOTAL_TRIPS)
                g_d_trips = _get_value(d, g_col, config.CALC_TOTAL_TRIPS)
                n_o_trips = _get_value(o, n_col, config.CALC_TOTAL_TRIPS)
                if n_p_trips is not None and g_d_trips is not None and n_o_trips is not None:
                    out[config.CALC_TOTAL_TRIPS][p] = _multiply_or_blank(
                        p, config.CALC_TOTAL_TRIPS, n_p_trips, g_d_trips, n_o_trips
                    )

    # --- section 3.6: deterministic warning emission order -----------------------
    value_warning_records: list[tuple[int, int, Phase2Warning]] = []
    for (row_idx, col), headers in _cell_headers.items():
        kind, payload = _cell_cache[(row_idx, col)]
        headers_sorted = sorted(headers, key=lambda h: config.CALCULATED_HEADERS.index(h))
        headers_str = config.LIST_JOIN_SEPARATOR.join(headers_sorted)
        role_text = role_raw[row_idx]
        study_val = study_values[row_idx]
        model_label = _block_label(row_idx)
        if kind == "blank":
            issue = config.ISSUE_VALUE_BLANK.format(role=role_text, row=row_idx + 2, headers=headers_str)
            code = config.P2W_VALUE_BLANK
        else:
            issue = config.ISSUE_VALUE_NOT_NUMERIC.format(
                value=payload, role=role_text, row=row_idx + 2, headers=headers_str
            )
            code = config.P2W_VALUE_NOT_NUMERIC
        value_warning_records.append((
            row_idx,
            1,
            Phase2Warning(study=study_val, model=model_label, column=col, issue=issue, code=code),
        ))

    precision_warning_records: list[tuple[int, int, Phase2Warning]] = []
    for row_idx, header in precision_issues:
        study_val = study_values[row_idx]
        model_label = _block_label(row_idx)
        issue = config.ISSUE_VALUE_TOO_PRECISE.format(
            prec=config.ARITH_PRECISION, row=row_idx + 2, headers=header
        )
        precision_warning_records.append((
            row_idx,
            2,
            Phase2Warning(
                study=study_val, model=model_label, column=header, issue=issue,
                code=config.P2W_VALUE_TOO_PRECISE,
            ),
        ))

    ordered = block_warning_records + value_warning_records + precision_warning_records
    ordered.sort(key=lambda rec: (rec[0], rec[1]))
    warnings.extend(rec[2] for rec in ordered)

    frame = pd.DataFrame(out, columns=list(config.CALCULATED_HEADERS), dtype=object)
    return CalculationResult(frame=frame, warnings=warnings)
