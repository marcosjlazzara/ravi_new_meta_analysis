# Meta Analysis Consolidation — Project Instructions

## READ THIS FIRST ON EVERY SESSION OPEN

When this project is opened, immediately greet Marcos and show him this status summary.
Do not wait for him to ask.

---

## Project Status (as of September 28, 2026)

### Phase 1 — consolidation: BUILT
- **Requirements:** confirmed — `META_BRIEF.md` (19 locked decisions, settled in a full requirements interview)
- **Design:** complete — `ARCHITECTURE.md` (module map, data contracts, 17 edge cases, precision contract)
- **Code: BUILD COMPLETE** — all 5 build stages implemented, each QC-approved by `qc-reviewer`
- **Tests: 237/237 passing**, exit 0 (236 + a round-trip check for the `Master_File_` prefix, Sep 8)
- **Output naming (Sep 8):** downloaded masters are `Master_File_<name>_<timestamp>.csv`;
  detection still keys on `master_`, so old `Master_*` files are still found
- **App:** confirmed to launch (`http://localhost:8501`, HTTP 200)
- **Git:** `master` = `origin/master` at
  `https://github.com/MarcosCircana/new_meta_lift_analysis_ravi` (private).
  `.gitignore` blocks all client data; no data file has ever been committed.
  Unstaged and deliberately left alone: `Meta Analysis_NewV1.docx` (modified, predates the build),
  `Meta Analysis_NewV1_STATUS.md` and `Phase 3 Summary.docx` (untracked).
- **Still outstanding:** interactive verification of `app.py` by a human (checklist below)

### Phase 2 — study metadata & calculations: SCOPED, NOT BUILT
- **Branch:** `phase2` — `master` stays the signed-off Phase 1 until Phase 2 passes QC
- **Requirements:** confirmed 2026-09-28 — `PHASE2_BRIEF.md` (33 locked decisions)
- **Stage 0 (docs):** brief written, Ravi questions added (Q20–Q24), rules 2 and 4 amended below
- **Next step:** `architect` design for Phase 2, reviewed by Marcos before any code
- Called "Phase 3" in `Meta Analysis_NewV1.docx` and the meeting notes; "Phase 2" in this project

### Documents

| File | Role |
|------|------|
| `CLAUDE.md` | This file — live status, rules, what's outstanding |
| `META_BRIEF.md` | Authority on **what** was agreed for Phase 1: 19 locked decisions, 4 deviations |
| `PHASE2_BRIEF.md` | Authority on **what** was agreed for Phase 2: 33 locked decisions, formulas, messages, glossary draft |
| `Phase 2 process/master_file_w_calculations.xlsx` | Ravi's reference workbook — formulas + cached results for the Phase 2 calculations. Client data, gitignored. |
| `Phase 3 Summary.docx` | Meeting notes (Ravi + Marcos) that scoped Phase 2 |
| `ARCHITECTURE.md` | Authority on **how**: module map, contracts, 17 edge cases, precision contract |
| `QUESTIONS_FOR_RAVI.md` | 24 questions for the requester: Q1–Q19 annotated against the Phase 1 build (**3 still open and affect existing code**), Q20–Q24 open Phase 2 points |
| `HANDOFF.md` | Inherited lessons from the predecessor project |
| `Meta Analysis_NewV1.docx` | The original source requirement |

---

## What this is

A Streamlit web app that consolidates Lift study score files into one Meta Analysis master
dataset. It replaces manual step 2 of the Meta Analysis workflow ("append all studies"),
currently 3–4 days of work. Phase 1 of a 4-phase roadmap in `Meta Analysis_NewV1.docx`;
phases 2–4 are explicitly out of scope.

Predecessor: `../new_pg_antara_6_24` — patterns reused (Streamlit, flat modules, stateless,
validation-warns-never-blocks), mapping logic not. This tool has **no column mapping**; the
master defines the schema at runtime.

---

## How to run

