# Paper 1 — PVDAQ 2107 External-Transfer Protocol (FROZEN v1)

**Freeze date:** 2026-09-11 (Asia/Dubai)  
**Status:** Frozen before opening the PVDAQ 2107 outcome files for the present study.  
**Purpose:** External test of the *use-oriented reconstruction principle*, not replication of the Qatar method winners.

## 1. Prespecified question
Does an independent, public, multi-inverter PV archive show that reconstruction-method preference depends on the downstream use (point recovery, gap-energy preservation, or relative channel ranking), or does it define a clear boundary where that Qatar finding does not transfer?

The external test is deliberately not: “Does Masked Context win again?” Qatar-specific winners and error magnitudes are not transport targets.

## 2. External evidence and measurement-hierarchy boundary
- Dataset: NREL PVDAQ system 2107 (Farm Solar Array, Arbuckle, California), public OEDI/Solar Data Prize data.
- Primary signal: the 24 inverter-level AC-power channels at their native cadence.
- This is a measurement-hierarchy transfer: Qatar used string-level DC power; PVDAQ 2107 uses inverter-level AC power. The hierarchy difference is retained and reported, not hidden.
- Public environmental/irradiance channels are inventoried. They are not required for the primary common-support test; a weather-assisted sensitivity may use POA, ambient temperature, and wind only if their temporal support is adequate and their channel definitions are unambiguous.
- No Qatar thresholds, normalizers, fitted parameters, or model iterations are transferred.

## 3. Source lock and provenance
Record for every downloaded object: canonical public key/URL, download timestamp, byte size, SHA-256, first/last timestamp, row count, and column count. Preserve raw files read-only. If 2024 increment files are used, record them separately from the 2017–2023 prize files.

## 4. Time handling and chronology
- Keep source timestamps in their documented local-time convention; record DST handling explicitly.
- Build a single ordered date list after admission/QC.
- Chronological split by admitted dates: earliest 60% train, next 20% validation, final 20% test.
- All scaling, correlation weights, hyperparameter choices, and learned models are fit using train/validation only. Test masks are never used for tuning.

## 5. Local normalization
For each inverter independently, estimate a robust capacity scale from the **training period only** as the 99.5th percentile of positive AC power after basic finite-value screening. Divide that inverter’s AC power by this fixed training-derived scale. Do not rescale the test period from test observations.

## 6. Candidate-mask admission and common support
A primary mask is eligible only when:
1. all ground-truth cells to be hidden are finite;
2. the immediately preceding and following boundary samples for every hidden inverter are finite;
3. at least 75% of the non-hidden inverter channels are finite at every masked timestamp;
4. the site-wide median normalized observed power at the masked timestamps lies in [0.05, 0.95], to avoid night/near-zero records and obvious upper-plateau clipping in the primary test;
5. the full mask lies within one local calendar day; and
6. no test mask overlaps another test mask. A one-hour exclusion buffer is applied between primary masks on the same date.

Environmental variables are not allowed to determine primary mask eligibility. Weather-assisted sensitivity uses the subset with finite aligned environmental context.

## 7. Prespecified artificial-loss regimes
Use the native 5-min sampling unit rather than copying Qatar minute counts.
- Missing breadth: 1, 2, 4, or 8 inverters.
- Gap length: 1, 3, or 12 samples (nominally 5, 15, or 60 min at the expected native cadence).
- Primary grid: 12 breadth × duration regimes.
- Target: 20 deterministic masks per regime (240 total), sampled from test dates with random seed 2107.
- Inverter inclusion is balanced as closely as combinatorially possible within each regime.
- Ranking endpoints are evaluated only for breadth >= 2 (9 regimes; target 180 masks).

If the source cadence differs locally, gap length remains defined in samples; actual elapsed duration is reported.

## 8. Frozen comparator family
Evaluate the same method families where mathematically compatible:
1. Linear interpolation from pre/post-gap boundaries.
2. Peer median; if every inverter in the evaluated set is hidden, use boundary interpolation.
3. Iterative low-rank SVD completion.
4. Ridge context reconstruction.
5. Distance-weighted context KNN.
6. Masked Context gradient-boosted regression.
7. Correlation Summary: the same Masked Context family plus a training-only positive-correlation summary feature.

No Transformer, GNN, diffusion model, or new fuzzy/AI method is added to improve the external result.

