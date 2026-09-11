# Use-Oriented PV Reconstruction

Companion repository for the conference manuscript **Use-Oriented Evaluation of Missing Multi-String PV Data Reconstruction: Point Recovery, Gap-Energy Preservation, and String Ranking**.

## Research question
When photovoltaic measurements are missing, should reconstruction method selection depend on whether the reconstructed data will be used for point-power recovery, gap-energy estimation, or comparative channel ranking?

## Qatar primary result
The Qatar analysis found different aggregate preferred methods for the three downstream uses: Masked Context for point recovery, Correlation Summary for gap energy, and Linear Interpolation for ranking. The transferable contribution is the **use-oriented evaluation principle**, not the Qatar-specific method ordering or error magnitude.

The stable-stage Qatar archive contains **45 string-level missing runs** corresponding to **35 distinct simultaneous missing-data episodes**. These are different counting units.

## Independent NREL/OEDI transfer
The prespecified external-transfer analysis on **NREL/OEDI PVDAQ system 2107** is complete. It uses 24 inverter AC-power channels, a local chronological 60/20/20 split, and 240 test masks across 12 locally defined breadth-duration regimes. No Qatar fitted model, normalization, threshold, or winner identity is transferred.

Aggregate PVDAQ2107 preferences again differ by downstream use:
- **Point recovery:** Iterative SVD, macro MAE 0.01913 p.u.
- **Gap energy:** Iterative SVD, median absolute error 0.599%.
- **Ranking:** Linear Interpolation, mean Spearman 0.820 and Top-1 0.803.

All prespecified stop rules pass. The same SVD/Linear task split remains under one-mask-per-day and high-output-removal checks; leave-one-inverter-out keeps the energy and ranking winners in 24/24 exclusions and the point winner in 22/24.

**Interpretation:** the independent test supports transfer of the use-oriented evaluation principle, not replication of the Qatar winner identities.

Primary public-data citation:

> Deline, C., Perry, K., Deceglie, M., Muller, M., Sekulic, W., & Jordan, D. (2021). *Photovoltaic Data Acquisition (PVDAQ) Public Datasets*. NREL / Open Energy Data Initiative. DOI: 10.25984/1846021.

Key persistent outputs are under `results/pvdaq2107/`. The successful external workflow was GitHub Actions run `34622092767`; original Actions artifact digest: `sha256:f354dfa400ab2755e08c0c8a6cc8dbf60f6035b0c1e948c6697e964321da6b0c`.

## Repository policy
- Qatar source telemetry is owner-controlled and is **not redistributed here**.
- Public external datasets are referenced by DOI/source and downloaded from their authoritative repositories.
- Reconstructed values remain analytical substitutes, not measurements.
- External tests evaluate transfer of the **scientific principle**, not forced replication of a Qatar winner.

## Structure
- `analysis/` external-transfer and reproducibility code
- `config/` frozen analysis settings
- `protocols/` frozen protocol and pre-outcome schema amendment
- `results/` persistent public result summaries and ledgers
- `external_data/` public-source boundaries and acquisition instructions
- `restricted_data/` Qatar-data access boundary

## Status
Paper 1 AC3 candidate: Qatar scientific results retained; independent PVDAQ2107 transfer added after contribution-first review.
