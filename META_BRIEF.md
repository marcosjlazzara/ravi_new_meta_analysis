# Meta Analysis Consolidation — Confirmed Brief

**Status:** scope confirmed 2026-09-07. **Built and QC-approved the same day — 236/236 tests
passing, app confirmed to launch.** See `CLAUDE.md` for live status and what remains outstanding,
and `ARCHITECTURE.md` for the design. This document stays the authority on WHAT was agreed.
**Source requirement:** `Meta Analysis_NewV1.docx`, Phase 1 section + Marcos's inline `//` annotations.
**Predecessor:** `../new_pg_antara_6_24` — patterns reused, mapping logic not.

---

## 1. What this is

A Streamlit web app, hosted internally at Circana, that consolidates Lift study score files
into a single Meta Analysis master dataset. It replaces manual step 2 of the Meta Analysis
workflow ("append all studies"), which currently takes 3–4 days.

### Relationship to the Antara tool

Antara maps a *known* Unify schema into a *fixed* 22-column P&G master via `mapping_config.py`.
This tool has **no column mapping at all** — incoming files already share the master's column
names, and the work is validation, ordering, tagging and appending.

Reused from Antara: Streamlit, flat module layout in `code/`, stateless design,
validation-warns-never-blocks, UTF-8-BOM CSV output, `architect → python-developer →
qc-reviewer → devops` workflow.

Not reused: `mapping_config.py`, `COLUMN_MAP`, `cleaner.py`, `tactic_*`, `metadata_form.py`.

---

## 2. Confirmed Scope (non-negotiable)

| # | Decision | Answer |
|---|----------|--------|
| 1 | Phases in scope | **Phase 1 only.** Phases 2–4 scoped separately later. |
| 2 | Deployment | **Streamlit web app, hosted on Circana-controlled infrastructure.** Not local. |
| 3 | Data boundary | Client read-result data must **never** reach non-Circana infrastructure. Rules out Streamlit Community Cloud and equivalents. |
| 4 | Persistence | **None.** Fully stateless — nothing stored server-side between sessions. |
| 5 | Input | **One drop zone.** User drops the whole batch: study files plus the master. |
| 6 | Accepted types | `.csv` and `.xlsx`. Excel reads **sheet 1**. Every csv/xlsx is attempted; unrelated spreadsheets appear as rejections and that is accepted noise. |
| 7 | Structure authority | **The master file.** Its column list and column order are the rule. |
| 8 | Match rule | Column **names** must match; incoming order does not matter. Case- and whitespace-insensitive. |
| 9 | Reordering | Incoming columns are **reordered into the master's order** before appending. |
| 10 | Rejects | Missing or extra columns → file skipped, logged, **run continues**. Never halts. |
| 11 | `Study_Name` | **Last column.** Value = source filename minus extension, verbatim. Shown and **editable** before append. |
| 12 | Duplicates | A study whose `Study_Name` is already in the master is **skipped automatically** and reported. Re-running the same batch appends nothing. |
| 13 | `MODEL_DESC` | Appended **exactly as-is**. No standardization, no derived columns. Master stays at 32 columns. |
| 14 | Numeric values | **Full precision preserved.** No Excel-style rounding. |
| 15 | Output name | `Master_<Name>_<YYYY-MM-DD_HHMM>.csv`, UTF-8-BOM. Prefix `Master_` matched case-insensitively. |
| 16 | Write model | Every run produces a **new** download. Nothing is overwritten. |
| 17 | Resume | Name carried forward from the uploaded master's filename; date restamped. |
| 18 | Reporting | Summary **on screen**; master and exception report via **download buttons**. Nothing auto-written to disk. |
| 19 | Zero-data-row file | Valid headers, no rows → **skipped**, reason `no data rows`. Not a rejection — the structure is fine. Does not reserve its `Study_Name`, so a real version later in the batch can still append. |

---

## 3. Flow

1. **Input section** — user drops the whole batch (study files + master, if they have one).
2. **App scans for a `Master_*` file** and verifies it has a `Study_Name` column.
   Two candidates → app asks which one.
3. **Master found** → its structure is the rule; the rest are appended into it.
4. **No master found** → a second slot appears: *"Which file do you want to use as the first
   Master?"* The user places that file there. It becomes the master — `Study_Name` added, its
   own rows included as the master's first rows — and its structure becomes the rule.
   **It is not appended a second time.**
5. **Study name** typed by the user when a master is being created
   (e.g. `Instacart` → `Master_Instacart_2026-09-07_1430.csv`).
6. **Run** → on-screen summary; master + exception report offered as downloads.

---

## 4. Reference schema (from `Samples/`)

All 10 sample study files share **byte-identical 31-column headers**. The provided master adds
`Study_Name` as column 32.

