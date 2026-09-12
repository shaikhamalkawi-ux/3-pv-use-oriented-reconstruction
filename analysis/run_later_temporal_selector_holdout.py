#!/usr/bin/env python3
from __future__ import annotations

import importlib.util, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT/'analysis'/'run_pvdaq2107_transfer_schemafixed.py'
spec=importlib.util.spec_from_file_location('later_selector_adapter',ADAPTER)
adapter=importlib.util.module_from_spec(spec); assert spec.loader is not None
sys.modules[spec.name]=adapter; spec.loader.exec_module(adapter)
base=adapter.core
CFG=ROOT/'config'/'pvdaq2107_frozen_config.json'
OUT=ROOT/'results'/'later_temporal_selector_holdout'
RAW=ROOT/'raw_later_selector'
OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)

EXPECTED={
 'baseline':'c6d8402ee90ffbeb22cd32e5c371b66dbd0b3e5accaf5f4d83c4988fd91d74d8',
 '2024':'bb2e9f7495e471503daa2c4b4ae9aa053ca4c779d63665afb1c2270daaa243a5',
 '2025':'f1c93d2124b6d7e20a3b77206cb104b99586a8a3d1c70615cc0737e7f6100d1d'}
URL_BASE='https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/data/'


def get(name,url,expected):
    p=RAW/name
    if not p.exists(): base.download(url,p)
    h=base.sha256_file(p)
    if h!=expected: raise RuntimeError(f'hash mismatch for {name}: {h}')
    return p,h


def metrics_for(norm,masks,svd_rank=2):
    arr=norm.to_numpy(float); rows=[]
    for m in masks:
        H=list(m.hidden); truth=arr[m.start_pos:m.start_pos+m.length][:,H]
        preds={'Iterative SVD':base.svd_complete_predict(norm,m,svd_rank),
               'Linear Interpolation':base.linear_predict(norm,m)}
        for method,pred in preds.items():
            met=base.evaluate_pred(truth,pred)
            rows.append({'mask_id':m.mask_id,'date':m.date,'breadth':m.breadth,'length':m.length,'method':method,**met})
    return pd.DataFrame(rows)


def aggregate(mm):
    return base.aggregate(mm)


def day_bootstrap(mm,reps=2000,seed=62107):
    rng=np.random.default_rng(seed); days=np.array(sorted(mm.date.unique())); byday={d:mm[mm.date.eq(d)] for d in days}
    vals={'spearman_gain':[],'top1_gain':[]}
    for _ in range(reps):
        pick=rng.choice(days,size=len(days),replace=True); x=pd.concat([byday[d] for d in pick],ignore_index=True); a=aggregate(x).set_index('method')
        if pd.notna(a.loc['Linear Interpolation','mean_spearman']) and pd.notna(a.loc['Iterative SVD','mean_spearman']): vals['spearman_gain'].append(float(a.loc['Linear Interpolation','mean_spearman']-a.loc['Iterative SVD','mean_spearman']))
        vals['top1_gain'].append(float(a.loc['Linear Interpolation','mean_top1']-a.loc['Iterative SVD','mean_top1']))
    return {k:{'n_boot':len(v),'median':float(np.median(v)),'ci95':[float(np.quantile(v,.025)),float(np.quantile(v,.975))]} for k,v in vals.items()}


