# PVDAQ2107 later temporal selector holdout — frozen 2026-09-12

## Status

This protocol is frozen before inspecting outcomes from the later non-overlapping PVDAQ2107 extension period. Historical 2018–2023 benchmark outcomes were already known before this protocol, so this is **not** a preregistration of the original study. It is a new temporal holdout test of a selector rule fixed from the earlier training/validation lineage.

## Fixed question

Does the validation-selected use-specific rule retain practical value on later PVDAQ2107 data that do not overlap the earlier benchmark or the 2024 increment used only to define the temporal cutoff?

## Fixed earlier selector

From the accepted schema-fixed 2018–2023 implementation and its regenerated validation masks:

- point-recovery method: **Iterative SVD**, rank = 2;
- gap-energy method: **Iterative SVD**, rank = 2;
- ranking method: **Linear Interpolation**.

The MAE-only policy therefore uses Iterative SVD for all downstream uses. The use-specific policy differs only for the ranking use.

No later data may alter these choices, the SVD rank, normalization, mask rules, endpoints, or stop rules.

## Source objects

Official OEDI PVDAQ2107 source objects:

- baseline electrical history: `2107_electrical_data.csv`, expected SHA-256 `c6d8402ee90ffbeb22cd32e5c371b66dbd0b3e5accaf5f4d83c4988fd91d74d8`;
- 2024 increment: `2107_electrical_data_2024.csv`, expected SHA-256 `bb2e9f7495e471503daa2c4b4ae9aa053ca4c779d63665afb1c2270daaa243a5`;
- 2025 object: `2107_electrical_data_2025.csv`, expected SHA-256 `f1c93d2124b6d7e20a3b77206cb104b99586a8a3d1c70615cc0737e7f6100d1d`.

## Non-overlap rule

The 2024 and 2025 objects overlap in calendar time. They will **not** be concatenated. The 2024 object is used only to establish its latest timestamp. The temporal-holdout candidate is the subset of the 2025 object with timestamps strictly later than the maximum timestamp present in the 2024 object.

If no such rows exist, STOP. If timestamp parsing, cadence, or 24-channel AC-power schema cannot be reconciled without post-outcome choices, STOP.

## Preprocessing lock

- Use the accepted schema-fixed loader.
- Use the original 2018–2023 train split and the original training-only 0.995 quantile normalization scales; do not refit normalization on later data.
- Expected electrical cadence is 5 minutes; infer and report the actual candidate cadence before masks.
- Admit complete calendar days using the same source-level completeness rule as the external baseline.
- No later environment/context files are needed because only Iterative SVD and Linear Interpolation are evaluated in this holdout.

## Mask lock

- breadths: 1, 2, 4, 8;
- gap lengths: 1, 3, 12 samples;
- 20 masks per breadth × length regime when feasible;
- deterministic seed: `42107`;
- same 12-sample boundary buffer, minimum unhidden-peer fraction 0.75, and normalized output range [0.05, 0.95];
- ranking endpoints only for breadth >= 2;
- identical masks for both evaluated methods.

## Endpoints

- point MAE and RMSE;
- pooled absolute gap-energy percentage where true pooled energy is nonzero;
- hidden-channel/sample-wise Spearman;
- Top-1 accuracy.

Zero-true-energy gaps remain evaluable for absolute error but do not receive an invented relative percentage.

## Primary policy contrast

For ranking, compare fixed earlier MAE-only policy (Iterative SVD) against fixed earlier use-specific policy (Linear Interpolation) on the same later masks.

Report:

- aggregate Spearman difference = Linear minus SVD;
- aggregate Top-1 difference = Linear minus SVD;
- day-cluster bootstrap 95% intervals for these differences.

Point and energy policies are identical by construction and are reported only as a check, not as a claimed gain.

## Stop rules

STOP without a policy-benefit claim if any of the following holds:

- fewer than 120 total later masks;
- fewer than 8 masks in any retained regime;
- fewer than 6 ranking regimes with at least 8 masks;
- fewer than 0.8 nonconstant hidden-ranking timestamp fraction in the ranking evaluation;
- source hashes do not match the locked objects;
- non-overlap or time handling cannot be resolved using the rules above.

A null or negative later ranking gain is an admissible result and must not trigger retuning.

## Manuscript gate

Open a new Paper 1 main-manuscript revision only if this later holdout adds decision-relevant information beyond AC3. Otherwise retain AC3 main and place the audit in Supplement/GitHub only.