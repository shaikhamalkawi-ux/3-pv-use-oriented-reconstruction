#!/usr/bin/env python3
from __future__ import annotations

import argparse, importlib.util, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ADAPTER_PATH=ROOT/'analysis'/'run_pvdaq2107_transfer_schemafixed.py'
spec=importlib.util.spec_from_file_location('selector_schemafixed_adapter',ADAPTER_PATH)
adapter=importlib.util.module_from_spec(spec); assert spec.loader is not None
sys.modules[spec.name]=adapter
spec.loader.exec_module(adapter)
base=adapter.core  # accepted frozen core with schema and balanced-cell pre-outcome fixes applied


def evaluate_masks(norm, masks, corr, models, svd_rank):
    arr=norm.to_numpy(float); rows=[]
    methods=['Linear Interpolation','Peer Median','Iterative SVD','Ridge Context','Context KNN','Masked Context','Correlation Summary']
    for m in masks:
        H=list(m.hidden); truth=arr[m.start_pos:m.start_pos+m.length][:,H]
        preds={'Linear Interpolation':base.linear_predict(norm,m),
               'Peer Median':base.peer_predict(norm,m),
               'Iterative SVD':base.svd_complete_predict(norm,m,svd_rank)}
        X,_,_=base.feature_rows(norm,m,corr,False); Xc,_,_=base.feature_rows(norm,m,corr,True)
        learned=base.predict_learned(models,X,Xc)
        for name,v in learned.items(): preds[name]=v.reshape(m.length,len(H))
        for method in methods:
            met=base.evaluate_pred(truth,preds[method])
            rows.append({'mask_id':m.mask_id,'date':m.date,'breadth':m.breadth,'length':m.length,'method':method,**met})
    return pd.DataFrame(rows)


def select_methods(validation_metrics: pd.DataFrame):
    agg=base.aggregate(validation_metrics).set_index('method')
    point=agg['macro_mae'].idxmin()
    energy=agg['median_energy_abs_pct'].idxmin()
    rankable=agg.dropna(subset=['mean_spearman']).copy()
    # Deterministic ranking selector: maximize validation Spearman; break exact ties by Top-1, then method name.
    best_s=rankable['mean_spearman'].max()
    cand=rankable[np.isclose(rankable['mean_spearman'],best_s,atol=1e-12,rtol=0)].copy()
    best_t=cand['mean_top1'].max()
    cand=cand[np.isclose(cand['mean_top1'],best_t,atol=1e-12,rtol=0)]
    ranking=sorted(cand.index.tolist())[0]
    return {'point':point,'energy':energy,'ranking':ranking}, agg.reset_index()


def test_policy_table(test_metrics, selected):
    agg=base.aggregate(test_metrics).set_index('method')
    p=selected['point']; e=selected['energy']; r=selected['ranking']
    out=[
      {'objective':'point_mae','policy':'MAE-only','method':p,'value':float(agg.loc[p,'macro_mae']),'direction':'lower_better'},
      {'objective':'point_mae','policy':'use-specific','method':p,'value':float(agg.loc[p,'macro_mae']),'direction':'lower_better'},
      {'objective':'energy_abs_pct','policy':'MAE-only','method':p,'value':float(agg.loc[p,'median_energy_abs_pct']),'direction':'lower_better'},
      {'objective':'energy_abs_pct','policy':'use-specific','method':e,'value':float(agg.loc[e,'median_energy_abs_pct']),'direction':'lower_better'},
      {'objective':'spearman','policy':'MAE-only','method':p,'value':float(agg.loc[p,'mean_spearman']) if pd.notna(agg.loc[p,'mean_spearman']) else None,'direction':'higher_better'},
      {'objective':'spearman','policy':'use-specific','method':r,'value':float(agg.loc[r,'mean_spearman']),'direction':'higher_better'},
      {'objective':'top1','policy':'MAE-only','method':p,'value':float(agg.loc[p,'mean_top1']) if pd.notna(agg.loc[p,'mean_top1']) else None,'direction':'higher_better'},
      {'objective':'top1','policy':'use-specific','method':r,'value':float(agg.loc[r,'mean_top1']),'direction':'higher_better'},
    ]
    return pd.DataFrame(out), agg.reset_index()


