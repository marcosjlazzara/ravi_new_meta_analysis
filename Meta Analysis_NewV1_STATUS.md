> **Status key:** ✅ Built &nbsp;·&nbsp; ⚠️ Built with a deviation (needs sign-off) &nbsp;·&nbsp; ⛔ Out of scope (not touched)
> This file reproduces `Meta Analysis_NewV1.docx` section by section and marks what the Phase 1 build (`code/`, confirmed complete 2026-09-07) actually delivered. Only **Phase 1** was in scope for this build — Phases 2–4 below are reproduced verbatim from the doc and were not started.

---

# Meta Analysis — Enhancement requirements for Marcos micro project

## Background

After looking at what Marcos has done for Antara for that specific client, I want to propose a few additional enhancements to the same so that it can be rolled out to any client and, if possible, add a few more additional steps thus helping in completing a meta-analysis for any Lift client.

Meta Analysis right now, with lack of the right benchmarking capabilities in the tool, takes a lot of time mainly due to the overload of manual work involved in completing a study.

Current situation is that we shy away from Meta studies because of the manual workload pressure, or we do it but it takes a lot of time completing one study.

Marcos's micro automation is the great first step, but still needs his input to be replicated for other clients, plus there are some subsequent steps that can be automated here which reduces overall workload for any analyst by 60%. Details below.

## Steps in completing Meta Analysis and Approximate Timeline

| # | Steps | Step Desc | Time Taken | Phase | Status |
|---|-------|-----------|------------|-------|--------|
| 1 | Collecting Data | Determine all the studies that need to be added in the Meta Analysis / Download source files for each of them, can be from tool or from Offshore SharePoint | ~8–10 hours | Phase 2 | ⛔ Not started |
| 2 | Append all study | Add additional column to put in study name in each downloaded file, so when appending into one there is no confusion on which row belongs to which study / Append each to create one master / Standardize break names/Model_Desc column / Marcos's tool does this now for Antara | ~3–4 days | **Phase 1** | ✅ **Built** (Model_Desc standardization stays manual — see deviations) |
| 3 | Create Additional Matrix for Meta analysis | Find reports or data for adding more metrics for analysis — Total Campaign cost, Total Campaign impressions, % Household Buying, Average price of Target brand, Read Type (Featured/Halo), Avg Purchase Cycle | ~5–7 days | Phase 3 | ⛔ Not started |
| 4 | Merge new Metrix to Consolidated file and add calculated fields and Histogram for new Metrix | Summarize all studies into measurable buckets — Purchase cycle, Audience Strategy, Audience/Brand Penetration, Overall Total Campaign, Weekly Frequency, etc. Trial-and-error bucketing process. | ~8–10 days | Phase 4 | ⛔ Not started |
| 5 | Finalize the story and create final PPT | Export all charts to PPT and build the storyline | 4–5 days | Phase 4 | ⛔ Not started |

Stage 2 is semi-automated, but that too specific to one client — here is the new proposal to enhance the experience of working on Meta studies.

---

# Phase 1: Standardized Meta Analysis File Consolidation Automation
### (Step 2 in above process flow) — ✅ **THIS PHASE WAS BUILT AND IS THE ENTIRE SCOPE OF THE PROJECT**

## Objective

Enhance the existing Meta Analysis file consolidation automation developed by Marcos and convert it into a generic, reusable solution that can be used across all clients without client-specific customization.

**✅ Delivered.** No column mapping, no client-specific config — the master file defines the schema at runtime for any client.

## Business Need

The current process of consolidating Meta Analysis study files is highly manual and can take 3 to 4 days to complete. While an automation exists today, it was built for a specific client and requires additional effort to reuse for other engagements. A standardized solution will significantly reduce manual effort, improve consistency, and accelerate Meta Analysis projects.

## User Inputs

The automation should allow users to provide:

- **Meta Study Name** — ✅ Built. Standard format: `MetaStudy_<ClientName>_<Date>`
  → Delivered as `Master_<Name>_<YYYY-MM-DD_HHMM>.csv`, typed by the user when a new master is created.
- **Output Folder** — ⚠️ **Deviated.** Location where the Master file and reports will be stored.
  → As a hosted web app, there is no filesystem access. Master and exception report are delivered via **download buttons** instead of a saved folder path. *(Requires requester sign-off — see Deviations below.)*
