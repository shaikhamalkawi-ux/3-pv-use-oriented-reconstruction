# PVDAQ 2107 — Pre-Outcome Schema Amendment

**Date:** 2026-09-11 (Asia/Dubai)  
**Applies to:** `PVDAQ2107_EXTERNAL_TRANSFER_FROZEN_v1`  
**Scientific protocol status:** unchanged  
**Outcome status at amendment:** no reconstruction metric, ranking metric, method winner, or contribution result had been computed.

## Trigger
The first automated run stopped inside the source-schema gate before analysis because the implementation used the strict selector `inv_\d+_ac_power_inv_` and therefore found 23 rather than the protocol-expected 24 inverter AC-power channels.

## Header-only inspection
A separate header-only workflow inspected the public CSV schema without opening outcome values. The current public file has 120 columns and contains all 24 inverter AC-power channels. Inverter 15 is labelled:

`inv_15_ac_power_iinv_149653`

whereas the other channels follow the usual `..._ac_power_inv_...` form. Thus the 23-channel count was an implementation/schema-label mismatch, not missing inverter data.

Header-only audit trail:
- schema workflow run: `34621433908`
- schema artifact: `pvdaq2107-schema-inventory`
- schema artifact ZIP SHA-256: `b9df9c9192f2edbff49cd22d39931a5f198a202808049a186ab851b89cc1324b`

The failed pre-outcome run was `34621182374`; it terminated at channel selection before splitting, mask generation, model fitting, or metric calculation.

## Amendment
Change only the AC-power channel selector from the strict suffix-dependent form to the schema-robust form:

`^inv_\d+_ac_power_`

Then parse and sort by the inverter number and still require exactly 24 distinct inverter AC-power channels. Record the exact selected source-column names in the source inventory.

## Workflow QA amendment
Enable shell `pipefail` and route stderr through `tee` so that any future Python failure makes the GitHub Actions job fail visibly while retaining the diagnostic log.

## What is NOT changed
No scientific design choice changes. In particular, the following remain frozen:
- the external-transfer question;
- 24 inverter-level AC-power channels;
- chronological 60/20/20 split;
- training-only 99.5th-percentile normalization;
- breadths 1/2/4/8 and gap lengths 1/3/12 samples;
- mask admission rules and random seed 2107;
- the seven comparator families;
- validation-only tuning;
- point, energy, Spearman, and Top-1 endpoints;
- winner-set tolerance;
- bootstrap and robustness plan;
- stop/downgrade rules; and
- the main-paper contribution gate.

This amendment is therefore a pre-outcome source-schema correction, not an outcome-driven methodological revision.