### Context features for learned methods
Primary features are constructed only from public 2107 electrical data and time descriptors: contemporaneously observed inverter powers, target-inverter identity, cyclic time, pre/post-gap target boundaries and their linear bridge, missing breadth, gap length in samples, and within-gap position. Missing peer values remain explicitly missing for models that support them; for ridge/KNN, training-only feature medians plus missingness indicators are used.

Correlation Summary uses training-only Pearson correlations r_ij and weights max(r_ij,0)^2; when the denominator is zero the summary feature is unavailable/missing rather than invented.

A secondary weather-assisted sensitivity may add POA, ambient temperature, and wind after alignment, but it cannot replace the primary electrical-only result.

## 9. Local tuning (validation only)
- SVD rank candidates: {1, 2, 4, 8}.
- Ridge alpha candidates: {0.001, 0.01, 0.1, 1, 10}.
- KNN k candidates: {3, 5, 10, 20, 50}; use a deterministic training cap of 30,000 masked examples if memory/runtime requires it, with the cap declared before model fitting.
- LightGBM: absolute-error objective, maximum 1,000 trees, validation early stopping with patience 50; all other settings and seeds are recorded before fitting.
- Select hyperparameters by validation macro point MAE only; do not tune separately for energy or ranking, so downstream comparisons remain genuine evaluations rather than endpoint-specific optimization.

## 10. Training-mask generation
Generate masked training/validation examples only inside their respective chronological partitions and from the same breadth × sample-length family. Target 100,000 masked training cells and 20,000 masked validation cells, balanced across regimes as closely as possible. Seed all stochastic operations and record the seeds.

## 11. Frozen endpoints
For every common-support test mask and method:
- **Point recovery:** mask MAE and RMSE on normalized hidden cells.
- **Gap energy:** absolute percentage error in the summed hidden-channel gap energy; also retain signed normalized energy error.
- **Ranking:** minute-wise Spearman correlation among hidden inverters and Top-1 agreement for the highest hidden inverter; breadth-one is undefined.

Macro metrics weight masks equally. Micro metrics are secondary. Ranking ties use the lowest fixed inverter index, mirroring the Qatar audit rule.

## 12. Primary transfer diagnostic
For each mask and each breadth-duration regime, define a winner set containing methods tied within numerical tolerance 1e-12. Quantify whether the point-MAE winner set intersects the winner set for:
- gap-energy error;
- hidden-inverter Spearman; and
- hidden-inverter Top-1.

Report aggregate preferred method(s) for each endpoint, mask-level agreement, and regime-level agreement. The scientific transfer claim concerns **non-interchangeability across downstream uses**, not identity of the winning algorithm across sites.

## 13. Uncertainty / robustness
Use 2,000 bootstrap resamples clustered by local calendar date for agreement fractions and paired mask-level differences. Treat these as within-archive descriptive uncertainty, not confidence intervals for all PV sites.

Mandatory sensitivities:
- exclude each inverter one at a time from scoring;
- compare all admitted masks with a non-overlapping-day subset;
- weather-assisted context sensitivity if adequate common support exists;
- report results with high-output [0.80, 0.95] normalized-power masks removed to check clipping dependence.

## 14. Stop / downgrade rules
Downgrade the external test to descriptive evidence and do **not** add a main-paper result if any of the following occurs:
- fewer than 120 total common-support primary masks are constructible;
- any primary regime has fewer than 8 admitted masks;
- fewer than 6 of the 9 multi-inverter regimes support >=8 ranking masks with non-constant truth ranks for at least 80% of masked timestamps;
- source schema/cadence prevents defensible channel alignment;
- a comparator cannot be implemented without changing its mathematical family after outcomes are known.

An unavailable method may be omitted from the common method set only with an explicit pre-outcome implementation failure log; it is never replaced post hoc by a more favorable method.

## 15. Contribution decision after rerun
A main-paper mini-table/statement is warranted only if the external test yields either:
A. task-dependent method preference / incomplete agreement across point, energy, and ranking; or
B. a clear, reproducible boundary explaining where the Qatar use-oriented finding does not transfer.

Otherwise the external result remains in Supplement/GitHub as a null/limited-transfer audit. The Qatar numerical results and winners remain unchanged.

## 16. Frozen deliverables
- raw-source manifest with SHA-256;
- data-inventory/QC report;
- exact split and mask ledgers;
- config/environment lock;
- per-mask and aggregate results;
- contribution audit and main-paper admission decision;
- reproducibility script(s), tests, and results_reference artifacts for the public GitHub repository.
