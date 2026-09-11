#!/usr/bin/env python3
"""Pre-outcome schema adapter for the frozen PVDAQ2107 analysis.

Scientific logic is imported unchanged from run_pvdaq2107_transfer.py.
This adapter only accepts the documented current header typo/variant by
selecting inverter AC-power columns with ^inv_\\d+_ac_power_ and still
requires exactly inverter indices 1..24.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

import analysis.run_pvdaq2107_transfer as core


def _arg_value(flag):
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def load_ac_power_schemafixed(csv_path, expected_n=24):
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    ts_col = header[0]
    ac = [c for c in header if re.search(r'^inv_\d+_ac_power_', c)]
    ac = sorted(ac, key=lambda c: int(re.search(r'^inv_(\d+)_', c).group(1)))
    ids = [int(re.search(r'^inv_(\d+)_', c).group(1)) for c in ac]
    expected_ids = list(range(1, expected_n + 1))
    if len(ac) != expected_n or ids != expected_ids:
        raise RuntimeError(
            f'Expected exactly inverter AC-power IDs {expected_ids}; '
            f'found IDs {ids} in {len(ac)} channels'
        )

    out_dir = _arg_value('--output-dir')
    if out_dir:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        with open(p / 'selected_ac_power_columns.json', 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'selector': r'^inv_\d+_ac_power_',
                    'expected_count': expected_n,
                    'inverter_ids': ids,
                    'columns': ac,
                    'schema_note': 'Inverter 15 is currently labelled inv_15_ac_power_iinv_149653; no value derivation or renaming is performed.'
                },
                f,
                indent=2,
            )

    df = pd.read_csv(csv_path, usecols=[ts_col] + ac, parse_dates=[ts_col], low_memory=False)
    df = df.rename(columns={ts_col: 'measured_on'}).set_index('measured_on').sort_index()
    dup = df.index.duplicated(keep=False)
    duplicate_rows = int(dup.sum())
    if duplicate_rows:
        df = df.loc[~dup]
    for c in ac:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df, ac, duplicate_rows, header


core.load_ac_power = load_ac_power_schemafixed

if __name__ == '__main__':
    core.main()
