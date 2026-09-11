#!/usr/bin/env python3
"""Outcome-free PVDAQ2107 preflight for the frozen external-transfer protocol.

Checks source schema/provenance, chronology, normalization, mask feasibility,
and ranking-truth support only. It does NOT fit or score any reconstruction
method and therefore does not reveal reconstruction outcomes.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CORE_PATH = Path(__file__).with_name('run_pvdaq2107_transfer.py')
SPEC = importlib.util.spec_from_file_location('pvdaq2107_core_preflight', CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


def load_schemafixed(csv_path, expected_n=24):
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    ts_col = header[0]
    ac = sorted(
        [c for c in header if re.search(r'^inv_\d+_ac_power_', c)],
        key=lambda c: int(re.search(r'^inv_(\d+)_', c).group(1)),
    )
    ids = [int(re.search(r'^inv_(\d+)_', c).group(1)) for c in ac]
    if ids != list(range(1, expected_n + 1)):
        raise RuntimeError(f'Expected inverter IDs 1..{expected_n}; found {ids}')
    df = pd.read_csv(csv_path, usecols=[ts_col] + ac, parse_dates=[ts_col], low_memory=False)
    df = df.rename(columns={ts_col: 'measured_on'}).set_index('measured_on').sort_index()
    dup = df.index.duplicated(keep=False)
    duplicate_rows = int(dup.sum())
    if duplicate_rows:
        df = df.loc[~dup]
    for c in ac:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df, ac, duplicate_rows, header


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--raw-dir', default='raw')
    args = ap.parse_args()
    cfg = json.load(open(args.config))
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    raw = Path(args.raw_dir); raw.mkdir(parents=True, exist_ok=True)
    src = raw / '2107_electrical_data.csv'
    if not src.exists():
        core.download(cfg['source']['electrical_url'], src)
    df, cols, dups, header = load_schemafixed(src, cfg['source']['expected_inverters'])
    cadence = core.infer_cadence_minutes(df.index)
    dates = core.admitted_dates_raw(df)
    trd, vad, ted = core.split_dates(dates, cfg['split_fractions'])
    scales = core.robust_scales(df, trd, cfg['normalization_quantile'])
    norm = df.div(scales, axis=1)
    val_masks, val_counts = core.generate_masks(
        norm, vad, cfg['breadths'], cfg['gap_samples'], cfg['validation_masks_per_regime'],
        cfg['seed'] + 10, cfg['mask_buffer_samples'], cfg['min_unhidden_peer_fraction'],
        cfg['primary_output_range'], cadence, 'val')
    test_masks, test_counts = core.generate_masks(
        norm, ted, cfg['breadths'], cfg['gap_samples'], cfg['test_masks_per_regime'],
        cfg['seed'] + 20, cfg['mask_buffer_samples'], cfg['min_unhidden_peer_fraction'],
        cfg['primary_output_range'], cadence, 'test')

    arr = norm.to_numpy(float)
    rank_rows = []
    for m in test_masks:
        if m.breadth < 2:
            continue
        truth = arr[m.start_pos:m.start_pos + m.length][:, list(m.hidden)]
        frac = float(np.mean(np.ptp(truth, axis=1) > 1e-12))
        rank_rows.append({'mask_id': m.mask_id, 'breadth': m.breadth, 'length': m.length,
                          'nonconstant_truth_rank_fraction': frac})
    rr = pd.DataFrame(rank_rows)
    sr = cfg['stop_rules']
    ranking_good = 0
    if not rr.empty:
        for (b, L), g in rr.groupby(['breadth', 'length']):
            if (g.nonconstant_truth_rank_fraction >= sr['min_nonconstant_rank_timestamp_fraction']).sum() >= sr['min_ranking_masks_per_regime']:
                ranking_good += 1

    reasons = []
    if len(test_masks) < sr['min_total_test_masks']:
        reasons.append(f'total_test_masks={len(test_masks)} < {sr["min_total_test_masks"]}')
    if any(v < sr['min_masks_per_regime'] for v in test_counts.values()):
        reasons.append('one_or_more_regimes_below_minimum_masks')
    if ranking_good < sr['min_ranking_regimes']:
        reasons.append(f'ranking_good_regimes={ranking_good} < {sr["min_ranking_regimes"]}')

    result = {
        'source_sha256': core.sha256_file(src),
        'source_bytes': src.stat().st_size,
        'source_rows_after_duplicate_exclusion': len(df),
        'raw_column_count_including_timestamp': len(header),
        'ac_power_channel_count': len(cols),
        'selected_columns': cols,
        'duplicate_timestamp_rows_excluded': dups,
        'first_timestamp': str(df.index.min()),
        'last_timestamp': str(df.index.max()),
        'inferred_cadence_minutes': cadence,
        'admitted_dates': len(dates),
        'train_dates': len(trd),
        'validation_dates': len(vad),
        'test_dates': len(ted),
        'train_range': [str(trd[0].date()), str(trd[-1].date())],
        'validation_range': [str(vad[0].date()), str(vad[-1].date())],
        'test_range': [str(ted[0].date()), str(ted[-1].date())],
        'validation_mask_counts': val_counts,
        'test_mask_counts': test_counts,
        'total_validation_masks': len(val_masks),
        'total_test_masks': len(test_masks),
        'ranking_good_regimes': ranking_good,
        'stop_rules_pass_before_method_scoring': not reasons,
        'stop_reasons': reasons,
    }
    json.dump(result, open(out / 'preflight.json', 'w'), indent=2)
    pd.DataFrame([core.asdict(m) for m in test_masks]).to_csv(out / 'test_mask_ledger.csv', index=False)
    rr.to_csv(out / 'ranking_truth_support.csv', index=False)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