def day_bootstrap_policy_delta(test_metrics, selected, reps, seed):
    rng=np.random.default_rng(seed); days=np.array(sorted(test_metrics.date.unique()))
    p,e,r=selected['point'],selected['energy'],selected['ranking']; vals={'energy_gain_pctpoints':[],'spearman_gain':[],'top1_gain':[]}
    byday={d:test_metrics[test_metrics.date.eq(d)] for d in days}
    for _ in range(reps):
        pick=rng.choice(days,size=len(days),replace=True)
        x=pd.concat([byday[d] for d in pick],ignore_index=True)
        a=base.aggregate(x).set_index('method')
        if pd.notna(a.loc[p,'median_energy_abs_pct']) and pd.notna(a.loc[e,'median_energy_abs_pct']): vals['energy_gain_pctpoints'].append(float(a.loc[p,'median_energy_abs_pct']-a.loc[e,'median_energy_abs_pct']))
        if pd.notna(a.loc[p,'mean_spearman']) and pd.notna(a.loc[r,'mean_spearman']): vals['spearman_gain'].append(float(a.loc[r,'mean_spearman']-a.loc[p,'mean_spearman']))
        if pd.notna(a.loc[p,'mean_top1']) and pd.notna(a.loc[r,'mean_top1']): vals['top1_gain'].append(float(a.loc[r,'mean_top1']-a.loc[p,'mean_top1']))
    out={}
    for k,v in vals.items():
        out[k]={'n_boot':len(v),'median':float(np.median(v)) if v else None,'ci95':[float(np.quantile(v,.025)),float(np.quantile(v,.975))] if v else [None,None]}
    return out


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(ROOT/'config'/'pvdaq2107_frozen_config.json')); ap.add_argument('--output-dir',default=str(ROOT/'results'/'use_specific_selector_audit')); ap.add_argument('--raw-dir',default='raw_selector'); ap.add_argument('--electrical-file',default=None); args=ap.parse_args()
    # Keep adapter output path aligned with this audit so schema/balance ledgers are retained.
    sys.argv=['audit_use_specific_selector.py','--output-dir',args.output_dir]
    cfg=json.load(open(args.config)); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); raw=Path(args.raw_dir); raw.mkdir(parents=True,exist_ok=True)
    src=Path(args.electrical_file) if args.electrical_file else raw/'2107_electrical_data.csv'
    if not src.exists(): base.download(cfg['source']['electrical_url'],src)
    source_hash=base.sha256_file(src); df,cols,dups,header=base.load_ac_power(src,cfg['source']['expected_inverters']); cadence=base.infer_cadence_minutes(df.index); dates=base.admitted_dates_raw(df); trd,vad,ted=base.split_dates(dates,cfg['split_fractions']); scales=base.robust_scales(df,trd,cfg['normalization_quantile']); norm=df.div(scales,axis=1); corr=base.corr_matrix_train(norm,trd)

    val_masks,val_counts=base.generate_masks(norm,vad,cfg['breadths'],cfg['gap_samples'],cfg['validation_masks_per_regime'],cfg['seed']+10,cfg['mask_buffer_samples'],cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,'val')
    test_masks,test_counts=base.generate_masks(norm,ted,cfg['breadths'],cfg['gap_samples'],cfg['test_masks_per_regime'],cfg['seed']+20,cfg['mask_buffer_samples'],cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,'test')

    Xtr,Xctr,ytr=base.random_training_cells(norm,trd,cfg['breadths'],cfg['gap_samples'],cfg['train_cells_target'],cfg['seed']+101,cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,corr,'train')
    Xv,Xcv,yv=base.random_training_cells(norm,vad,cfg['breadths'],cfg['gap_samples'],cfg['validation_cells_target'],cfg['seed']+102,cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,corr,'learnval')
    models,tuning=base.fit_models(Xtr,Xctr,ytr,Xv,Xcv,yv,cfg); svd_rank,svd_tuning=base.tune_svd(norm,val_masks,cfg['svd_ranks']); tuning['svd']=svd_tuning; tuning['svd_selected_rank']=svd_rank

    val=evaluate_masks(norm,val_masks,corr,models,svd_rank); test=evaluate_masks(norm,test_masks,corr,models,svd_rank)
    val.to_csv(out/'validation_per_mask_metrics.csv',index=False); test.to_csv(out/'test_per_mask_metrics_rerun.csv',index=False)
    selected,valagg=select_methods(val); valagg.to_csv(out/'validation_aggregate_metrics.csv',index=False)
    policy,testagg=test_policy_table(test,selected); policy.to_csv(out/'test_policy_comparison.csv',index=False); testagg.to_csv(out/'test_aggregate_metrics_rerun.csv',index=False)
    boot=day_bootstrap_policy_delta(test,selected,cfg['bootstrap_reps'],cfg['seed']+2026)

    # Test oracle is descriptive only and never used in selection.
    ta=testagg.set_index('method')
    test_oracle={'point':ta['macro_mae'].idxmin(),'energy':ta['median_energy_abs_pct'].idxmin(),'ranking':ta['mean_spearman'].idxmax()}
    decision={'scope':'Post-baseline validation-locked selector audit. Test outcomes from the historical benchmark were already known before this audit; this is not preregistered or independent confirmation.',
              'accepted_implementation_adapter':'run_pvdaq2107_transfer_schemafixed.py',
              'source_sha256':source_hash,'cadence_minutes':cadence,'train_dates':len(trd),'validation_dates':len(vad),'test_dates':len(ted),
              'validation_masks':len(val_masks),'test_masks':len(test_masks),'selected_on_validation':selected,'test_oracle_descriptive_only':test_oracle,
              'bootstrap_test_policy_gains':boot,
              'interpretation_rule':'A positive test gain supports practical value of validation-locked use-specific selection for that endpoint; a null or negative gain must be retained and does not invalidate the benchmark finding that objectives can prefer different methods.'}
    json.dump(decision,open(out/'CONTRIBUTION_DECISION.json','w'),indent=2)
    json.dump(tuning,open(out/'validation_tuning_rerun.json','w'),indent=2)
    pd.DataFrame([base.asdict(m) for m in val_masks]).to_csv(out/'validation_mask_ledger_rerun.csv',index=False)
    pd.DataFrame([base.asdict(m) for m in test_masks]).to_csv(out/'test_mask_ledger_rerun.csv',index=False)
    with open(out/'RESULTS_SUMMARY.md','w') as f:
        f.write('# Use-Specific Selector Audit\n\n')
        f.write('This is a post-baseline audit with method choices locked on regenerated validation masks only. Historical test outcomes were already known before this audit.\n\n')
        f.write('## Validation-selected methods\n\n```json\n'+json.dumps(selected,indent=2)+'\n```\n\n')
        f.write('## Test policy comparison\n\n'+policy.to_markdown(index=False)+'\n\n')
        f.write('## Day-cluster bootstrap policy gains\n\n```json\n'+json.dumps(boot,indent=2)+'\n```\n')
    print(json.dumps(decision,indent=2))

if __name__=='__main__': main()
