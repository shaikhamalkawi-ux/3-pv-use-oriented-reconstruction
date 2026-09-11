# PVDAQ 2107 — Pre-Outcome Schema and Implementation-Conformance Amendment

**Date:** 2026-09-11 (Asia/Dubai)  
**Applies to:** `PVDAQ2107_EXTERNAL_TRANSFER_FROZEN_v1`  
**Scientific protocol status:** unchanged  
**Outcome status at amendment:** no reconstruction metric, ranking metric, method winner, or contribution result from PVDAQ 2107 had been inspected or accepted when these fixes were committed.

## 1. Source-schema trigger
The first automated run stopped inside the source-schema gate before analysis because the implementation used the strict selector `inv_\d+_ac_power_inv_` and therefore found 23 rather than the protocol-expected 24 inverter AC-power channels.

### Header-only inspection
A separate header-only workflow inspected the public CSV schema without opening outcome values. The current public file has 120 columns and contains all 24 inverter AC-power channels. Inverter 15 is labelled:

`inv_15_ac_power_iinv_149653`

whereas the other channels follow the usual `..._ac_power_inv_...` form. Thus the 23-channel count was an implementation/schema-label mismatch, not missing inverter data.

Header-only audit trail:
- schema workflow run: `34621433908`
- schema artifact: `pvdaq2107-schema-inventory`
- schema artifact ZIP SHA-256: `b9df9c9192f2edbff49cd22d39931a5f198a202808049a186ab851b89cc1324b`

The first pre-outcome run was `34621182374`; Python terminated at channel selection before splitting, mask generation, model fitting, or metric calculation. Its workflow was initially displayed as successful because the shell pipeline lacked `pipefail`; no scientific result from that run exists.

### Schema amendment
Change only the AC-power channel selector from the strict suffix-dependent form to the schema-robust form:

`^inv_\d+_ac_power_`

Then parse and sort by the inverter number and still require exactly 24 distinct inverter AC-power channels. Record the exact selected source-column names in the source inventory. No values are derived, renamed, or imputed to manufacture the 24th channel.

## 2. Workflow-QA correction
Enable shell `pipefail` and route stderr through `tee` so that any future Python failure makes the GitHub Actions job fail visibly while retaining the diagnostic log.

The next run (`34621705112`) then failed correctly before analysis because the schema adapter attempted a package-style import that is not valid when the script is executed directly. The adapter was changed to load the frozen core by its explicit file path with `importlib`. This is execution plumbing only.

## 3. Pre-outcome protocol-conformance audit
Before inspecting or accepting any PVDAQ outcome, a static comparison of the analysis code against the frozen protocol identified one further implementation mismatch: the first training-example generator cycled equally over regimes at the *mask* level, so regimes with larger breadth×duration produced more masked cells. The frozen protocol instead requires the target training and validation **masked cells** to be balanced across the 12 breadth-duration regimes as closely as possible.

The adapter therefore replaces only the training/validation example generator with a quota-based version that assigns approximately equal masked-cell quotas to each frozen regime and records both quota and realized cell counts. The test-mask generator, test masks, endpoints, method definitions, and all scientific stop rules are unchanged.

The same pre-outcome audit also makes the already-frozen time-handling requirement machine-readable: PVDAQ metadata use `PST8PDT`; published timestamp labels are retained as local labels without UTC conversion, exact duplicate labels are conservatively excluded by the frozen core, and mask continuity is enforced at the inferred native cadence.

## 4. What is NOT changed
No scientific design choice changes. In particular, the following remain frozen:
- the external-transfer question;
- 24 inverter-level AC-power channels;
- chronological 60/20/20 split;
- training-only 99.5th-percentile normalization;
- breadths 1/2/4/8 and gap lengths 1/3/12 samples;
- mask admission rules and random seed 2107;
- the seven comparator families;
- validation-only tuning;
- point, normalized gap-energy, Spearman, and Top-1 endpoints;
- winner-set tolerance;
- bootstrap and robustness plan;
- stop/downgrade rules; and
- the main-paper contribution gate.

These corrections are pre-outcome schema/execution/protocol-conformance fixes, not outcome-driven methodological revisions.
