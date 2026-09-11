# PVDAQ 2107 External-Transfer Results

Protocol: `PVDAQ2107_EXTERNAL_TRANSFER_FROZEN_v1`  
Source SHA-256: `c6d8402ee90ffbeb22cd32e5c371b66dbd0b3e5accaf5f4d83c4988fd91d74d8`  
Cadence: 5 min  
Test masks: 240  
GitHub Actions run: `34622092767`  
Source commit: `25edab3607ea1fd83ac092ff3175295aac07d466`  
Original Actions artifact digest: `sha256:f354dfa400ab2755e08c0c8a6cc8dbf60f6035b0c1e948c6697e964321da6b0c`

## Aggregate metrics

| method | macro MAE | macro RMSE | median energy abs. error (%) | mean Spearman | mean Top-1 | masks |
|---|---:|---:|---:|---:|---:|---:|
| Context KNN | 0.0632380 | 0.0725400 | 7.9370 | 0.188692 | 0.403241 | 240 |
| Correlation Summary | 0.0207314 | 0.0281316 | 1.61347 | 0.603304 | 0.668519 | 240 |
| **Iterative SVD** | **0.0191304** | 0.0285523 | **0.598939** | 0.703929 | 0.676389 | 240 |
| **Linear Interpolation** | 0.0366049 | 0.0454601 | 1.11627 | **0.819895** | **0.803241** | 240 |
| Masked Context | 0.0199661 | **0.0274048** | 1.43462 | 0.614334 | 0.650926 | 240 |
| Peer Median | 0.0354822 | 0.0522366 | 1.43407 | NA | 0.214815 | 240 |
| Ridge Context | 0.0404100 | 0.0476023 | 3.36684 | 0.586579 | 0.642130 | 240 |

## Contribution decision

All prespecified stop rules pass. Nine multi-inverter regimes support ranking evaluation. Aggregate winners differ by downstream use: Iterative SVD is preferred for point MAE and gap-energy error, while Linear Interpolation is preferred for Spearman and Top-1 ranking. Regime-level disagreement is also present.

**Interpretation:** the external test supports transfer of the use-oriented evaluation principle, not transfer of the Qatar winner identities or error magnitudes.

## Day-cluster agreement

- Point vs. energy: 0.6034; 2,000-replicate descriptive interval 0.5436–0.6623.
- Point vs. Spearman: 0.6167; interval 0.5480–0.6911.
- Point vs. Top-1: 0.7611; interval 0.6957–0.8249.

## Sensitivity

The same SVD/Linear aggregate task split is retained under one-mask-per-calendar-day and high-output-removal checks. Leave-one-inverter-out preserves energy, Spearman, and Top-1 winner identities in 24/24 exclusions and the point winner in 22/24; the two point exceptions select Masked Context.

Raw Qatar telemetry is not redistributed in this repository. The public NREL/OEDI data are referenced by source/DOI and downloaded by the repository workflow.