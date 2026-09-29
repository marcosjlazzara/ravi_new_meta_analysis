# Meta Analysis Consolidation — Project Instructions

## READ THIS FIRST ON EVERY SESSION OPEN

When this project is opened, immediately greet Marcos and show him this status summary.
Do not wait for him to ask.

---

## Project Status (as of September 29, 2026)

> **Next session starts here:** Phase 1 + Phase 2 are **browser-verified, committed, merged into
> `master` and pushed** (2026-09-29). That includes the Q16 rejected-files banner, which was also
> browser-checked. What's open: send Ravi the Outstanding item 3 points, and the `devops` pass
> (packaging and deployment), which hasn't started.

### Phase 1 — consolidation: BUILT
- **Requirements:** confirmed — `META_BRIEF.md` (19 locked decisions, settled in a full requirements interview)
- **Design:** complete — `ARCHITECTURE.md` (module map, data contracts, 17 edge cases, precision contract)
- **Code: BUILD COMPLETE** — all 5 build stages implemented, each QC-approved by `qc-reviewer`
- **Output naming (Sep 8):** downloaded masters are `Master_File_<name>_<timestamp>.csv`;
  detection still keys on `master_`, so old `Master_*` files are still found
- **Changed by Phase 2 (now on `master`):** Run now works with an existing master and zero
  studies (P4); files carrying Phase 2 calculated/merged columns are rejected as studies and
  refused as masters (P3). `ARCHITECTURE.md` edge case 14 is superseded by P4. Recorded in `ARCHITECTURE.md`
  section 10 "Phase 2 amendments" (2026-09-29), per `PHASE2_ARCHITECTURE.md` section 12.
- **Browser-verified 2026-09-29** by Marcos, on the `phase2` code (Outstanding item 1)

### Phase 2 — study metadata & calculations: BUILT, QC-APPROVED, BROWSER-VERIFIED (2026-09-29)
- Called "Phase 3" in `Meta Analysis_NewV1.docx` and the meeting notes; "Phase 2" in this project
- **Requirements:** `PHASE2_BRIEF.md` — 33 locked decisions (2026-09-28) + rulings in section 11b
  and section 8 (option B tolerance, 2026-09-28)
- **Design:** `PHASE2_ARCHITECTURE.md` — approved by Marcos; all 7 concerns (C1–C7) accepted as
  recommended; 20 design defaults in section 11, each marked in code with
  `# DESIGN DEFAULT — pending confirmation, see PHASE2_ARCHITECTURE.md section 11, item N`
- **Code:** all 5 build stages implemented, **each QC-approved** (2026-09-28/29)
- **Tests: 561/561 passing, 0 skipped**, exit 0 (2026-09-29; 556 + 5 for the Q16 banner). Every run must print
  `LAYER 2 RAN — 212 rows, 7 columns, 318 non-blank cells compared, worst relative error 1.1E-14, tolerance 1E-13`
  (comparison of every calculated cell against Ravi's workbook). If that line is missing or
  says SKIPPED, the workbook was not found/readable — that is **not** a pass.
- **Git:** Phase 2 was committed on `phase2` (2026-09-29) and fast-forward merged into `master`.
  `master` = `origin/master` = Phase 1 + Phase 2 at
  `https://github.com/MarcosCircana/new_meta_lift_analysis_ravi` (private). The `phase2` branch
  itself was not pushed. Marcos commits and pushes only when he says so.
  - still deliberately left out of git: `Meta Analysis_NewV1.docx` (modified, predates the build),
    `Meta Analysis_NewV1_STATUS.md`, `Phase 3 Summary.docx` (untracked)
  `.gitignore` blocks all client data (`*.csv`, `*.xlsx`, `Samples/`, `test_fixtures/`);
  no data file has ever been committed.

### Lessons from the Phase 2 build (worth keeping)
- **A test that tries several variants per cell can accept anything.** Stage 3's first layer-2
  comparison accepted a cell if any of several Excel-rounding re-derivations matched — but never
  compared against the app's own output. QC proved it accepted a deliberately wrong formula and
  even a nonsense constant on all affected cells. Replaced by one fixed tolerance (option B).
  Always mutation-test a numeric comparison: break the code on purpose and confirm the test fails.
- **Excel is not an exact reference.** Its arithmetic rounds at the 15th digit, and it coerces
  text-stored numbers its own way; a literal 15-digit match with an exact-decimal app is not
  achievable. Ravi's workbook inputs are also Excel-rounded (`0.036091684` vs source
  `0.03609168443151368`), so app figures built from full-precision masters will differ from his
  manual ones from ~the 8th digit — the app's are the more accurate (flagged in `PHASE2_BRIEF` section 11 item 6).
