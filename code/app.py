"""
app.py — ORCHESTRATOR (start here if you are now reading this code)

This is the only file that runs directly, and the ONLY file in code/ that
imports streamlit. It controls the full flow, top to bottom, exactly as
specified in ARCHITECTURE.md section 2:

  STEP 0  Page config + title. st.session_state is Streamlit's own
          persistent store across reruns, so the download payloads it
          holds (written in STEP 5) are read directly at their point of
          use in STEP 6 rather than shadowed into local variables here —
          one source of truth, no risk of a stale copy.

  STEP 1  INPUT — user drops the whole batch (study files + master, if any).
          Bytes are read exactly once into UploadedItem; nothing downstream
          touches a Streamlit object again.

  STEP 2  MASTER DETECTION — 0 / 1 / >1 valid Master_* candidates.
          master_detector.py  -> find_master_candidates(), build_master_context_from_existing()
  STEP 2b FIRST-MASTER SLOT — renders only when zero valid candidates exist.
          master_detector.py  -> build_master_context_from_first_file()

  STEP 3  MASTER LOADED — caption summarising the schema authority.
          The only place a failure halts the run (no master = no schema to
          validate against) — this applies to BOTH master-construction call
          sites (resume path and first-master path); see _load_master().

  STEP 4  STUDY NAME REVIEW — editable table, default = filename stem.
          Rendered only once a master schema exists (nothing to review
          against before then).

  STEP 5  RUN — study_processor.py -> process_batch(). Builds both CSV byte
          payloads and both filenames immediately and stores them in
          st.session_state, because a download_button click triggers a
          Streamlit rerun and anything computed only inside `if
          st.button(...)` would vanish on that rerun.

  STEP 6  OUTPUT — rendered from st.session_state, OUTSIDE the button block:
          report.py -> summarize() / outcomes_to_frame() / build_exception_report()
          csv_writer.py -> to_csv_bytes() / build_master_filename() / build_exception_filename()
          Two st.download_button calls; the exception report is always
          offered, even when empty, so the user never wonders if it failed.

  --- PHASE 2 — study metadata & calculations (PHASE2_ARCHITECTURE.md section 8) ---
  Rendered only when result is not None AND "p2_calc" is in st.session_state
  (i.e. only after a successful Run). p2_calc / p2_base_name / the template
  bytes+filename+study count are all written once, inside the Run block
  above, from the same `now`, alongside the Phase 1 session_state writes —
  they depend only on the just-built master, which changes only on Run.

  STEP 7  Download template — template_builder.py -> build_template_bytes(),
          list_template_studies(). One download button (the blank
          studyname_master workbook) plus a Glossary expander (fields table,
          extras note, rules, calculated-column note and table).

  STEP 8  Upload completed template — metadata_upload.py -> parse_upload().
          A single .xlsx/.csv uploader. An empty slot shows the upload
          prompt; the CSV-caution caption (ruling C5) is always shown below
          it. A refused upload shows its refusal message and STEP 9 does not
          render.

  STEP 9  Final file — final_builder.py -> build_final(), recomputed on
          EVERY rerun from the current master (st.session_state["result"])
          and the current upload (P29: never cached, unlike p2_calc).
          report.py -> phase2_warnings_to_frame() / summarize_phase2_warnings().
          csv_writer.py -> build_final_filename() / build_phase2_warnings_filename().
          Two more download buttons (after_formulas_master always; the
          phase2_warnings CSV only when there are warnings).

Module map:
  config.py               — constants (extensions, prefix, status/reason strings, patterns)
  models.py                — dataclasses passed between modules (UploadedItem, MasterContext, ...)
  file_reader.py            — bytes -> all-string DataFrame (+ read_raw_grid, header-less)
  master_detector.py         — finds/validates the master; builds MasterContext
  schema.py                   — column normalization, comparison, reordering, tagging
  study_processor.py           — per-file pipeline + batch loop -> BatchResult
  report.py                     — BatchResult -> exception report + summary dict
                                   (+ phase2_warnings_to_frame / summarize_phase2_warnings)
  csv_writer.py                  — timestamped filenames + UTF-8-BOM bytes
                                   (+ template/final/phase2_warnings filename builders)
  numeric.py                      — exact-decimal parse/format/multiply (Phase 2)
  calculations.py                  — master frame -> 8 calculated columns + warnings (Phase 2)
  template_builder.py                — distinct study list -> studyname_master .xlsx bytes (Phase 2)
  metadata_upload.py                  — completed-template bytes -> ParsedUpload (Phase 2)
  final_builder.py                     — master + calculations + ParsedUpload -> FinalResult (Phase 2)
  test_meta_pipeline.py                 — python test_meta_pipeline.py
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

import pandas as pd
import streamlit as st

import config
from calculations import build_calculations
from csv_writer import (
    build_exception_filename,
    build_final_filename,
    build_master_filename,
    build_phase2_warnings_filename,
    build_template_filename,
    to_csv_bytes,
)
from file_reader import FileReadError
from final_builder import build_final
from master_detector import (
    build_master_context_from_existing,
    build_master_context_from_first_file,
    find_master_candidates,
    first_master_slot_allowed,
    sanitize_base_name,
)
from metadata_upload import parse_upload
from models import FileOutcome, MasterContext, UploadedItem
from report import (
    build_exception_report,
    outcomes_to_frame,
    phase2_warnings_to_frame,
    rejected_files_message,
    summarize,
    summarize_phase2_warnings,
)
from schema import SchemaError
from study_processor import is_run_ready, process_batch
from template_builder import build_template_bytes, list_template_studies

# ---------------------------------------------------------------------------
# STEP 0 — page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Meta Analysis Consolidation", layout="wide")
st.title("Meta Analysis Consolidation")
st.caption("Drop your batch of study files plus the master (or the first file to become one).")
st.caption(
    "If you already have a master file, please make sure its filename starts with "
    "\"Master_\" — including the underscore — otherwise it will not be recognised."
)

# ---------------------------------------------------------------------------
# STEP 1 — input section
# ---------------------------------------------------------------------------
uploads = st.file_uploader(
    "Drop the whole batch",
    type=["csv", "xlsx"],
    accept_multiple_files=True,
)

if not uploads:
    st.info("Upload the study files plus your master (or your first file to become one) to begin.")
    st.stop()

# Bytes are read exactly once, immediately. Nothing downstream touches a
# Streamlit UploadedFile object. `index` (upload position) is the ONLY
# stable identity key — never de-duplicate by filename (duplicate names are
# legal, edge case 15).
items: list[UploadedItem] = [
    UploadedItem(index=i, name=f.name, data=f.getvalue()) for i, f in enumerate(uploads)
]
items_by_index: dict[int, UploadedItem] = {item.index: item for item in items}

# ---------------------------------------------------------------------------
# STEP 2 — master detection
# ---------------------------------------------------------------------------
st.header("Master detection")

candidates = find_master_candidates(items)
valid_candidates = [c for c in candidates if c.is_valid]
invalid_candidates = [c for c in candidates if not c.is_valid]

for c in invalid_candidates:
    if c.is_phase2_output:
        # P3: a Master_-prefixed file carrying calculated/merged columns is
        # never a valid master, readable or not. Checked first so it is never
        # misreported as "no Study_Name column" below.
        st.warning(f"'{c.name}': " + config.MSG_PHASE2_OUTPUT)
    elif not c.readable:
        # Edge case 8b: surface candidate.error VERBATIM. A Master_-prefixed
        # file with duplicate columns is readable=False with the real reason
        # captured in .error (e.g. the exact duplicate-column detail) — a
        # hardcoded "unreadable" message here would hide that and send the
        # user hunting for a corrupt file instead.
        st.warning(
            f"'{c.name}' looks like a master file but could not be read: "
            f"{c.error} It will be treated as a study file instead."
        )
    else:
        # DESIGN DEFAULT — pending confirmation, see spec section 8, item 3
        # A Master_-prefixed file lacking Study_Name is warned about, excluded
        # from master candidacy, and falls through to be validated as an
        # ordinary study file (rather than rejected outright).
        st.warning(
            f"'{c.name}' looks like a master file but has no "
            f"{config.STUDY_NAME_COL} column. It will be treated as a study file instead."
        )

master: MasterContext | None = None
excluded_indices: set[int] = set()
excluded_outcomes: list[FileOutcome] = []


def _load_master(item: UploadedItem, *, first_file_name: str = "") -> MasterContext | None:
    """Shared halt-on-failure wrapper for both master-construction call sites.

    'The master-load failure is the ONLY place a failure halts' — the
    'without a master there is no schema to validate against' reasoning
    applies identically whether the master arrives via the resume path
    (build_master_context_from_existing) or is freshly designated on the
    first-master path (build_master_context_from_first_file), since both
    can raise FileReadError/SchemaError from the same read_table /
    build_column_index calls underneath. Both call sites therefore share
    this halt behaviour rather than the first-master path warning and
    letting the user pick again.
    """
    try:
        if first_file_name:
            return build_master_context_from_first_file(item, first_file_name)
        return build_master_context_from_existing(item)
    except (FileReadError, SchemaError) as e:
        st.error(f"Could not load the master file '{item.name}': {e}")
        st.stop()
        return None  # unreachable — st.stop() halts execution here


if len(valid_candidates) == 1:
    master = _load_master(items_by_index[valid_candidates[0].index])

elif len(valid_candidates) > 1:
    labels = [f"{c.name} (upload #{c.index + 1})" for c in valid_candidates]
    chosen_label = st.selectbox(
        "Two master files were found. Which one is the current master?",
        options=labels,
        index=None,
    )
    if chosen_label is not None:
        chosen = valid_candidates[labels.index(chosen_label)]
        master = _load_master(items_by_index[chosen.index])
        # Unselected valid candidates are excluded from study processing and
        # recorded as skipped / not selected as master (spec section 8 item 5).
        for c in valid_candidates:
            if c.index != chosen.index:
                excluded_indices.add(c.index)
                excluded_outcomes.append(
                    FileOutcome(
                        file=c.name,
                        index=c.index,
                        status=config.STATUS_SKIPPED,
                        reason=config.REASON_NOT_SELECTED_MASTER,  # DESIGN DEFAULT — pending confirmation, see spec section 8, item 5
                        missing_cols=[],
                        extra_cols=[],
                        study_name="",
                        rows=0,
                    )
                )
    else:
        st.info("Select which file is the current master to continue.")

elif first_master_slot_allowed(candidates):
    # STEP 2b — first-master slot, rendered ONLY when zero valid candidates
    # exist AND none of them is a Phase 2 output (P3, design default 7). A
    # Phase 2 output offered as the only candidate must not silently fall
    # through to "designate the first one" — Run stays disabled until a
    # proper master is supplied.
    st.subheader("No master found — designate the first one")
    first_labels = [f"{item.name} (upload #{item.index + 1})" for item in items]
    chosen_first_label = st.selectbox(
        "Which file do you want to use as the first Master?",
        options=first_labels,
        index=None,
    )
    typed_study_name = st.text_input("Study name for this master")

    # A typed name that is non-blank can still sanitize to "" (e.g. "...",
    # "   ...   " — dots and whitespace are not in config.ILLEGAL_FILENAME_CHARS
    # and are stripped entirely by sanitize_base_name's trailing
    # .rstrip(". ")). Left unguarded, that empty base_name would silently
    # flow into build_master_filename() and produce an unlabeled
    # "Master__<timestamp>.csv". This extends the existing first-master gate
    # rather than introducing a new halt: Run simply stays disabled and the
    # user is told why, exactly like the blank-name case already handled below.
    sanitized_preview = sanitize_base_name(typed_study_name) if typed_study_name.strip() else ""

    if chosen_first_label is not None and typed_study_name.strip() and sanitized_preview:
        chosen_item = items[first_labels.index(chosen_first_label)]
        master = _load_master(chosen_item, first_file_name=typed_study_name)
    elif chosen_first_label is not None and typed_study_name.strip() and not sanitized_preview:
        st.warning(
            f"The study name '{typed_study_name}' sanitizes to an empty string "
            "once illegal filename characters and trailing dots/spaces are "
            "removed. Type a study name that has at least one other character."
        )
    else:
        st.info("Choose a file and type a study name to create the first master.")

# Otherwise (P3): every candidate is a Phase 2 output and none is otherwise
# valid. STEP 2b is suppressed entirely; master stays None and Run stays
# disabled. No extra message — the agreed MSG_PHASE2_OUTPUT warning has
# already been shown for each such file in STEP 2 above.

# ---------------------------------------------------------------------------
# STEP 3 — master loaded caption
# ---------------------------------------------------------------------------
if master is not None:
    # Resume-path safety check: parse_master_base_name has no sanitize step of
    # its own, and a filename like "master_.csv" or "Master_.csv" parses to an
    # empty base_name (the prefix consumes the entire stem, leaving nothing
    # for MASTER_TIMESTAMP_SUFFIX_RE to match). Left unwarned, that flows
    # silently into build_master_filename() as an unlabeled
    # "Master__<timestamp>.csv" download. Warning only — this is not the
    # master-load-failure halt case, so Run stays available.
    if not master.created_this_run and not master.base_name.strip():
        st.warning(
            f"The master file '{master.source_file}' has no usable name once its "
            f"'{config.MASTER_FILENAME_PREFIX}' prefix and any timestamp suffix are "
            "removed — downloaded files will use a blank name (e.g. "
            "'Master__<timestamp>.csv'). Consider renaming the file before "
            "re-uploading it."
        )
    st.success(
        f"Master ready — source: {master.source_file or '(created this run)'} | "
        f"{len(master.frame)} rows | {len(master.columns)} columns | "
        f"base name carried forward: '{master.base_name}' | "
        f"{len(master.existing_study_names)} distinct existing study name(s)."
    )

# ---------------------------------------------------------------------------
# STEP 4 — study name review (rendered once a master schema exists)
# ---------------------------------------------------------------------------
study_items: list[UploadedItem] = []
study_names: dict[int, str] = {}

if master is not None:
    st.header("Study name review")
    study_items = [
        item for item in items
        if item.index not in excluded_indices and item.index != master.source_index
    ]

    if study_items:
        review_df = pd.DataFrame(
            {
                "File": [item.name for item in study_items],
                config.STUDY_NAME_COL: [item.stem for item in study_items],
            }
        )
        edited_df = st.data_editor(
            review_df,
            key="study_names",
            hide_index=True,
            disabled=["File"],
            num_rows="fixed",
            use_container_width=True,
        )
        study_names = {
            study_items[row].index: str(edited_df.loc[row, config.STUDY_NAME_COL])
            for row in range(len(edited_df))
        }

        # Warnings only — never a blocker (brief decision 11 / STEP 4).
        blank_files = [
            item.name for item in study_items
            if not study_names.get(item.index, "").strip()
        ]
        if blank_files:
            st.warning(
                f"These files have a blank study name and will be rejected: {', '.join(blank_files)}"
            )

        # DESIGN DEFAULT — pending confirmation, see spec section 8, item 6
        # Duplicate Study_Name detection is strip + casefold ("instacart_bounty"
        # collides with "Instacart_Bounty"); the values themselves are stored
        # verbatim in study_names / the master, never normalized in place.
        normalized_counts = Counter(
            name.strip().casefold() for name in study_names.values() if name.strip()
        )
        duplicate_keys = {key for key, count in normalized_counts.items() if count > 1}
        if duplicate_keys:
            dup_files = [
                item.name for item in study_items
                if study_names.get(item.index, "").strip().casefold() in duplicate_keys
            ]
            st.warning(
                "These files share the same study name (case/whitespace-insensitive) "
                f"within this batch: {', '.join(dup_files)}. Only the first in upload "
                "order will append; the rest will be skipped as duplicates."
            )
    elif master.created_this_run:
        st.info("No study files left to review — everything uploaded is the master.")
    else:
        # P4: an existing master with zero study files is a valid Run —
        # the master is used as-is and Phase 2 unlocks (edge case P2-1).
        st.info(config.MSG_MASTER_ONLY_RUN)

# ---------------------------------------------------------------------------
# STEP 5 — run
# ---------------------------------------------------------------------------
st.header("Run")

ready = is_run_ready(master, len(study_items))

if not ready:
    reasons: list[str] = []
    if master is None:
        reasons.append("a master must be selected or created")
    elif len(study_items) == 0:
        # P4: only the first-master path still requires a study file — an
        # existing master may run alone (is_run_ready already accounts for
        # this; this branch is therefore only reached on the first-master path).
        reasons.append("at least one study file must be available to append")
    st.info(f"Complete the following to enable Run: {', '.join(reasons)}.")

if st.button("Run", disabled=not ready, type="primary"):
    result = process_batch(
        items,
        master,
        study_names,
        excluded_indices=excluded_indices,
        excluded_outcomes=excluded_outcomes,
    )

    now = datetime.now()
    exception_frame = build_exception_report(result.outcomes)

    # Build BOTH byte payloads and BOTH filenames now, inside the Run block,
    # and stash them in session_state. A download_button click triggers a
    # Streamlit rerun; anything computed only inside `if st.button(...)`
    # would vanish on that rerun, so STEP 6 reads exclusively from
    # session_state, outside this block.
    st.session_state["result"] = result
    st.session_state["master_bytes"] = to_csv_bytes(result.master_df)
    st.session_state["exception_bytes"] = to_csv_bytes(exception_frame)
    st.session_state["master_filename"] = build_master_filename(master.base_name, now)
    st.session_state["exception_filename"] = build_exception_filename(master.base_name, now)

    # PHASE 2 — calculations and the template are pure functions of the just-
    # built master, so they are computed once here (same `now`) and stashed
    # in session_state exactly like the Phase 1 payloads above, surviving the
    # reruns triggered by downloads and by the Phase 2 uploader.
    calc = build_calculations(result.master_df)
    studies = list_template_studies(result.master_df)
    st.session_state["p2_calc"] = calc
    st.session_state["p2_base_name"] = master.base_name
    st.session_state["p2_template_bytes"] = build_template_bytes(studies)
    st.session_state["p2_template_filename"] = build_template_filename(master.base_name, now)
    st.session_state["p2_template_study_count"] = len(studies)

# ---------------------------------------------------------------------------
# STEP 6 — output, rendered from session_state, OUTSIDE the button block
# ---------------------------------------------------------------------------
result = st.session_state.get("result")

if result is not None:
    st.header("Results")

    # Q16: whenever any file is rejected, say so up front — the metric and
    # the table alone were too easy to miss.
    rejected_banner = rejected_files_message(result.outcomes)
    if rejected_banner:
        st.warning(rejected_banner)

    # P3: any study file rejected as Phase 2 output gets the clear message,
    # once, followed by the affected filenames — not a per-file warning.
    phase2_output_files = [
        o.file for o in result.outcomes if o.reason == config.REASON_PHASE2_OUTPUT
    ]
    if phase2_output_files:
        st.warning(config.MSG_PHASE2_OUTPUT)
        st.caption(", ".join(phase2_output_files))

    summary = summarize(result)
    metric_cols = st.columns(len(summary))
    for col, (label, value) in zip(metric_cols, summary.items()):
        col.metric(label, value)

    st.subheader("File-by-file outcome")
    st.dataframe(outcomes_to_frame(result.outcomes), use_container_width=True)

    st.subheader("Updated master (preview)")
    st.dataframe(result.master_df.head(20), use_container_width=True)
    st.caption(f"Showing 20 of {len(result.master_df)} total rows — download the file to see all.")

    st.download_button(
        label="Download updated master",
        data=st.session_state["master_bytes"],
        file_name=st.session_state["master_filename"],
        mime="text/csv",
    )
    st.download_button(
        label="Download exception report",
        data=st.session_state["exception_bytes"],
        file_name=st.session_state["exception_filename"],
        mime="text/csv",
    )

# ---------------------------------------------------------------------------
# PHASE 2 — STEPs 7-9, rendered only after a successful Run (guard mirrors
# STEP 6: read exclusively from session_state, outside the button block).
# ---------------------------------------------------------------------------
if result is not None and "p2_calc" in st.session_state:
    p2_calc = st.session_state["p2_calc"]
    p2_base_name = st.session_state["p2_base_name"]
    p2_template_bytes = st.session_state["p2_template_bytes"]
    p2_template_filename = st.session_state["p2_template_filename"]
    p2_template_study_count = st.session_state["p2_template_study_count"]

    st.header("Phase 2 · Study metadata & calculations")

    # -------------------------------------------------------------------
    # STEP 7 — download template
    # -------------------------------------------------------------------
    st.subheader("STEP 7 — Download template")
    st.info(config.MSG_TEMPLATE.format(n=p2_template_study_count))

    template_col, glossary_col = st.columns(2)
    with template_col:
        st.download_button(
            label="Download studyname_master",
            data=p2_template_bytes,
            file_name=p2_template_filename,
            mime=config.XLSX_MIME,
            key="dl_template",
        )
    with glossary_col:
        with st.expander("Glossary"):
            st.markdown(f"**{config.GLOSSARY_FIELDS_TITLE}**")
            fields_frame = pd.DataFrame(
                list(config.GLOSSARY_FIELD_ROWS),
                columns=list(config.GLOSSARY_FIELD_COLUMNS),
            )
            st.dataframe(fields_frame, hide_index=True, use_container_width=True)

            st.markdown(f"**{config.GLOSSARY_EXTRAS_TITLE}**")
            st.markdown(config.GLOSSARY_EXTRAS_TEXT)

            st.markdown(f"**{config.GLOSSARY_RULES_TITLE}**")
            for rule in config.GLOSSARY_RULES:
                st.markdown(f"- {rule}")

            st.markdown(config.GLOSSARY_CALC_BLOCK_NOTE)
            calc_frame = pd.DataFrame(
                list(config.GLOSSARY_CALC_ROWS),
                columns=list(config.GLOSSARY_CALC_COLUMNS),
            )
            st.dataframe(calc_frame, hide_index=True, use_container_width=True)

    # -------------------------------------------------------------------
    # STEP 8 — upload completed template
    # -------------------------------------------------------------------
    st.subheader("STEP 8 — Upload completed template (.xlsx or .csv)")
    p2_upload = st.file_uploader(
        "Drop the completed studyname_master file",
        type=["xlsx", "csv"],
        accept_multiple_files=False,
        key="p2_upload",
    )
    st.caption(config.MSG_UPLOAD_CSV_CAUTION)

    if p2_upload is None:
        st.caption(config.MSG_UPLOAD_PROMPT)
    else:
        parsed = parse_upload(p2_upload.name, p2_upload.getvalue(), list(result.master_df.columns))
        if not parsed.accepted:
            st.error(parsed.refusal_message)
        else:
            # ---------------------------------------------------------------
            # STEP 9 — final file. Rebuilt from scratch on EVERY rerun from
            # the current master (st.session_state["result"].master_df) and
            # the current upload — never cached (P29).
            # ---------------------------------------------------------------
            final = build_final(result.master_df, p2_calc, parsed)
            now9 = datetime.now()

            st.subheader("STEP 9 — Final file")
            st.info(config.MSG_COLUMN_MATCHING)

            if final.zero_match:
                st.warning(config.MSG_ZERO_MATCH.format(n=final.upload_study_count))

            if final.warnings:
                st.warning(summarize_phase2_warnings(final))
                with st.expander("Details"):
                    st.dataframe(
                        phase2_warnings_to_frame(final.warnings),
                        hide_index=True,
                        use_container_width=True,
                    )
            else:
                st.success(config.MSG_NO_ISSUES)

            st.dataframe(final.frame.head(20), use_container_width=True)
            st.caption(f"Showing 20 of {len(final.frame)} total rows — download the file to see all.")

            st.download_button(
                label="Download after_formulas_master",
                data=to_csv_bytes(final.frame),
                file_name=build_final_filename(p2_base_name, now9),
                mime=config.CSV_MIME,
                key="dl_final",
            )
            if final.warnings:
                st.download_button(
                    label="Download phase2_warnings",
                    data=to_csv_bytes(phase2_warnings_to_frame(final.warnings)),
                    file_name=build_phase2_warnings_filename(p2_base_name, now9),
                    mime=config.CSV_MIME,
                    key="dl_p2_warnings",
                )

st.markdown("---")
st.markdown(
    "<p style='text-align: right; color: gray; font-size: 0.85em;'>Developed by Marcos J. Lazzara</p>",
    unsafe_allow_html=True,
)
