# Questions for Ravi — Meta Analysis Enhancement Proposal

Context: questions on `Meta Analysis_NewV1.docx` (the 4-phase Meta Analysis automation proposal), to clarify scope, priority, and feasibility before estimating any build work.

---

> ## ANNOTATED 2026-09-07 — Phase 1 has since been built
>
> Since this list was written, Phase 1 was scoped, designed and built: see `META_BRIEF.md`
> (19 locked decisions), `ARCHITECTURE.md` (design), and `code/` (236 tests passing).
> Annotations below mark what the build already answers, so this list isn't re-asked wholesale.
>
> **Original questions are unchanged.** Annotations are indented beneath each.
>
> | Marker | Meaning |
> |---|---|
> | ✅ **ANSWERED** | Settled by a locked decision. Confirm only if Ravi disagrees. |
> | ⚠️ **OPEN — AFFECTS BUILT CODE** | Not decided, and the answer changes code that already exists. **Ask these.** |
> | ⬜ **OPEN — LATER PHASE** | Still genuinely open, but Phases 2–4 are out of scope, so not urgent. |
>
> **The three that matter most are Q5, Q15 and Q16.** All three concern the tool as built.

---

## On priority and scope

1. Of the 4 phases, which one(s) do you want me to actually scope and estimate for build right now, versus which are long-term direction you want documented but not committed to a timeline?

   > ✅ **ANSWERED** — Phase 1 only (decision 1). Phases 2–4 documented, not committed. Phase 1 is now built.

2. For whichever phase(s) are "now" — is there a target rollout date or milestone (e.g. a specific upcoming Meta Analysis project) this needs to be ready for?

   > ⬜ **STILL OPEN** — never asked. Now more pressing, not less: the code is done, so this is a deployment-scheduling question. Hosting is on Circana-controlled infrastructure (decision 2), which needs IT provisioning — the long pole, and outside our control.

3. Is there a specific second client or engagement already lined up that needs the generalized version, or is "usable for any client" the goal without a concrete second use case yet? I ask because the original tool was deliberately built narrow for one client's file format — I want to build the right amount of flexibility, not more than needed.

   > ⚠️ **OPEN — AFFECTS BUILT CODE.** Directly tied to Q5. All 10 sample files came from one client set and have byte-identical headers. If a second client's scored files differ, the answer to Q5 becomes urgent rather than theoretical.

4. Once Phase 1 is delivered, should I treat that as a complete, standalone deliverable — not an automatic commitment to start Phase 2 — so we scope 2-4 as separate conversations later?

   > ✅ **ANSWERED** — yes, standalone (decision 1).

## On Phase 1 (consolidation automation)

5. The spec calls for validating each new file's structure strictly against the Master file. The original tool instead tolerated column-name variation across sources using an alias map (I hit real differences in column naming across files). Do you want strict exact-match validation this time, or should it still tolerate known naming variants?

   > ⚠️ **OPEN — AFFECTS BUILT CODE. Highest-risk item on this list.**
   >
   > Built as: column **names must match**, tolerant of case and whitespace only (decision 8). Incoming column *order* doesn't matter — files are reordered to the master's order (decision 9). **There is no alias map.**
   >
   > That was the right call on the evidence — all 10 samples have byte-identical 31-column headers, so an alias map would have been unused machinery. But they are all one client, one scoring engine. This question notes the Antara tool needed aliases *because real naming differences turned up*.
   >
   > **If naming varies across clients, every file from a differing client rejects and the tool looks broken.** Ask Ravi directly whether he has seen the scored-file column names vary. If yes, an alias map is a real Phase 1 gap and should be added before rollout.