```
MODEL_DESC, Model, TIME_AGG_PERIOD, START_WEEK, END_WEEK, dependent_variable,
CNT_EXPSD_HH, UDJ_AVG_EXPSD_HH_PRE, UDJ_AVG_CNTRL_HH_PRE, UDJ_AVG_EXPSD_HH_PST,
UDJ_AVG_CNTRL_HH_PST, UDJ_DOD_EFFCT, UDJ_DIFF_EFFCT, ADJ_MEAN_EXPSD_GRP,
ADJ_MEAN_CNTRL_GRP, ADJ_DOD_EFFCT, TWOTAIL_PVAL, ONETAIL_PVAL, ABS_DIFF, DOL_DIFF,
ONETAIL_80_PCT_INTRVL_UB, ONETAIL_80_PCT_INTRVL_LB, ONETAIL_90_PCT_INTRVL_UB,
ONETAIL_90_PCT_INTRVL_LB, TWOTAIL_80_PCT_INTRVL_UB, TWOTAIL_80_PCT_INTRVL_LB,
TWOTAIL_90_PCT_INTRVL_UB, TWOTAIL_90_PCT_INTRVL_LB, CNT_IMPRESSIONS, CNT_Model_HH,
Channels [, Study_Name]
```

The schema is **not hardcoded** — it is read from the master at runtime. The list above is
reference only, for tests and sanity checks.

### Facts established from the sample data

- `Samples/MaserFile_XXXX_DATE.csv` is Holly_Rancher already appended: 52 rows, 32 columns.
  It is a **worked example, not a blank template**. Note the filename typo (`Maser`) — the app
  uses `Master_`.
- `Study_Name` in that file = `Holly_Rancher 27382_Scored` — filename stem, extension dropped,
  spaces / job number / `_Scored` suffix all preserved verbatim.
- Its numeric values are **rounded** vs the source (`0.035810509` vs `0.03581050949715417`) —
  an Excel round-trip artifact. The tool must not reproduce this.
- Study files run 52–96 data rows each. A 100-study master lands near 8,000 rows — scale is a
  non-issue.
- `MODEL_DESC` varies heavily across studies: `freq(1)`, `freq(2)`, `freq(2+)`, `freq(2-3)`,
  `freq(3+)`, `freq(4+)`, `freq(5-6)`, `freq(7+)`, `freq(static_1_)`…`freq(static_10+_)`;
  `publisher(Instacart)` vs `publisher(Liveramp)`; `audience_crt(Group3…Group60)`.
  This is real and **intentionally left untouched** — see decision 13.

---

## 5. Exception report and summary

Exception report — one row per file that was not appended:

| Column | Contents |
|---|---|
| `file` | Source filename |
| `status` | `rejected` / `skipped` |
| `reason` | e.g. `column mismatch`, `already in master`, `unreadable` |
| `missing_cols` | Columns the master has that the file lacks |
| `extra_cols` | Columns the file has that the master lacks |

Processing summary — shown on screen:

- Total files processed
- Files successfully appended
- Files skipped (already in master)
- Files rejected
- Total records consolidated

---

## 6. Out of scope

Per the doc:

- Automatic download of source study files (Phase 2)
- Additional metric generation / benchmarking (Phase 3)
- Chart creation, storytelling, PowerPoint (Phase 4)
- Centralized storage and management of Meta Analysis projects

---

## 7. Deviations from the doc — SIGNED OFF by Marcos, 2026-09-29

| Doc says | Reality | Why |
|---|---|---|
| "Output Folder" as a user input | Master is **downloaded**, not written to a path | A hosted app cannot see a user's drive |
| "Bulk folder processing", "select a folder" | **Select-all-files** (Ctrl+A in the file dialog) | Browsers do not hand folder paths to servers — a security boundary, not a Streamlit limitation |
| "Standardize break names/Model_Desc" (manual step 2) | **Stays manual** | Reconciling `freq(2+)` against `freq(2)`+`freq(3)` is an analytical judgment, not a rename; belongs with Phase 4 bucketing |
| "Store the file structure as the reference schema" | Structure read from the **master at runtime** | Equivalent outcome, no stored state |

---

## 8. Known limitations accepted for v1

- **Rescored studies cannot be refreshed.** A rescore keeps the same filename, so it will be
  skipped as a duplicate forever. No override in v1.
- **Unrelated spreadsheets produce rejections.** Accepting `.xlsx` means any Excel file in the
  batch is read and validated; non-study files land in the exception report as noise.
- **No true folder picker.** See section 7.

---

## 9. Outstanding

- [x] **A study file that should fail validation.** None of the 10 samples exercises the
      rejection path, so fabricated fixtures now live in `test_fixtures/` (kept out of
      `Samples/` so they can never be picked up by a real run). Derived from
      `Instacart_Bounty_scored.csv`, 5 data rows each:

      | Fixture | Expected |
      |---|---|
      | `reject_missing_column_scored.csv` | rejected — `ABS_DIFF` missing |
      | `reject_extra_column_scored.csv` | rejected — extra `RETAILER_ID` |
      | `reject_missing_and_extra_scored.csv` | rejected — both, report must list each separately |
      | `reject_unrelated_notes.csv` | rejected — unrelated spreadsheet (the section 8 noise case) |
      | `reject_empty_file_scored.csv` | rejected — zero bytes, must not raise |
      | `pass_reordered_columns_scored.csv` | **appended** — columns fully reversed, must be reordered to master order |
      | `pass_messy_header_case_scored.csv` | **appended** — alternating upper/lower case, padded whitespace |
      | `edge_headers_only_scored.csv` | **skipped** — `no data rows` (decision 19) |

      A real-world failing file is still preferable and welcome.

- [x] **Zero-data-row file** — settled as decision 19 below.
- [x] **Sign-off** on the four deviations in section 7 — given by Marcos, 2026-09-29.