- **The rule-4 scan bans the bare string `"Model"` anywhere outside `config.py`** — it is a
  reference column name. Use config constants, even for UI labels.
- **openpyxl 3.1.5 raises `IllegalCharacterError`** on XML-illegal characters rather than
  stripping them; `template_builder.py` strips them first.

### Documents

| File | Role |
|------|------|
| `CLAUDE.md` | This file — live status, rules, what's outstanding |
| `META_BRIEF.md` | Authority on **what** was agreed for Phase 1: 19 locked decisions, 4 deviations |
| `PHASE2_BRIEF.md` | Authority on **what** was agreed for Phase 2: 33 locked decisions, formulas, messages, glossary draft |
| `PHASE2_ARCHITECTURE.md` | Authority on **how** for Phase 2: modules, contracts, 34 edge cases, test plan, 20 design defaults, C1–C7 rulings |
| `Phase 2 process/master_file_w_calculations.xlsx` | Ravi's reference workbook — formulas + cached results for the Phase 2 calculations. Client data, gitignored. |
| `Phase 3 Summary.docx` | Meeting notes (Ravi + Marcos) that scoped Phase 2 |
| `ARCHITECTURE.md` | Authority on **how** for Phase 1: module map, contracts, 17 edge cases, precision contract |
| `QUESTIONS_FOR_RAVI.md` | 24 questions for the requester. All that affect built code, plus Q20–Q24, were answered by Marcos on 2026-09-29. Still for Ravi: the 4 deviations, the 8th-digit heads-up and the later-phase questions |
| `HANDOFF.md` | Inherited lessons from the predecessor project (read once; not maintained — this project's lessons live in this file) |
| `Meta Analysis_NewV1.docx` | The original source requirement |

---

## What this is

A Streamlit web app that consolidates Lift study score files into one Meta Analysis master
dataset. It replaces manual step 2 of the Meta Analysis workflow ("append all studies"),
currently 3–4 days of work.

**Phase 2** (built on branch `phase2`, merged into `master` 2026-09-29) extends the same app, after Run: it offers a blank
`studyname_master_*.xlsx` template (one row per study, column A locked, glossary on sheet 2),
takes the completed template back, and produces `after_formulas_master_*.csv` = the master +
8 calculated columns (Ravi's formulas, exact decimal arithmetic) + the user's study metadata
repeated on every row of each study, with a warnings panel/CSV. Reporting, charts and
bucketing remain out of scope.

Predecessor: `../new_pg_antara_6_24` — patterns reused (Streamlit, flat modules, stateless,
validation-warns-never-blocks), mapping logic not. This tool has **no column mapping**; the
master defines the schema at runtime.

---

## How to run

```
cd "C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\code"
git branch --show-current        # master has Phase 1 + Phase 2
python -m streamlit run app.py
```

Open `http://localhost:8501`. Stop with Ctrl+C.

First time only:
```
pip install -r requirements.txt
```

Run the QC suite:
```
python test_meta_pipeline.py
```

---

## Code structure — flat, in `code/`

| File | Responsibility |
|------|----------------|
| `app.py` | Streamlit orchestrator, STEPs 0–9 — **the only file that imports streamlit** |
| `config.py` | All constants, messages, glossary text. The **only** file allowed column-name literals (rule 4). |
| `models.py` | Dataclasses: `UploadedItem`, `MasterCandidate`, `MasterContext`, `FileOutcome`, `BatchResult`; Phase 2: `Phase2Warning`, `CalculationResult`, `UploadRow`, `ParsedUpload`, `FinalResult` |
| `file_reader.py` | bytes → all-string DataFrame (`.csv` / `.xlsx` sheet 1); `read_raw_grid` header-less read (Phase 2) |
| `schema.py` | Column normalize / compare / reorder / tag; Phase 2 header normalize + output detection |
| `master_detector.py` | Finds and validates the master; builds `MasterContext`; refuses Phase 2 outputs |
| `study_processor.py` | Per-file pipeline (fixed checks incl. step 3b) + batch loop; `is_run_ready` |
| `report.py` | Exception report + on-screen summary + rejected-files banner (Q16); Phase 2 warnings frame/summary |
| `csv_writer.py` | Timestamped filenames (master, exception, template, final, warnings) + UTF-8-BOM bytes |
| `numeric.py` | Phase 2 — exact `Decimal` parse / multiply / format; the only module touching `decimal` |
| `calculations.py` | Phase 2 — master → 8 calculated columns + warnings (block matching by key) |
| `template_builder.py` | Phase 2 — study list → `studyname_master` .xlsx bytes; the only app module importing openpyxl |
| `metadata_upload.py` | Phase 2 — completed template → `ParsedUpload` (refusals, header rules) |
| `final_builder.py` | Phase 2 — master + calculations + upload → `after_formulas_master` frame + warnings |
| `test_meta_pipeline.py` | QC harness, 561 checks: Phase 1 sections 1–9, rule scans (10), Phase 2 stages (11–14) |

---

## Rules that must not be broken

These were each enforced through five QC reviews. Breaking one is a regression.

1. **Only `app.py` may import `streamlit`.** This is what makes the whole pipeline testable
   headlessly — every claim in the QC reviews was verifiable because of it.
2. **`dtype=str` everywhere; no numeric coercion, ever.** Banned anywhere in `code/`:
   `astype(float)`, `pd.to_numeric`, `.round()`, `np.float64`, `float_format=`, `converters=`,
   `parse_dates=`, `thousands=`, `decimal=`, and `read_csv`/`read_excel` without `dtype=str`.
   Values pass through byte-exact — a 17-digit decimal must survive the full pipeline
   character-for-character.
   *Phase 2 amendment:* the calculated columns are computed with `decimal.Decimal` on parsed
   copies — never float. Source values are never altered and are still written byte-exact.
3. **No filesystem writes anywhere.** This is a hosted app with no disk access. There is no
   output folder. Output is `st.download_button` only.
4. **Column names appear as literals only in `config.py`.** *(Amended for Phase 2 — was "no
   column name other than `config.STUDY_NAME_COL`".)* Phase 2's calculations must name their
   source columns (`dependent_variable`, `CNT_EXPSD_HH`, `ADJ_MEAN_EXPSD_GRP`, `MODEL_DESC`,
   `Model`), and they are matched by name, never by column letter. Every other module refers to
   them through `config`. The 31-name reference list still belongs solely in
   `test_meta_pipeline.py`.
5. **The schema is never hardcoded.** It comes from the master at runtime.
6. **Validation never halts the run.** The single exception is a master that cannot be loaded —
   without it there is no schema to validate against (this includes a Phase 2 output offered as
   the master, P3). *Phase 2 adds one parallel exception:* a studyname upload with no
   `Study_Name` column, or that is itself a master, is refused (P11) — nothing to match on.
   Phase 1 results stay on screen. Everything else in Phase 2 warns, never blocks.
7. **These rules are now enforced automatically** by the AST scans in `test_meta_pipeline.py`
   section 10 (rule 2 banned constructs, rule 3 no writes, rule 4 column literals, openpyxl
   import location). Before Phase 2 they were enforced by review only.

---

## Outstanding — in priority order

### 1. Browser verification of `app.py`, Phase 1 + Phase 2 — DONE 2026-09-29

Marcos clicked through every item below on the `phase2` code; nothing broke.

Streamlit's test harness cannot drive `st.file_uploader`, so this manual pass is the only
coverage STEPs 2–9 have beyond QC tracing. Re-run it after any change to `app.py`, using files
from `Samples/`, not the whole folder (see trap 1 below).

**Phase 1**
- [x] **Download-rerun path.** Upload the 10 study files + `Master_Instacart_2026-09-07_1200.csv`
      + a renamed copy of it (e.g. `Master_Test_2026-09-29_0900.csv`). Pick one, Run
      (expect 9 appended / 1 skipped / 732 rows), click *Download updated master*. Results table
      and both downloads must still be there afterwards. Highest-risk path.
- [x] **Study-name editor.** Blank one name and duplicate another: both warn, Run still works.
- [x] **First-master slot (STEP 2b).** Only study files; type `...` as the study name → refused,
      Run stays disabled; then a real name → runs.
- [x] **A real `.xlsx` study upload** (save a sample CSV as .xlsx) — appends like the CSV.
- [x] **Master-only Run (new, P4).** Upload only the master → Run enabled, "No study files
      uploaded…" message, 0 appended.

**Phase 2** (after any Run)
- [x] **Template in Excel.** Download `studyname_master`: column A refuses edits; B–G and H1
      editable; `25%` in D2 shows 25.00%; sheet 2 = glossary; unprotects with no password.
- [x] **Fill and upload.** Fill some rows, add an extra column at H, put `$3.49` in one cell,
      upload the `.xlsx` → one warning; final file downloads with `0.25` in `Pct_HH_Buying`.
- [x] **Everything survives clicks.** After the upload, click all 5 download buttons — Phase 1
      results, template and final file all stay on screen.
- [x] **Run again** with the template still uploaded → final file rebuilds without re-uploading.
- [x] **Refusals.** In the STEP 8 slot: a study file (no `Study_Name`) and the master itself are
      refused. As a Phase 1 study: the downloaded `after_formulas_master` gets the
      "calculated columns" warning.


### 2. Questions affecting built code — ANSWERED 2026-09-29 (Marcos)

Recorded under each question in `QUESTIONS_FOR_RAVI.md`.
- **Q5:** column names do not change between clients. Strict matching stays and there is **no alias map**. Q3 is closed with it.
- **Q15:** the schema stays locked, now by choice. A file with an unexpected column is rejected on
  its own, the rest of the batch appends, and the user is warned (option a). Halting the whole batch was declined.
- **Q16:** keep "fix the source and re-run", but **always warn when a file fails**. Built 2026-09-29:
  a Results banner lists every rejected file with its reason (`report.rejected_files_message`,
  `config.MSG_FILES_REJECTED_ONE`/`_MANY`, 5 new checks in test section 8). **Browser-checked
  2026-09-29** (run with `test_fixtures/reject_*` files in the batch).
- **Q6:** divergent copies are not reconciled. Accepted.
- **Q11:** only `.csv` and `.xlsx`. Accepted.
- **Q20–Q24 (Phase 2):** all defaults agreed. Q22: both header clean-ups, including the "Partner Member" rename.
  Q23: glossary now says "Whole number (e.g. 45)." with no unit and no extra check.

### 3. Still for Ravi

- **Sign-off on four deviations from the doc** (`META_BRIEF.md` section 7, also at the end of
  `QUESTIONS_FOR_RAVI.md`). All four follow from the hosted-web-app decision: no output folder, no
  true folder picker, `MODEL_DESC` standardization stays manual, and the schema is read at runtime rather than stored.
- **Heads-up:** app figures will differ from his manual workbook from about the 8th digit
  (`PHASE2_BRIEF.md` section 11 item 6).
- **Later-phase questions** (Q2 target date, Q7–Q10, Q12, Q13, Q17–Q19) are not urgent.

### 4. Open design defaults

- **Phase 1:** `ARCHITECTURE.md` section 8 items 1, 2, 3, 5, 6, 7, 8 are implemented per their
  stated default but not confirmed with the requester. Each is marked in code with
  `# DESIGN DEFAULT — pending confirmation, see spec section 8, item N`. Items 4 and 9 are
  resolved. Item 10 is a note, not a decision.
- **Phase 2:** `PHASE2_ARCHITECTURE.md` section 11, items 1–20, same convention.

### 5. After the browser check passes (it has — 2026-09-29)

- ~~Amend `ARCHITECTURE.md` with a "Phase 2 amendments" section~~ — done 2026-09-29 (section 10).
- ~~Commit `phase2`, merge to `master`, push~~ — done 2026-09-29.
- `devops` pass (packaging/deployment) — not started for either phase.

---

## Test data

- `Samples/` — 10 real study files (31 cols) + `MaserFile_XXXX_DATE.csv` and
  `Master_Instacart_2026-09-07_1200.csv` (32 cols, byte-identical to each other).
- `test_fixtures/` — 8 fabricated edge cases; filenames state expected behaviour
  (`reject_*`, `pass_*`, `edge_*`).

**Two traps worth knowing:**

1. **`MaserFile_XXXX_DATE.csv` is not detected as a master** — `maserfile_` is not `master_`.
   That is correct per decision 15. It means dropping the whole `Samples/` folder in takes the
   *first-master* path, and `MaserFile_XXXX_DATE.csv` falls through as a study file where it
   matches the schema perfectly and appends, duplicating Holly_Rancher's 52 rows under a second
   name. Correct-by-spec, surprising in a demo. For a clean demo use the 10 study files plus
   **one** master.
2. **Holly_Rancher is skipped on a normal run.** The master was built from that study, so
   appending the 10 study files gives 9 appended / 1 skipped / 732 rows. That is decision 12
   working, not a bug.

---

## Agent workflow

1. `architect` — structural decisions only, before any code
2. `python-developer` — all code changes, one phase at a time
3. `qc-reviewer` — after **every** phase, not just at the end
4. `devops` — packaging and deployment (not yet started)

QC reviews on this project have been genuinely load-bearing — they caught a stale spec claim,
two tests that looked like order tests but weren't, an untested parameter pair, and a real
defect where a study name of `...` silently produced an unlabeled master. Do not treat the
review step as a formality.

## Golden Rule

Never assume. Always ask when anything is unclear. Match complexity to the task — no more,
no less.
