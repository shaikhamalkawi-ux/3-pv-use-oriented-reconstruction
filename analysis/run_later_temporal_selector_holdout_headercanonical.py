#!/usr/bin/env python3
"""Pre-outcome header-canonicalization adapter for the frozen later holdout.

The annual PVDAQ objects use different literal AC-power header suffixes while
preserving the same inverter identities. The accepted schema adapter already
requires exactly inverter IDs 1..24 in sorted order. This wrapper changes only
the dataframe labels after that gate to canonical inverter-ID labels so that
training-only normalization and later-period evaluation align by physical
inverter identity rather than by source header spelling.

No split, mask, method, metric, seed, selector, threshold, or outcome-dependent
choice is changed here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import run_later_temporal_selector_holdout as frozen

_ORIGINAL_LOAD = frozen.base.load_ac_power


def load_ac_power_headercanonical(csv_path, expected_n=24):
    df, cols, duplicate_rows, header = _ORIGINAL_LOAD(csv_path, expected_n)
    if df.shape[1] != expected_n:
        raise RuntimeError(
            f"Header-canonicalization gate expected {expected_n} admitted AC-power columns; "
            f"received {df.shape[1]}"
        )

    canonical = [f"inv_{i:02d}" for i in range(1, expected_n + 1)]
    mapping = dict(zip(cols, canonical))
    out = df.copy()
    out.columns = canonical

    audit_dir = frozen.OUT
    audit_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(csv_path).name.replace(".csv", "")
    with open(audit_dir / f"header_canonicalization_{source_name}.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": Path(csv_path).name,
                "rule": "accepted sorted inverter IDs 1..24 mapped positionally to canonical inv_01..inv_24 labels",
                "original_columns": cols,
                "canonical_columns": canonical,
                "mapping": mapping,
                "duplicate_rows_removed_by_accepted_loader": int(duplicate_rows),
                "scientific_change": "none; labels only, after exact inverter-ID admission gate",
            },
            f,
            indent=2,
        )
    return out, canonical, duplicate_rows, header


frozen.base.load_ac_power = load_ac_power_headercanonical

if __name__ == "__main__":
    sys.argv[0] = "run_later_temporal_selector_holdout_headercanonical.py"
    frozen.main()
