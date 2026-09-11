# External data record — NREL/OEDI PVDAQ 2107

Planned independent transfer dataset: **PVDAQ system 2107**.

Authoritative dataset:
- NREL/OEDI PVDAQ Public Datasets
- DOI: `10.25984/1846021`
- Landing page: https://data.openei.org/submissions/4568
- License: CC BY 4.0

The local project archive already contains a verified intake of system 2107 with multi-inverter DC/AC channels, plane-of-array irradiance, meteorological channels, and system metadata. Public data will not be copied into this repository unless redistribution and size are appropriate; authoritative download instructions and hashes will be recorded instead.

## Prespecified transfer question
Does the preferred reconstruction method remain dependent on downstream use (point recovery, gap energy, comparative channel ranking) in an independent multi-inverter PV plant?

## Guardrails
1. Freeze the external analysis specification before inspecting headline outcomes.
2. Do not retune the Qatar result using PVDAQ test outcomes.
3. Use time-based splits and group-aware masking.
4. Respect the native external sampling interval; do not pretend that 15-minute observations are 1-minute data.
5. Report external winners separately from Qatar winners.
6. A different external winner does not invalidate the Qatar result; the primary transfer estimand is **objective dependence**, not exact algorithm identity.