6. Resuming an existing project is based on the file being named with a `Master_` prefix. Is filename-based detection acceptable, or should I plan for something more durable — e.g. if the file gets renamed, downloaded twice, or two people work off copies of the same study set?

   > ✅ **MOSTLY ANSWERED** — detection is the `Master_` prefix (case-insensitive) **plus** verification that the file actually has a `Study_Name` column, so a misnamed study file can't masquerade as a master (decision 15, spec section 3). Two candidates → the app asks which. Every run produces a new timestamped download, so nothing is overwritten (decision 16).
   >
   > ⚠️ **Still unaddressed:** two people working off copies of the same study set. The app is stateless with no server-side storage (decision 4), so nothing detects or reconciles divergent copies. Probably acceptable, but it is undecided rather than decided.

## On Phase 2 (study search & bulk download)

7. What platform/system actually holds the study search data and score files today? Will I have API or export access to query and bulk-download from it, or is this only accessible through a manual UI right now?

   > ⬜ **OPEN — LATER PHASE.** Phase 2 out of scope. This is its blocking dependency — worth asking early, since a "manual UI only" answer would make Phase 2 largely infeasible as written.

## On Phase 3 (metric enrichment & benchmarking)

8. Where do Total Campaign Cost, Total Campaign Impressions, % Household Buying, Average Purchase Cycle, and Average Brand Price currently come from — which reports or systems? Are those queryable somewhere, or are analysts compiling them manually today? I want to know before estimating, since if there's no systematic source for these yet, that's a data-availability problem, not something Python can solve on its own.

   > ⬜ **OPEN — LATER PHASE.** Phase 3 out of scope. The framing holds: if there's no systematic source, no amount of code fixes it.

## Gaps and inconsistencies in the doc itself

9. The manual Step 2 description says your tool already "standardizes break names/Model_Desc column" for Antra, but the Phase 1 Functional Requirements only mention adding a Study Name column and validating/appending structure — standardizing break/label names across clients isn't listed. Should that be part of Phase 1? If so, since break names vary by client, what's the standardization logic supposed to be — a lookup table I maintain and extend per client, or something else?

   > ✅ **ANSWERED** — **out of scope for Phase 1** (decision 13). `MODEL_DESC` values are appended exactly as-is; standardization stays manual.
   >
   > The sample data confirms the instinct behind the question. Across 10 files: `freq(1)`, `freq(2)`, `freq(2+)`, `freq(2-3)`, `freq(3+)`, `freq(4+)`, `freq(5-6)`, `freq(7+)`, `freq(static_1_)`…`freq(static_10+_)`; `publisher(Instacart)` vs `publisher(Liveramp)`; `audience_crt(Group3…Group60)`.
   >
   > This is not a naming problem — it is a **bucketing** problem. `freq(2+)` means "2 or more"; `freq(2)` means "exactly 2" because that study also has `freq(3)` and `freq(4+)`. No rename reconciles them. Deciding which buckets are comparable is an analytical judgment, and it belongs with Phase 4 bucketing — not baked irreversibly into the raw data at append time.

10. The original 5-step manual process ends with "Finalize the story and create final PPT" (4-5 days). None of the 4 phases cover that — Phase 4 stops at "export-ready charts, tables, and summaries." Is final PPT/story assembly intentionally staying manual forever, or is there a Phase 5 that just hasn't been written up yet?

    > ⬜ **OPEN — LATER PHASE.** Genuine gap in the source document; unaffected by the Phase 1 build.

11. File formats and volume: will source files always be .xlsx/.csv across every client, or should I plan for other formats? And roughly how many study files, and how large, make up a typical Meta Analysis (10 files? 100? what size each)? This determines whether a straightforward pandas-based approach holds up or something else is needed.

    > ✅ **MOSTLY ANSWERED.** Formats: `.csv` and `.xlsx`, Excel reading sheet 1 (decision 6). Every csv/xlsx in a batch is attempted; unrelated spreadsheets surface as rejections, accepted as noise.
    >
    > Volume is measured, not estimated: sample study files run **52–96 data rows each**, so a 100-study master lands near 8,000 rows. **Scale is a non-issue** — pandas is comfortably the right tool.
    >
    > ⚠️ **Still unconfirmed:** whether formats other than csv/xlsx ever appear at other clients.

