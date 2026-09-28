# Meta Analysis — Phase 2 Confirmed Brief (Study metadata & calculations)

**Status:** scope confirmed 2026-09-28 in a full requirements interview. **Not yet designed or built.**
Branch: `phase2`. See `CLAUDE.md` for live status.
This document is the authority on **WHAT** was agreed for Phase 2. `META_BRIEF.md` stays the
authority for Phase 1; nothing here changes a Phase 1 decision except where section 9 says so.

**Sources:**
- Marcos's Phase 2 notes (2026-09-28 session)
- `Phase 3 Summary.docx` — meeting notes, Ravishankar + Marcos (this work is "Phase 3" in the
  original doc's numbering, "Phase 2" in the project's)
- `Phase 2 process/master_file_w_calculations.xlsx` — Ravi's reference workbook, sheet
  `MaserFile_from STEP4 (2)`: the formulas for the calculated columns, with cached results

---

## 1. What this is

An extension of the existing Phase 1 app — **same app, same repo** — that takes the
consolidated master and:

1. generates a blank **`studyname_master`** template listing every study in the master;
2. accepts the **completed** template back from the user;
3. produces **`after_formulas_master`**: the master + 8 calculated columns + the user's study
   metadata merged onto every row of each study.

It replaces the manual "Create Additional Matrix" and part of the "Merge new Metrix" steps of the
Meta Analysis workflow (~5–7 days today).

---

## 2. Confirmed decisions (non-negotiable)

| # | Decision | Answer |
|---|----------|--------|
| P1 | Where it lives | **The existing app and repo.** New STEPs 7–9 on the same page, below Phase 1 results. |
| P2 | Project file across sessions | **`Master_File_*` stays the project file.** `after_formulas_master` is a derived output, rebuilt each time, never used as a master. |
| P3 | Output fed back as input | A file carrying Phase 2 calculated/merged columns is **detected** and gets a clear message (section 6). As a *study* → rejected with that message, run continues. Renamed `Master_*` and used as *master* → refused as master with that message; Run stays disabled until a proper master is supplied. |
| P4 | Master-only Run | **Run is enabled with a master and zero study files.** Result: 0 appended, master unchanged, Phase 2 unlocks. Only an *existing* master may run alone — the first-master slot is unchanged. **This changes Phase 1 behaviour** (section 9). |
| P5 | Template contents | Column A = **distinct** `Study_Name` values from the updated master, **verbatim**, in **first-appearance order**. Columns B–G blank. |
| P6 | Template headers | `Study_Name`, `Avg_Brand_Price`, `Avg_Purch_Cycle`, `Pct_HH_Buying`, `Tot_Camp_Cost`, `Tot_Camp_Impr`, `Read_Type`. `Avg_Brand_Price` does **not** state its period. |
| P7 | Template format | **`.xlsx`**, download only in xlsx. Sheet 1 = template, sheet 2 = glossary. Filename `studyname_master_<name>_<YYYY-MM-DD_HHMM>.xlsx`. |
| P8 | Column A locked | Sheet protection, **no password**. Columns B onward (including H+ for user extras) stay editable. |
| P9 | Template is always blank | No carry-over from earlier sessions. On-screen message explains this (section 6). |
| P10 | Upload formats | **`.xlsx` and `.csv` always accepted.** Excel: sheet 1 only (glossary sheet ignored). |
| P11 | Upload sanity check | **Refused** (no final file) if there is no `Study_Name` column, or if it contains master columns (i.e. the master itself was uploaded). **Accepted with strong warning** if `Study_Name` exists but zero studies match the master. This is Phase 2's single halt, parallel to Phase 1's unloadable-master exception. |
| P12 | Study-name matching | Trimmed, **case-insensitive**, otherwise exact. |
| P13 | Row mismatches | In master but not upload → merged columns blank, warning. In upload but not master → ignored, warning. Same study twice in upload → merged columns **blank** for that study, warning. Row with name but all values blank → "not filled in yet", blank, **no** warning. |
| P14 | User-added columns | Allowed from column **H** onward, merged after the fixed six. Blank header → ignored + warning. Header > 15 characters → warning, **still merged**. Duplicate header, or clash with a master column name → ignored + warning. |
| P15 | Fixed column missing/renamed in upload | Warning; that column is blank in the final file. |
| P16 | Value check | **On** (single flag in `config.py`). Columns B–F (`Avg_Brand_Price` … `Tot_Camp_Impr`) only. Non-numeric → **warning, value merged as typed**. Never blocks, never alters. `Read_Type` and user extras never checked. |
| P17 | What counts as numeric | Plain digits, optional leading `-`, optional decimal point, optional E-notation (`3.49`, `-2`, `1500000`, `1.2E+06`). Warn on thousands commas, currency symbols, a typed `%`, free text. Blank = fine. |
| P18 | Percentages | `Pct_HH_Buying` stored as a **decimal fraction** (`0.25`). Template column percent-formatted so users can type `25%`. |
| P19 | Final output format | **CSV of calculated values**, not Excel formulas. UTF-8-BOM like Phase 1. Filename `after_formulas_master_<name>_<YYYY-MM-DD_HHMM>.csv`. |
| P20 | Arithmetic | **Exact decimal arithmetic** (`decimal.Decimal`), never float. **Full precision everywhere**, products included. No rounding. |
| P21 | AM rounding | The workbook has `TEXT(N,"0.00")`. **Built at full precision**; rounding is one config setting if Ravi asks for it. |
| P22 | Block matching | A block = rows sharing **`Study_Name` + `MODEL_DESC` + `Model`**. The `pen` / `occ` / `dolhh` rows are found by `dependent_variable`, **case-insensitively**. Never by position. |
| P23 | Broken block | Missing or duplicated `pen` / `occ` / `dolhh` row → AH and AL blank for that block, warning. Single-row columns still calculate. |
| P24 | Source-column lookup | **By column name**, never by letter. Names live **only in `config.py`**. Required column missing → dependent calculated columns blank + one warning; merge still works. On-screen note always shown (section 6). |
| P25 | Calculated headers | Ravi's names, with trailing zero-width characters (`​`) **stripped** and "Instacart Member" → **"Partner Member"**. AN output as an **empty column with header**. |
| P26 | Final layout | Master unchanged → 8 calculated (AG–AN) → 6 merged fixed → user extras. **Placed relative to the master's last column**; letters are illustrative for a 32-column master. `Study_Name` is **not** repeated. Row count and order identical to the master. |
| P27 | Merge placement | Study values repeated on **every row** of that study (VLOOKUP-style). No Sum-pivot warning — pivot behaviour is the user's responsibility. |
| P28 | When the final file exists | **Only after a valid completed upload.** A user wanting calculations only may upload the blank template. |
| P29 | Recalculation | The final file is **always derived** from the current master + current upload. Pressing Run again rebuilds the template and final file automatically; never stale. |
| P30 | Warnings | Panel **above** the final download: summary line + expandable table `Study | Model | Column | Issue`. Plus a **`phase2_warnings`** CSV download, shown only when warnings exist. `✅ No issues found` otherwise. Never blocks the download. |
| P31 | Glossary | Template sheet 2 + on-screen expander. Draft in section 7, **Ravi confirms**. Calculated-column entries on screen only. |
| P32 | Screen layout | Section 5. |
| P33 | Build | Stages in section 10, `phase2` branch, QC after every stage. |

