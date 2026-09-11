#!/usr/bin/env python3
"""Pre-outcome implementation adapter for the frozen PVDAQ2107 analysis.

Scientific logic is loaded unchanged from run_pvdaq2107_transfer.py.
This adapter implements two protocol-fidelity fixes identified before any
outcome was accepted: (1) robust selection of the documented inverter-15
AC-power header typo/variant, while still requiring IDs 1..24 exactly; and
(2) masked-cell balancing across the 12 frozen breadth-duration regimes for
training and validation example generation.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_CORE_PATH = Path(__file__).with_name('run_pvdaq2107_transfer.py')
_SPEC = importlib.util.spec_from_file_location('pvdaq2107_frozen_core', _CORE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f'Cannot load frozen core analysis from {_CORE_PATH}')
core = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = core
_SPEC.loader.exec_module(core)


def _arg_value(flag):
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _output_dir():
    value = _arg_value('--output-dir')
    if value is None:
        return None
    p = Path(value)
    p.mkdir(parents=True, exist_ok=True)
    return p


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

    out = _output_dir()
    if out is not None:
        with open(out / 'selected_ac_power_columns.json', 'w', encoding='utf-8') as f:
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
        with open(out / 'source_time_handling.json', 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'metadata_timezone_code': 'PST8PDT',
                    'handling': 'Published timestamp labels are retained in source order as local naive labels; no UTC conversion is applied.',
                    'duplicate_policy': 'If exact timestamp labels are duplicated, all duplicated labels are conservatively excluded by the frozen core before splitting/masking.',
                    'cadence_policy': 'The modal positive source interval is inferred and continuity is required at every admitted mask.'
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


def random_training_cells_balanced(norm_df, allowed_dates, breadths, lengths,
                                   target_cells, seed, min_peer_frac, out_range,
                                   cadence_min, corr, prefix):
    """Generate approximately equal masked-cell quotas per frozen regime."""
    rng = np.random.default_rng(seed)
    arr = norm_df.to_numpy(float)
    idx = norm_df.index
    pos_by_date = core.date_positions(idx, allowed_dates)
    dkeys = list(pos_by_date)
    if not dkeys:
        raise RuntimeError('No admitted dates available for balanced training-mask generation')

    regimes = [(int(b), int(L)) for b in breadths for L in lengths]
    base = target_cells // len(regimes)
    rem = target_cells % len(regimes)
    quotas = {reg: base + (1 if i < rem else 0) for i, reg in enumerate(regimes)}
    realized = {reg: 0 for reg in regimes}

    X, Xc, y = [], [], []
    for ri, (b, L) in enumerate(regimes):
        quota = quotas[(b, L)]
        attempts = 0
        max_attempts = max(20000, quota * 50)
        maskno = 0
        while realized[(b, L)] < quota and attempts < max_attempts:
            attempts += 1
            d = dkeys[int(rng.integers(0, len(dkeys)))]
            pos = pos_by_date[d]
            if len(pos) < L + 2:
                continue
            start = int(pos[int(rng.integers(1, max(2, len(pos) - L - 1)))])
            hidden = tuple(sorted(rng.choice(arr.shape[1], size=b, replace=False).tolist()))
            if not core.mask_valid(arr, idx, start, L, hidden, cadence_min, out_range, min_peer_frac):
                continue
            maskno += 1
            m = core.Mask(f'{prefix}_b{b}_l{L}_{maskno}', str(idx[start]), str(d), start, L, b, hidden)
            xb, yb, _ = core.feature_rows(norm_df, m, corr, False)
            xc, _, _ = core.feature_rows(norm_df, m, corr, True)
            need = quota - realized[(b, L)]
            if len(yb) > need:
                take = np.arange(len(yb))
                rng.shuffle(take)
                take = take[:need]
                xb = xb[take]
                xc = xc[take]
                yb = yb[take]
            X.append(xb)
            Xc.append(xc)
            y.append(yb)
            realized[(b, L)] += len(yb)
        if realized[(b, L)] < quota:
            raise RuntimeError(
                f'Balanced generation shortfall for breadth={b}, length={L}: '
                f'{realized[(b, L)]}/{quota} cells after {attempts} attempts'
            )

    out = _output_dir()
    if out is not None:
        with open(out / f'{prefix}_cell_balance.json', 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'target_cells': int(target_cells),
                    'regime_quotas': {f'b{b}_l{L}': int(quotas[(b, L)]) for b, L in regimes},
                    'realized_cells': {f'b{b}_l{L}': int(realized[(b, L)]) for b, L in regimes},
                    'total_realized': int(sum(realized.values()))
                },
                f,
                indent=2,
            )

    return np.vstack(X), np.vstack(Xc), np.concatenate(y)


core.load_ac_power = load_ac_power_schemafixed
core.random_training_cells = random_training_cells_balanced

if __name__ == '__main__':
    core.main()