## On Phase 4 (bucketing, histograms, insight generation)

12. "Automatic generation of recommended bucket ranges based on data distribution" — is there a bucketing method analysts already use today (quantiles, fixed-width ranges, something else), or am I defining that methodology from scratch?

    > ⬜ **OPEN — LATER PHASE.** See Q9 — this is where the `MODEL_DESC` reconciliation problem properly belongs.

13. "Statistical significance indicators where applicable" — what test and threshold should this use (e.g. t-test on lift, confidence interval), or is there an existing standard the analytics team already follows that I should match?

    > ⬜ **OPEN — LATER PHASE.** Note the scored files already carry `TWOTAIL_PVAL`, `ONETAIL_PVAL`, and 80/90% interval bounds — so significance may already be upstream rather than something to compute.

## On Phase 1 mechanics (additional)

14. In bulk folder mode, the first valid file found becomes the Master and sets the reference schema — first by what ordering (alphabetical, file date, something else)? And if that particular file happens to be missing a column that later files have, is it still treated as authoritative, or should I be able to designate which file defines the schema?

    > ✅ **ANSWERED — and the built design supersedes the premise.** There is no automatic "first file" ordering at all. If the batch contains a `Master_*` file, that is the schema authority. If it does not, a slot appears asking **"Which file do you want to use as the first Master?"** and the user designates it explicitly (brief section 3, step 4). The poison-pick risk this question anticipates cannot occur.

15. Once a Master file's reference schema is set, is it locked for the life of that Meta Analysis project, or does a legitimate new column need to be addable later without every other file suddenly failing validation?

    > ⚠️ **OPEN — AFFECTS BUILT CODE. Not decided; the current behaviour fell out of another decision rather than being chosen.**
    >
    > As built, the schema is effectively **locked**: the master defines the columns (decision 7), and a file with a column the master lacks is `extra` → rejected (decision 10). So a legitimately new column appearing mid-study means **every subsequent file fails validation**, with no in-tool path to widen the master.
    >
    > That may well be correct — silent schema drift is exactly what validation exists to prevent — but nobody chose it. If new columns are a real occurrence, Phase 1 needs a deliberate "extend the master" path.

16. When a file fails structure validation and lands in the exception report, what's supposed to happen next — does the user fix the source file and re-run it, or do you want an in-tool way to remap/fix columns before retrying?

    > ⚠️ **OPEN — AFFECTS BUILT CODE.**
    >
    > As built: **fix the source file and re-run.** There is no in-tool remap. Re-running is safe and cheap — duplicate studies skip automatically, so an analyst can fix one file and re-drop the whole batch, and only the fixed file appends (decision 12).
    >
    > A defensible v1 choice, but a choice. If remapping is expected, it is a Phase 1 gap. Note it would also partly overlap the alias-map question in Q5 — answering Q5 "yes, aliases" would remove much of the need for manual remapping.

## On Phase 3 (derived metric definitions)

17. The derived metrics (ROAS, %Lift, Absolute Difference, Average Weekly Impressions, etc.) aren't defined with formulas. Since these can be computed more than one way (e.g. is %Lift `(Exposed-Control)/Control` or something else; is ROAS revenue/cost or a different ratio), can you give me the exact formula for each so the numbers match what analysts already report?

    > ⬜ **OPEN — LATER PHASE.** Phase 3 out of scope. Worth getting in writing regardless — ambiguous formulas are how automated numbers end up quietly disagreeing with the ones analysts already publish.

## On Phase 2 (field list)

18. The search filters and output fields both end in "additional project/key attributes as available" — can you give me the definitive field list you need for a usable MVP, rather than "as available," so I'm not guessing at what the platform actually exposes?

    > ⬜ **OPEN — LATER PHASE.** Phase 2 out of scope.

## On phase dependencies