---

## 3. The calculated columns

Transcribed from `master_file_w_calculations.xlsx`. Every calculated value lands on **one** row
of its block; the other rows are blank (as in Excel, where the `IF` returns `""`).

Abbreviations: `N` = `ADJ_MEAN_EXPSD_GRP`, `G` = `CNT_EXPSD_HH`, `F` = `dependent_variable`.
`G` is populated only on `dolhh` rows in every sample file.

| Col | Header (as output) | Value | Lands on | Excel original |
|---|---|---|---|---|
| AG | Total Analyzed Population | `G` of the dolhh row | dolhh | `=IF(F="dolhh",G,"")` |
| AH | Count of Circana Buyers | `N`(pen) × `G`(dolhh) | pen | `=IF(F="Pen",N*INDIRECT("G"&ROW()+3),"")` |
| AI | Partner Member Overlap % with Circana Retailer | `N` of the pen row | pen | `=IF(F="pen",N,"")` |
| AJ | Dollars spent at Circana Retailer by HH | `N` of the dolhh row | dolhh | `=IF(F="dolhh",N,"")` |
| AK | Total Dollars spent at Circana Retailers | `N`(dolhh) × `G`(dolhh) | dolhh | `=IF(F="dolhh",N*G,"")` |
| AL | Total Buying Trips at Circana Retailer | `N`(pen) × `G`(dolhh) × `N`(occ) | pen | `=IF(F="Pen",N*INDIRECT("G"&ROW()+3)*INDIRECT("N"&ROW()+1),"")` |
| AM | Total Buying Trips per Buyer at Circana Retailer | `N` of the occ row, **full precision** | occ | `=IF(F="occ",TEXT(N,"0.00"),"")` |
| AN | Total Offline Category New Buyers | *(empty)* | — | *(no formula)* |