def main():
    cfg=json.loads(CFG.read_text())
    pb,hb=get('2107_electrical_data.csv',cfg['source']['electrical_url'],EXPECTED['baseline'])
    p24,h24=get('2107_electrical_data_2024.csv',URL_BASE+'2107_electrical_data_2024.csv',EXPECTED['2024'])
    p25,h25=get('2107_electrical_data_2025.csv',URL_BASE+'2107_electrical_data_2025.csv',EXPECTED['2025'])

    # Load all sources with the accepted schema-fixed adapter.
    sys.argv=['run_later_temporal_selector_holdout.py','--output-dir',str(OUT)]
    base_df,cols,_,_=base.load_ac_power(pb,cfg['source']['expected_inverters'])
    df24,cols24,_,_=base.load_ac_power(p24,cfg['source']['expected_inverters'])
    df25,cols25,_,_=base.load_ac_power(p25,cfg['source']['expected_inverters'])
    if list(base_df.columns)!=list(df24.columns) or list(base_df.columns)!=list(df25.columns): raise RuntimeError('AC-power schema mismatch after adapter')

    cut=df24.index.max(); later=df25[df25.index>cut].copy()
    if later.empty: raise RuntimeError('No non-overlapping rows after 2024 cutoff')
    overlap_idx=df24.index.intersection(df25.index)
    overlap=pd.DataFrame({'n_overlap_timestamps':[len(overlap_idx)],'cutoff_2024_max':[str(cut)],'later_first':[str(later.index.min())],'later_last':[str(later.index.max())],
                          'rows_2024':[len(df24)],'rows_2025_object':[len(df25)],'rows_later_nonoverlap':[len(later)]})
    overlap.to_csv(OUT/'source_nonoverlap_audit.csv',index=False)

    # Original training-only normalization; no later refit.
    baseline_dates=base.admitted_dates_raw(base_df); trd,vad,ted=base.split_dates(baseline_dates,cfg['split_fractions']); scales=base.robust_scales(base_df,trd,cfg['normalization_quantile'])
    norm=later.div(scales,axis=1); cadence=base.infer_cadence_minutes(norm.index); dates=base.admitted_dates_raw(later)
    masks,counts=base.generate_masks(norm,dates,cfg['breadths'],cfg['gap_samples'],cfg['test_masks_per_regime'],42107,cfg['mask_buffer_samples'],cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,'later')
    ledger=pd.DataFrame([base.asdict(m) for m in masks]); ledger.to_csv(OUT/'later_mask_ledger.csv',index=False)
    pd.DataFrame([counts]).to_csv(OUT/'later_mask_counts.csv',index=False)

    mm=metrics_for(norm,masks,2); mm.to_csv(OUT/'later_per_mask_metrics.csv',index=False); agg=aggregate(mm); agg.to_csv(OUT/'later_aggregate_metrics.csv',index=False)
    aa=agg.set_index('method'); spearman_gain=float(aa.loc['Linear Interpolation','mean_spearman']-aa.loc['Iterative SVD','mean_spearman']); top1_gain=float(aa.loc['Linear Interpolation','mean_top1']-aa.loc['Iterative SVD','mean_top1']); boot=day_bootstrap(mm)

    ranking=mm[mm.breadth>=2]; regime_counts=ranking.groupby(['breadth','length'])['mask_id'].nunique(); n_rank_regimes_ge8=int((regime_counts>=8).sum())
    nc=ranking[ranking.method.eq('Iterative SVD')]['nonconstant_rank_fraction'].dropna(); nonconstant=float(nc.mean()) if len(nc) else 0.0
    stop=[]
    if len(masks)<cfg['stop_rules']['min_total_test_masks']: stop.append(f'total_masks:{len(masks)}')
    min_reg=int(pd.Series(counts).min()) if counts else 0
    if min_reg<cfg['stop_rules']['min_masks_per_regime']: stop.append(f'min_masks_per_regime:{min_reg}')
    if n_rank_regimes_ge8<cfg['stop_rules']['min_ranking_regimes']: stop.append(f'ranking_regimes_ge8:{n_rank_regimes_ge8}')
    if nonconstant<cfg['stop_rules']['min_nonconstant_rank_timestamp_fraction']: stop.append(f'nonconstant_rank_fraction:{nonconstant}')

    decision={'protocol':'PVDAQ2107_LATER_TEMPORAL_SELECTOR_HOLDOUT_FROZEN_20260912','source_hashes':{'baseline':hb,'2024':h24,'2025':h25},'cutoff_rule':'2025-object timestamps strictly later than max timestamp in 2024 object','cutoff_timestamp':str(cut),'later_period':[str(later.index.min()),str(later.index.max())],
              'later_rows':int(len(later)),'admitted_complete_dates':int(len(dates)),'cadence_minutes':float(cadence),'masks':int(len(masks)),'min_masks_per_regime':min_reg,'ranking_regimes_ge8':n_rank_regimes_ge8,'mean_nonconstant_rank_fraction':nonconstant,'stop_reasons':stop,
              'fixed_policies':{'MAE-only':'Iterative SVD rank 2 for all uses','use-specific-ranking':'Linear Interpolation'},'later_spearman_gain_linear_minus_svd':spearman_gain,'later_top1_gain_linear_minus_svd':top1_gain,'day_cluster_bootstrap':boot,
              'decision':'STOP' if stop else ('KEEP_MAIN_CANDIDATE' if (spearman_gain>0 or top1_gain>0) else 'KEEP_NEGATIVE_OR_NULL_SUPPLEMENT'),
              'claim_boundary':'Temporal same-site holdout only; not a new independent site and not evidence of universal method superiority. No retuning from later outcomes.'}
    (OUT/'CONTRIBUTION_DECISION.json').write_text(json.dumps(decision,indent=2))
    with open(OUT/'RESULTS_SUMMARY.md','w') as f:
        f.write('# Later temporal selector holdout\n\n```json\n'+json.dumps(decision,indent=2)+'\n```\n\n## Aggregate metrics\n\n'+agg.to_markdown(index=False)+'\n')
    print(json.dumps(decision,indent=2))

if __name__=='__main__': main()