```
cd "C:\Users\MLazza01\OneDrive - IRI\Documents\AI Innitative\RAVI_new_p&G\code"
python -m streamlit run app.py
```

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
| `app.py` | Streamlit orchestrator — **the only file that imports streamlit** |
| `config.py` | All constants. Contains NO data column names. |
| `models.py` | Dataclasses: `UploadedItem`, `MasterCandidate`, `MasterContext`, `FileOutcome`, `BatchResult` |
| `file_reader.py` | bytes → all-string DataFrame (`.csv` / `.xlsx` sheet 1) |
| `schema.py` | Column normalize / compare / reorder / tag |
| `master_detector.py` | Finds and validates the master; builds `MasterContext` |
| `study_processor.py` | Per-file pipeline (7 fixed checks) + batch loop |
| `report.py` | Exception report + on-screen summary |
| `csv_writer.py` | Timestamped filenames + UTF-8-BOM bytes |
| `test_meta_pipeline.py` | QC harness, 9 sections, 236 checks |

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
   without it there is no schema to validate against.

---

## Outstanding — in priority order

### 1. Interactive verification of `app.py` (NOT YET DONE)

Streamlit's test harness cannot drive `st.file_uploader`, so STEP 2–6 of `app.py` have been
traced against the spec but **never executed**. A human must confirm:

- [ ] **The download-rerun path.** Upload a batch with 2+ valid `Master_*` files, pick one,
      Run, then click *Download updated master*. The results table and both downloads must
      still be populated afterwards. This is the highest-risk untested path — a download click
      reruns the whole script.
- [ ] **Study-name editor.** Introduce a blank name and a duplicate; both must warn, neither
      may block Run.
- [ ] **First-master slot (STEP 2b)** end-to-end, including typing `...` as the study name —
      must refuse and keep Run disabled.
- [ ] **A real `.xlsx` upload.** All samples are CSV; Excel sheet-1 reading has never been
      exercised through the UI.

### 2. Three questions for Ravi that affect code ALREADY BUILT

Full detail in `QUESTIONS_FOR_RAVI.md` (annotated). These are not future-phase questions —
each one changes existing behaviour:

- **Q5 — is an alias map needed?** Built with strict column-name matching, tolerant of case
  and whitespace only. **No alias map.** That was right on the evidence: all 10 samples have
  byte-identical 31-column headers. But they are one client and one scoring engine, and the
  question itself notes the Antara tool needed aliases *because real naming differences
  appeared*. **If naming varies across clients, every file from a differing client rejects
  and the tool looks broken.** Highest-risk open item on the project.
- **Q15 — is the schema locked for a project's life?** As built, effectively yes: the master
  defines the columns and any extra column rejects. A legitimately new column mid-study fails
  every subsequent file. Nobody chose this — it fell out of decisions 7 and 10.
- **Q16 — what happens after a file fails?** As built: fix the source and re-run (safe and
  cheap, since duplicates skip). There is no in-tool remap. A defensible v1 choice, but a
  choice. Overlaps Q5 — answering Q5 "yes, aliases" removes much of the need.

### 3. Requester sign-off on four deviations from the doc

See `META_BRIEF.md` section 7, also summarised at the end of `QUESTIONS_FOR_RAVI.md`. All four
follow from the hosted-web-app decision: no output folder, no true folder picker,
`MODEL_DESC` standardization stays manual, schema read at runtime rather than stored.

Same conversation as item 2 — send them together, along with the five Phase 2 questions
(Q20–Q24 in `QUESTIONS_FOR_RAVI.md`).

### 4. Open design defaults

`ARCHITECTURE.md` section 8 items 1, 2, 3, 5, 6, 7, 8 are implemented per their stated default
but not confirmed with the requester. Each is marked in code with
`# DESIGN DEFAULT — pending confirmation, see spec section 8, item N`. Items 4 and 9 are
resolved. Item 10 is a note, not a decision.

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