`dolocc` rows receive no calculated values.

### Facts established from the data

- All 10 sample studies and all 3 studies in the reference workbook are strict 4-row blocks in
  the order `pen, occ, dolocc, dolhh`. Excel's positional `ROW()+3` / `ROW()+1` depends on this;
  key matching (P22) does not.
- In every sample study, each `MODEL_DESC` + `Model` pair identifies exactly one clean 4-row block.
- The reference workbook has **cached results**: 53 non-blank values per column AG–AM across
  212 rows (Holly_Rancher 52, Instacart_Cascade 80, Instacart_Bel Brands 80). Example: AH2 =
  `0.036091684 × 12149247` = `438486.783561948` (Excel, 15 significant digits).
- The workbook stores some `N` values as text; Excel coerces them. The app parses them as
  `Decimal` directly.
- The workbook also has `AO = "Avg Price"`, `AP = "Purchase Cycle"` — superseded by P6.

---

## 4. Final file layout (`after_formulas_master`)

| Position (32-col master) | Content |
|---|---|
| A–AF | Master, unchanged, byte-for-byte |
| AG–AM | 7 calculated columns |
| AN | Total Offline Category New Buyers — empty |
| AO–AT | `Avg_Brand_Price`, `Avg_Purch_Cycle`, `Pct_HH_Buying`, `Tot_Camp_Cost`, `Tot_Camp_Impr`, `Read_Type` |
| AU+ | User-added columns, in the order they appear in the upload |

---

## 5. Screen layout

```
── Results (Phase 1, unchanged) ─────────────────────────────
  [metrics]  [file-by-file table]  [master preview]
  [Download updated master]  [Download exception report]

── Phase 2 · Study metadata & calculations ──────────────────
  STEP 7 — Download template
    ℹ️ template message (section 6)
    [Download studyname_master]          ▸ Glossary (expander)

  STEP 8 — Upload completed template (.xlsx or .csv)
    [ drop zone ]
    ❌ refusal message if wrong file (P11)

  STEP 9 — Final file  (only after a valid upload)
    ℹ️ column-name matching note (section 6)
    ⚠️ N warnings — summary line
       ▸ Details: Study | Model | Column | Issue
    [preview, 20 rows]
    [Download after_formulas_master]  [Download phase2_warnings]
    (or ✅ No issues found)
```

Phase 2 appears **only after Run**. The Phase 1 results must survive the rerun triggered by the
Phase 2 upload and downloads — the same session-state pattern Phase 1 STEP 6 already uses.

---

## 6. User-facing messages (agreed wording)

**Output fed back as input (P3):**
> ⚠️ **This file contains calculated columns.** It looks like an `after_formulas_master` output.
> Please upload the original Master File (`Master_File_…`), without calculations.

**Template (P9):**
> ℹ️ **This template lists all N studies currently in the master, with blank values.** Values from
> earlier sessions are not carried over. If you completed a `studyname_master` before, copy those
> rows into this new file before uploading it.

**Column-name matching (P24):**
> ℹ️ **Calculations match source columns by column name, not by position** (e.g. `CNT_EXPSD_HH`,
> `ADJ_MEAN_EXPSD_GRP`). If a column is renamed or missing in the master, the calculated columns
> that depend on it are left blank and listed in the warnings.

**Wrong file in the studyname slot (P11):**
> ❌ This doesn't look like a `studyname_master` file (no `Study_Name` column). Please upload the
> completed template downloaded above.

**Zero matching studies (P11):**
> ⚠️ None of the N studies in this file match the current master. Is this from a different project?

**Master-only Run (P4):**
> ℹ️ No study files uploaded. The master will be used as-is for Phase 2.

---

## 7. Glossary — DRAFT, pending Ravi's confirmation

### Columns to fill in (template sheet 2 and on screen)

| Header | Full name | What to enter | Example |
|---|---|---|---|
| `Study_Name` | Study name | **Locked** — filled by the app from the master. Do not edit. | `Instacart_Cascade` |
| `Avg_Brand_Price` | Average Brand Price | Average price of the target brand (study period or latest 52 weeks). Number only, no currency symbol. | `3.49` |
| `Avg_Purch_Cycle` | Average Purchase Cycle | Average time between purchases. Number only. **Unit: TBC (days?)** | `45` |
| `Pct_HH_Buying` | % Household Buying | Share of households buying. Type `25%` or `0.25` — stored as `0.25`. | `25%` |
| `Tot_Camp_Cost` | Total Campaign Cost | Total media cost of the campaign. Number only, no commas or currency symbol. | `150000` |
| `Tot_Camp_Impr` | Total Campaign Impressions | Total impressions delivered. Number only, no commas. | `12500000` |
| `Read_Type` | Read Type | Type of read, as text. | `Featured`, `Halo` |