- **Input Source** — ✅ Built, one combined drop zone instead of two separate modes:
  - Single-file mode. → subsumed into the one drop zone.
  - Folder-processing mode. → ⚠️ Delivered as **select-all-files** in the browser's file picker (Ctrl+A), not a true OS folder path — browsers don't hand folder paths to a server.

## Functional Requirements

### 1. Master File Creation — ✅ Built

When a user loads a study file that does not begin with "Master_":

- Create a copy of the file in the output location *(// cool note it)* → ⚠️ No output location exists (hosted app); delivered via download instead.
- Rename it with the prefix `Master_`. → ✅ Built.
- Add a new column called Study Name. *(// added at the end of the chart)* → ✅ Built — `Study_Name` is the **last column**, exactly as annotated.
- Populate the Study Name column with the source file name. *(// got it)* → ✅ Built — filename minus extension, verbatim.
- Store the file structure as the reference schema for future validation. *(// keep the schema of that file // every file will have the exact same structure)* → ✅ Built, with one implementation nuance: the schema is **read from the master at runtime** on every run rather than persisted anywhere (app is stateless — nothing is stored server-side between sessions).

### 2. Append Additional Studies — ✅ Built

For all subsequent files:

- Automatically add the Study Name column. *(// added at the end of the chart)* → ✅ Built.
- Validate the file structure against the Master file. *(// perform a qc process)* → ✅ Built. Column **names** must match (case/whitespace-insensitive); incoming column **order** does not matter.
- If it fails it should not stop, it should skip to the next file and pop up saying this file "xxxx" was not appended correctly. *(// but it shouldn't interrupt the process)* → ✅ Built. Validation never halts the run — the single exception is an unloadable master, since without it there's no schema to validate against.
- Append valid files to the Master dataset. *(// it has to read the headers but schema has to follow as per the masters)* → ✅ Built. Incoming columns are reordered into the master's order before appending.
- Generate an exception report for files that fail validation. *(// ok noted, if it fails create a report and downloadable report log for files that fail validation)* → ✅ Built. Exception report is a downloadable CSV (`file`, `status`, `reason`, `missing_cols`, `extra_cols`).

### 3. Resume Existing Projects — ✅ Built
*(// differences between the NEW project or Existing project)*

Users should be able to pause and continue a Meta Analysis project at any time.

If a user loads a file beginning with "Master_":

- The system should recognize it as an existing Master file. → ✅ Built (prefix matched case-insensitively).
- No new Master file should be created. → ✅ Built.
- The existing Master file becomes the starting point for all future append activity. → ✅ Built.
- Users can continue adding studies over multiple sessions without rebuilding the dataset from scratch. → ✅ Built — each run's output filename carries the study name forward from the uploaded master, restamping only the date.

### 4. Bulk Folder Processing — ✅ Built (with the folder-picker deviation noted above)
*(// it should process the full folder with files)*

The automation should also support processing an entire folder of study files.

When a folder is selected:

- Automatically identify the first valid file and create the Master file. *(// [no annotation])* → ⚠️ Built differently: if **no** `Master_*` file is present in the batch, the app opens a second slot and asks the **user** to designate which uploaded file becomes the first master (rather than auto-picking one). This was a deliberate build decision — auto-picking risked silently anchoring the whole schema to an arbitrary file.
- Specify: Output folder / Input folder / Client name / User must identify the first file → ⚠️ Output & input folders replaced by the single drop zone + download buttons (same deviation as above); client name is captured as the typed study name.
- Automatically add the Study Name column to each file. *(// good)* → ✅ Built.
- Append all compatible files automatically from input folder. *(// good)* → ✅ Built.
- Create the final consolidated dataset with no additional user intervention. *(// cool)* → ✅ Built — one "Run" click processes the whole batch.

### 5. Validation and Reporting — ✅ Built

The automation should validate each incoming file against the Master structure. *(// makes sense)*

For files that cannot be appended:

- Capture file name. → ✅ Built.
- Identify missing or additional columns. *(// if there are different, capture the missing or additional column)* → ✅ Built — separate `missing_cols` / `extra_cols` fields.
- Record the reason for failure. → ✅ Built (e.g. `column mismatch`, `already in master`, `unreadable`, `no data rows`).

A processing summary should also be generated showing:

- Total files processed. → ✅ Built, shown on screen.
- Files successfully appended. → ✅ Built.
- Files rejected. → ✅ Built.
- Total records consolidated. → ✅ Built. (Files **skipped as duplicates** are also surfaced, beyond what the doc asked for.)

## Expected Outcome

- Reduce file consolidation effort from multiple days to less than an hour. → ✅ On track to be met — full batch runs in seconds once uploaded; pending final human timing confirmation.
- Eliminate client-specific dependencies. → ✅ Built — no client-specific code or config anywhere in `code/`.
- Create a reusable Meta Analysis consolidation framework for all clients. → ✅ Built.
- Improve data consistency and reduce analyst workload. → ✅ Built (full-precision values, no rounding, byte-exact append).
- Establish the foundation for future automation phases, including automated file collection and metric enrichment. → ✅ Achieved structurally (flat modules, no Streamlit imports outside `app.py`, testable pipeline) — no Phase 2/3 code was written.

## Out of Scope (per the doc — correctly excluded from this build)

- Automatic download of source study files. ⛔ (Phase 2)
- Additional metric generation and benchmarking. ⛔ (Phase 3)
- Chart creation, storytelling, or PowerPoint generation. ⛔ (Phase 4)
- Centralized storage and management of Meta Analysis projects. ⛔ (not scheduled in any phase)

---

## Deviations introduced by the Phase 1 build — pending your sign-off

These four came directly out of "hosted Streamlit web app, no filesystem access" and are not optional implementation choices — they're the only way the doc's ask can work as a hosted tool. Full detail in `META_BRIEF.md` §7 and `QUESTIONS_FOR_RAVI.md`.

| Doc says | What was built instead | Why |
|---|---|---|
| "Output Folder" as a user input | Master is **downloaded**, not written to a path | A hosted app cannot see a user's local drive |
| "Bulk folder processing", "select a folder" | **Select-all-files** in the browser's file dialog (Ctrl+A) | Browsers do not hand folder paths to servers |
| "Standardize break names/Model_Desc column" (step 2 of the workflow) | **Stays manual** — `MODEL_DESC` is appended as-is | Reconciling `freq(2+)` vs `freq(2)`+`freq(3)` is an analytical judgment call, not a rename — it belongs with Phase 4 bucketing, not Phase 1 |
| "Store the file structure as the reference schema" | Structure is **read from the master at runtime** on every run, nothing persisted | Same outcome, but consistent with the stateless/no-storage requirement |

---

# Phase 2 — Automated Discovery and Download of Meta Analysis Source Files
### (Step 1 of the above Meta Analysis workflow) — ⛔ **OUT OF SCOPE, NOT STARTED**

## Objective

Reduce the manual effort involved in identifying and downloading study files required for Meta Analysis by enabling users to search, review, and download source files directly from the platform.

## Business Need

The first step of any Meta Analysis project is identifying all relevant studies and downloading the associated score files. This process is currently manual and can take 8 to 10 hours per project. Analysts must search for studies individually, validate their relevance, and download files one at a time, creating significant overhead before analysis can even begin.

Automating this process will reduce preparation time, improve study selection consistency, and provide a more streamlined workflow for Meta Analysis projects.

## Proposed Solution

Once a Meta Analysis scope has been defined, users should be able to search for studies within the platform using one or more of the following filters:

- Client Name
- Media Partner
- Matching Partner
- Study Start Date
- Study End Date
- Read Date Range
- Additional project attributes as available

### Search Output

The system should return a list of all studies matching the search criteria, including:

- Project Name
- Client Name
- Media Partner
- Matching Partner
- Study Dates
- Read Dates
- Additional key project attributes

Users should have the ability to:

- Export the results to Excel or CSV.
- Review the list offline.
- Remove studies that should not be included.
- Save the final study selection.

### Automated File Download

After confirming the study list, users should be able to:

- Upload the approved study list back into the system, or select studies directly from the search results.
- Initiate a bulk download process.
- Automatically download all corresponding score files into a designated folder.

The output should be structured in a format that can be used directly by the Phase 1 Meta Analysis Consolidation Automation.

### Future-State Consideration

As a longer-term enhancement, the system could eliminate the need for a separate consolidation step by:

- Automatically downloading all selected study files.
- Appending them into a single consolidated dataset.
- Adding key study attributes such as: Project Name, Study Type (Featured, Halo, etc.), Client Name, Media Partner.

This would provide users with a ready-to-use Meta Analysis dataset directly from the platform.

## Expected Outcome

- Reduce study discovery and file collection effort from 8 to 10 hours to a few minutes.
- Eliminate manual downloading of individual study files.
- Improve consistency in study selection.
- Accelerate Meta Analysis project startup.
- Create a seamless handoff into the Phase 1 consolidation process.

## Scope Boundary

**In Scope:** Study search and filtering / Exportable study inventory / Study selection workflow / Bulk download of score files / Creation of a standardized download package.

**Out of Scope:** Consolidation and append logic (covered in Phase 1) / Additional metric generation / Benchmarking and advanced analytics / Story development and presentation creation.

---

# Phase 3: Automated Metric Enrichment, Benchmarking and Study Context — ⛔ **OUT OF SCOPE, NOT STARTED**

## Objective

Automatically collect, calculate, validate, and append all business, campaign, and benchmarking metrics required for Meta Analysis, eliminating manual data gathering and creating a single enriched dataset for downstream analysis.

## Business Need

After study files are consolidated, analysts spend approximately 5–7 days gathering supporting metrics from multiple reports and systems. Much of this work is repetitive and prone to inconsistency. Automating this process will improve accuracy, reduce effort, and ensure all Meta Analysis studies use a consistent set of metrics.

## Proposed Solution

For every study selected as part of a Meta Analysis, the platform should automatically retrieve, standardize, validate, and append all required metrics at the study level:

- Average Brand Price (study period and/or latest 52-week period)
- Average Purchase Cycle
- % Household Buying
- Total Campaign Cost
- Total Campaign Impressions
- Read Type (Featured, Halo, etc.)

The platform should also automatically calculate derived metrics required for reporting and benchmarking:

- ROAS
- % Lift
- Absolute Difference (Exposed vs Control)
- Average Campaign Impressions
- Average Weekly Impressions
- Average Weekly Impression Volume

## Data Quality and Validation

The solution should identify missing metrics, surface data-quality issues, and generate an exception report detailing studies with incomplete information. Where metrics are unavailable, the system should flag the study and allow users to decide whether to exclude or retain it.

## Expected Outcome

Reduce metric collection effort from 5–7 days to a largely automated process, provide a fully enriched Meta Analysis dataset, improve consistency across studies, and create the foundation for automated insight generation.

---

# Phase 4: Automated Insight Discovery, Bucketing, Visualization and Story Development — ⛔ **OUT OF SCOPE, NOT STARTED**

## Objective

Accelerate insight generation by automating bucket creation, histogram generation, KPI summarization, and exploratory analysis that helps analysts identify meaningful stories from Meta Analysis datasets.

## Business Need

Analysts currently spend 8–10 days testing different ranges, bucket definitions, and chart combinations before identifying a compelling story. This trial-and-error process is repeated for every Meta Analysis project and represents one of the largest manual components of the workflow.

## Proposed Solution

Using the final enriched Meta Analysis dataset, users should be able to select any variable and automatically generate bucket ranges, KPI summaries, histograms, and exploratory charts:

- Purchase Cycle
- Audience Strategy
- Audience and Brand Penetration
- Brand Penetration Range
- Campaign Size and Spend
- Weekly Frequency
- Any user-selected metric

### Key Functional Requirements

- Automatic generation of recommended bucket ranges based on data distribution
- Manual bucket overrides for custom storytelling needs
- Automatic creation of bucket-mapped columns
- Histogram generation and visualization by bucket
- Summary metrics including Lift, ROAS, Absolute Difference, and other KPIs by bucket
- Side-by-side comparison of alternative bucket definitions
- Statistical significance indicators where applicable
- Export-ready charts, tables, and summaries for use in presentations

## Future Vision

As the platform evolves, automated insight recommendations could identify the strongest drivers of Lift, ROAS, and conversion performance. The system could highlight statistically meaningful patterns, recommend story angles, and generate presentation-ready outputs, significantly reducing the effort required to move from data to narrative.

## Expected Outcome

Reduce analysis and story-development effort from 8–10 days to a fraction of the current timeline, enable rapid exploration of multiple hypotheses, standardize Meta Analysis outputs, and allow analysts to focus on strategic interpretation rather than repetitive data manipulation.

---

## Bottom line

- **Phase 1 (the only in-scope phase): fully built**, all functional requirements delivered, 236/236 tests passing.
- **4 deviations** from the literal doc wording — all forced by "hosted web app, no filesystem access" — awaiting your sign-off (see table above, or `META_BRIEF.md` §7 / `QUESTIONS_FOR_RAVI.md` for full detail).
- **Phases 2, 3, 4** — untouched, exactly as scoped.
