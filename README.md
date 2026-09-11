# Use-Oriented PV Reconstruction

Companion repository for the conference manuscript **Use-Oriented Evaluation of Missing Multi-String PV Data Reconstruction: Point Recovery, Gap-Energy Preservation, and String Ranking**.

## Research question
When photovoltaic measurements are missing, should the reconstruction method be selected differently depending on whether the reconstructed data will be used for point-power recovery, gap-energy estimation, or comparative channel ranking?

## Current Qatar result
The Qatar analysis found different aggregate preferred methods for the three downstream uses. The transferable contribution is the **use-oriented evaluation principle**, not the Qatar-specific method ordering or error magnitude.

## Independent public-data extension
A prespecified external transfer test is being prepared with **NREL/OEDI PVDAQ system 2107**. The external analysis will test whether downstream-use dependence persists in an independent multi-inverter PV plant. It will not be used to retune the Qatar analysis after inspecting the external outcome.

Primary public-data citation:

> Deline, C., Perry, K., Deceglie, M., Muller, M., Sekulic, W., & Jordan, D. (2021). *Photovoltaic Data Acquisition (PVDAQ) Public Datasets*. NREL / Open Energy Data Initiative. DOI: 10.25984/1846021.

## Repository policy
- Qatar source telemetry is owner-controlled and is **not redistributed here**.
- Public external datasets are referenced by DOI/source and should be downloaded from their authoritative repositories.
- Reconstructed values remain analytical substitutes, not measurements.
- External tests are intended to evaluate transfer of the **scientific principle**, not to force replication of the Qatar winner.

## Planned structure
- `src/` analysis code
- `configs/` frozen analysis settings
- `tests/` reproducibility checks
- `results/` public/reproducible result tables
- `supplement/` conference supplementary material
- `external_data/` source records and download instructions
- `restricted_data/` Qatar-data access boundary and required schema

## Status
Public research companion. Manuscript authorship/affiliations will be synchronized after collaborator confirmation.