### Adding your own columns
Add new columns from column **H** onward. Each header must be unique, must not repeat a master
column name, and should be **15 characters or fewer**.

### Rules
- Column A is locked; study names come from the master.
- A blank cell means "not filled in yet" and stays blank in the final file.
- Numbers: plain digits only — no `$`, no thousands commas, no text. Anything else is kept as
  typed but flagged in the warnings.
- Values are repeated on every row of their study in the final file.

### Calculated columns (on screen only)
The eight AG–AN entries of section 3, in plain English, e.g. *"Count of Circana Buyers =
ADJ_MEAN_EXPSD_GRP of the pen row × CNT_EXPSD_HH of the dolhh row, per model block."*

---

## 8. Verification standard

Two layers, both in the QC suite:

1. **Synthetic tests — always run, no client data.** A small fabricated master with hand-checkable
   values (e.g. `N`(pen) = `0.5`, `G`(dolhh) = `1000` → AH = `500` exactly). Covers every formula
   and every edge case: broken block, `Pen` vs `pen`, shuffled rows, missing source column, long
   decimals kept exact.
2. **Reference-workbook comparison — runs when `Phase 2 process/master_file_w_calculations.xlsx`
   is present.** Rebuild the workbook's master from the same 3 sample studies, calculate, and
   compare **every AG–AM cell on all 212 rows** against Excel's cached values:
   - Excel non-blank → app agrees to **15 significant digits**.
   - Excel blank → app blank.
   - AM: app's full value must **round to** Excel's 2-decimal text.
   - A **shuffled-row** rerun must produce identical results.
   - Workbook absent → loud `SKIPPED — reference workbook not found`. Never counted as a pass,
     never fails the run.

**QC sign-off on the calculation stage requires layer 2 to have actually run.** The workbook is
client data and is blocked by `.gitignore` (`*.xlsx`) — it must never be committed.

---

## 9. Changes to Phase 1 and to project rules

- **P4 — master-only Run.** `app.py` Run-enable rule changes from "master and ≥1 study" to
  "master, and either ≥1 study or an existing master". Needs its own test.
- **P3 — output detection.** Phase 1 detection recognises Phase 2 output columns.
- **`CLAUDE.md` rule 2** — no float/numeric coercion of data. Phase 2 calculations use
  `decimal.Decimal` on parsed copies; source values are never altered and are still written
  byte-exact.
- **`CLAUDE.md` rule 4** — becomes *"column names appear only in `config.py`"*. The QC scan that
  enforces it is updated to exempt `config.py` and still scan every other module.

---

## 10. Build stages

`architect` → `python-developer` one stage at a time → `qc-reviewer` after **every** stage.

| Stage | What | Touches |
|---|---|---|
| 0 | This brief, `QUESTIONS_FOR_RAVI.md` update, `CLAUDE.md` rules, then `architect` design | Docs |
| 1 | Master-only Run (P4); output-as-input detection (P3) | `app.py`, `master_detector.py`, tests |
| 2 | Template generation (P5–P9, glossary sheet) | New module |
| 3 | Calculations (section 3, P20–P25) + both test layers | New module |
| 4 | Upload validation + matching + value check + extras + merge + warnings report | New module |
| 5 | UI STEPs 7–9 in `app.py`, recalculation on rerun, then interactive check | `app.py` |

**Before Stage 5:** complete the outstanding Phase 1 interactive checks in `CLAUDE.md`. Phase 2
builds on the download-rerun path, which has never been clicked through by a human.

---

## 11. Open — for Ravi

1. Template values: **numbers only, or strings too?** (Value check is on until answered.)
2. **AM**: full precision (as built) or rounded to 2 decimals as in the workbook?
3. Calculated headers: OK to **strip the zero-width characters** and rename
   **"Instacart Member" → "Partner Member"**?
4. **Unit of `Avg_Purch_Cycle`** — days or weeks?
5. **Glossary definitions** (section 7) — confirm or correct.

## 12. Out of scope for this phase

- Automatic retrieval of the metadata values (the user fills the template by hand)
- Derived metrics beyond AG–AM (ROAS, % Lift, weekly impressions, etc.)
- Pre-filling the template from a previous session's completed file (candidate for v2)
- Reporting, charts, bucketing, histograms (later phase, per the meeting notes)
- Column mapping / aliases for other clients' naming — revisit with Phase 1 Q5