19. Phase 3 depends on Phase 1's consolidated output, and Phase 4 depends on Phase 3's enriched output — so 1 → 3 → 4 is a real chain. Phase 2 is only loosely linked (its output just needs to match Phase 1's input format), but its "Future-State Consideration" suggests it could eventually replace Phase 1's consolidation step entirely (download + append + tag in one shot). Is that future-state a real intention? If so, I'd rather keep Phase 1's append/validation logic simple now instead of over-investing in mechanics that Phase 2 might supersede later.

    > ✅ **THE INSTINCT WAS FOLLOWED.** Phase 1 was deliberately kept minimal: no alias map, no `MODEL_DESC` standardization, no schema-extension path, no in-tool remap, no persistence. Roughly 1,240 lines of application code.
    >
    > ⬜ **Still worth confirming** whether the Phase 2 future-state is a real intention — it determines whether the Q5/Q15/Q16 gaps are worth closing in Phase 1 at all, or whether Phase 2 would supersede them anyway.

---

## Additional items for the same conversation

Not in the original list — these arose from building Phase 1 and need the same sign-off.

**Four deviations from the source document** (detail in `META_BRIEF.md` section 7). All four follow from the decision to build a hosted web app rather than a local tool:

| Doc says | As built | Why |
|---|---|---|
| "Output Folder" as a user input | Master is **downloaded** | A hosted app cannot see a user's drive |
| "Bulk folder processing", "select a folder" | **Select-all-files** (Ctrl+A) | Browsers do not hand folder paths to servers — a security boundary, not a tool limitation |
| "Standardize break names/Model_Desc" | **Stays manual** | See Q9 |
| "Store the file structure as the reference schema" | Read from the **master at runtime** | Same outcome, no stored state |

**One behaviour that is correct-by-spec but surprising**, worth showing Ravi rather than letting him discover it: a previously-produced master fed back in as a *study* file has identical columns, so it validates cleanly and appends, with its `Study_Name` overwritten. It duplicates that master's rows under a new name. Every rule works as designed; the outcome still surprises. Detail in `ARCHITECTURE.md` section 8 item 9.

---

## Phase 2 (study metadata & calculations) — added 2026-09-28

Scoped in `PHASE2_BRIEF.md` (33 locked decisions). Not yet built. These five are the open points
from that interview; each has a working default so the build is not blocked.

20. **Studyname template values — numbers only, or text too?** Columns `Avg_Brand_Price`,
    `Avg_Purch_Cycle`, `Pct_HH_Buying`, `Tot_Camp_Cost`, `Tot_Camp_Impr` look numeric;
    `Read_Type` is text.

    > **Default:** a non-numeric value in those five columns is **flagged as a warning but kept
    > as typed** — never blocked, never altered. One config flag turns the check off.

21. **Total Buying Trips per Buyer (AM) — rounded or full precision?** Your workbook formula is
    `TEXT(N,"0.00")`, which rounds to 2 decimals and stores text (`1.95`). Every other column keeps
    full precision.

    > **Default:** full precision (`1.9454682413648197`), so nothing is lost before later phases.
    > Rounding is one config setting if you want it.

22. **Calculated-column headers — two clean-ups OK?**
    (a) Six of the eight headers end in an invisible zero-width character (`​`), almost
    certainly from copy-paste; it breaks pivots and lookups. (b) "**Instacart** Member Overlap %
    with Circana Retailer" names one partner in a tool meant for any client.

    > **Default:** strip the hidden characters; rename to "**Partner** Member Overlap % with
    > Circana Retailer". All other wording unchanged.

23. **What unit is Average Purchase Cycle in** — days or weeks? The workbook's sample values
    (25, 100, 150) do not settle it.

    > **Default:** glossary says "unit: TBC".

24. **Glossary definitions** — please confirm or correct the draft in `PHASE2_BRIEF.md`
    section 7. It ships inside the template (sheet 2) and on screen.
