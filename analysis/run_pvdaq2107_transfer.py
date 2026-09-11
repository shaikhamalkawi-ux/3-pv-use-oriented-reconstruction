#!/usr/bin/env python3
import argparse, hashlib, json, math, os, random, re, sys, time, urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

@dataclass(frozen=True)
class Mask:
    mask_id: str
    start_ts: str
    date: str
    start_pos: int
    length: int
    breadth: int
    hidden: tuple

def sha256_file(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(chunk),b''): h.update(b)
    return h.hexdigest()

def download(url, path):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size>0: return
    req=urllib.request.Request(url, headers={'User-Agent':'PVDAQ2107-use-oriented-transfer/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(path,'wb') as f:
        while True:
            b=r.read(1024*1024)
            if not b: break
            f.write(b)

def load_ac_power(csv_path, expected_n=24):
    header=pd.read_csv(csv_path,nrows=0).columns.tolist(); ts_col=header[0]
    ac=[c for c in header if re.search(r'inv_\d+_ac_power_inv_',c)]
    ac=sorted(ac,key=lambda c:int(re.search(r'inv_(\d+)_',c).group(1)))
    if len(ac)!=expected_n: raise RuntimeError(f'Expected {expected_n} inverter AC-power channels, found {len(ac)}')
    df=pd.read_csv(csv_path,usecols=[ts_col]+ac,parse_dates=[ts_col],low_memory=False)
    df=df.rename(columns={ts_col:'measured_on'}).set_index('measured_on').sort_index()
    dup=df.index.duplicated(keep=False); duplicate_rows=int(dup.sum())
    if duplicate_rows: df=df.loc[~dup]
    for c in ac: df[c]=pd.to_numeric(df[c],errors='coerce')
    return df, ac, duplicate_rows, header

def infer_cadence_minutes(index):
    d=pd.Series(index).sort_values().diff().dropna().dt.total_seconds().div(60); d=d[(d>0)&(d<180)]
    if d.empty: raise RuntimeError('Cannot infer cadence')
    return float(d.mode().iloc[0])

def admitted_dates_raw(df):
    out=[]
    for date,g in df.groupby(df.index.date):
        if len(g)>=24 and (g.median(axis=1,skipna=True)>0).any(): out.append(pd.Timestamp(date))
    return sorted(out)

def split_dates(dates, fracs):
    n=len(dates); a=int(math.floor(fracs[0]*n)); b=int(math.floor((fracs[0]+fracs[1])*n))
    if min(a,b-a,n-b)<2: raise RuntimeError(f'Insufficient admitted dates for split: {n}')
    return dates[:a], dates[a:b], dates[b:]

def robust_scales(df, train_dates, q):
    train_set=set(d.date() for d in train_dates); tr=df[[idx.date() in train_set for idx in df.index]]; scales={}
    for c in df.columns:
        v=tr[c].to_numpy(dtype=float); v=v[np.isfinite(v)&(v>0)]
        if len(v)<100: raise RuntimeError(f'Insufficient positive training values for {c}: {len(v)}')
        s=float(np.quantile(v,q))
        if not np.isfinite(s) or s<=0: raise RuntimeError(f'Invalid scale for {c}: {s}')
        scales[c]=s
    return pd.Series(scales)

def date_positions(index, allowed_dates):
    aset=set(d.date() for d in allowed_dates); out={}
    for i,ts in enumerate(index):
        if ts.date() in aset: out.setdefault(ts.date(),[]).append(i)
    return out

def contiguous(idx, start, length, cadence_min):
    end=start+length-1
    if start<1 or end+1>=len(idx): return False
    if idx[start].date()!=idx[end].date() or idx[start-1].date()!=idx[start].date() or idx[end+1].date()!=idx[start].date(): return False
    dd=pd.Series(idx[start-1:end+2]).diff().dropna().dt.total_seconds().to_numpy()/60
    return bool(np.allclose(dd,cadence_min,atol=1e-6))

def mask_valid(arr, idx, start, length, hidden, cadence_min, out_range, min_peer_frac):
    if not contiguous(idx,start,length,cadence_min): return False
    hidden=np.array(hidden,dtype=int); seg=arr[start:start+length]
    if not np.all(np.isfinite(seg[:,hidden])) or not np.all(np.isfinite(arr[start-1,hidden])) or not np.all(np.isfinite(arr[start+length,hidden])): return False
    unhidden=np.setdiff1d(np.arange(arr.shape[1]),hidden)
    if len(unhidden)==0 or np.any(np.mean(np.isfinite(seg[:,unhidden]),axis=1)<min_peer_frac): return False
    med=np.nanmedian(seg,axis=1)
    return bool(np.all(np.isfinite(med)) and np.all(med>=out_range[0]) and np.all(med<=out_range[1]))

def choose_hidden_balanced(counts,b,rng):
    chosen=np.sort(np.argsort(counts+rng.random(len(counts))*1e-6)[:b]); counts[chosen]+=1
    return tuple(int(x) for x in chosen)

def generate_masks(norm_df, allowed_dates, breadths, lengths, target_per_regime, seed, buffer_samples, min_peer_frac, out_range, cadence_min, prefix):
    rng=np.random.default_rng(seed); arr=norm_df.to_numpy(dtype=float); idx=norm_df.index
    pos_by_date=date_positions(idx,allowed_dates); date_keys=list(pos_by_date); occupancy={d:[] for d in date_keys}; masks=[]; regime_counts={}
    for b in breadths:
        for L in lengths:
            counts=np.zeros(arr.shape[1],dtype=int); got=0; attempts=0; max_attempts=max(20000,target_per_regime*1000)
            while got<target_per_regime and attempts<max_attempts:
                attempts+=1; d=date_keys[int(rng.integers(0,len(date_keys)))]; positions=pos_by_date[d]
                if len(positions)<L+2: continue
                start=int(positions[int(rng.integers(1,max(2,len(positions)-L-1)))]); hidden=choose_hidden_balanced(counts,b,rng)
                if not mask_valid(arr,idx,start,L,hidden,cadence_min,out_range,min_peer_frac): counts[list(hidden)]-=1; continue
                lo=start-buffer_samples; hi=start+L-1+buffer_samples
                if any(not (hi<olo or lo>ohi) for olo,ohi in occupancy[d]): counts[list(hidden)]-=1; continue
                occupancy[d].append((lo,hi)); masks.append(Mask(f'{prefix}_b{b}_l{L}_{got:02d}',str(idx[start]),str(d),start,L,b,hidden)); got+=1
            regime_counts[f'b{b}_l{L}']=got
    return masks, regime_counts

def corr_matrix_train(norm_df,train_dates):
    aset=set(d.date() for d in train_dates); tr=norm_df[[x.date() in aset for x in norm_df.index]]
    return tr.corr(min_periods=100).fillna(0.0).to_numpy(dtype=float)

def time_features(ts):
    tod=(ts.hour*60+ts.minute)/1440.0; doy=(ts.dayofyear-1)/365.25
    return [math.sin(2*math.pi*tod),math.cos(2*math.pi*tod),math.sin(2*math.pi*doy),math.cos(2*math.pi*doy)]

def feature_rows(norm_df, mask, corr=None, add_corr=False):
    arr=norm_df.to_numpy(dtype=float); idx=norm_df.index; n=arr.shape[1]; s=mask.start_pos; L=mask.length; H=np.array(mask.hidden,dtype=int)
    rows=[]; y=[]; meta=[]; current=arr[s:s+L].copy(); current[:,H]=np.nan; miss=(~np.isfinite(current)).astype(float)
    for pos in range(L):
        ts=idx[s+pos]
        for target in H:
            before=arr[s-1,target]; after=arr[s+L,target]; frac=(pos+1)/(L+1); bridge=before+(after-before)*frac
            onehot=np.zeros(n); onehot[target]=1.0
            base=np.concatenate([current[pos],onehot,np.asarray(time_features(ts)),np.asarray([before,after,bridge,float(mask.breadth),float(L),float(pos)/(max(L-1,1))]),miss[pos]])
            if add_corr:
                w=np.maximum(corr[target],0.0)**2; w[target]=0.0; obs=np.isfinite(current[pos]); den=float(np.sum(w[obs])); cs=float(np.sum(w[obs]*current[pos,obs])/den) if den>0 else np.nan
                base=np.concatenate([base,[cs]])
            rows.append(base); y.append(arr[s+pos,target]); meta.append((ts,target,pos))
    return np.asarray(rows,float),np.asarray(y,float),meta

def random_training_cells(norm_df, allowed_dates, breadths, lengths, target_cells, seed, min_peer_frac, out_range, cadence_min, corr, prefix):
    rng=np.random.default_rng(seed); arr=norm_df.to_numpy(float); idx=norm_df.index; pos_by_date=date_positions(idx,allowed_dates); dkeys=list(pos_by_date); X=[]; Xc=[]; y=[]; attempts=0; maskno=0; regimes=[(b,L) for b in breadths for L in lengths]
    while len(y)<target_cells and attempts<target_cells*20:
        attempts+=1; b,L=regimes[maskno%len(regimes)]; maskno+=1; d=dkeys[int(rng.integers(0,len(dkeys)))]; pos=pos_by_date[d]
        if len(pos)<L+2: continue
        start=int(pos[int(rng.integers(1,max(2,len(pos)-L-1)))]); hidden=tuple(sorted(rng.choice(arr.shape[1],size=b,replace=False).tolist()))
        if not mask_valid(arr,idx,start,L,hidden,cadence_min,out_range,min_peer_frac): continue
        m=Mask(f'{prefix}_{maskno}',str(idx[start]),str(d),start,L,b,hidden); xb,yb,_=feature_rows(norm_df,m,corr,False); xc,_,_=feature_rows(norm_df,m,corr,True); remain=target_cells-len(y)
        if len(yb)>remain:
            take=np.arange(len(yb)); rng.shuffle(take); take=take[:remain]; xb=xb[take]; xc=xc[take]; yb=yb[take]
        X.append(xb); Xc.append(xc); y.extend(yb.tolist())
    if len(y)<target_cells: raise RuntimeError(f'Could generate only {len(y)} of {target_cells} cells')
    return np.vstack(X),np.vstack(Xc),np.asarray(y)

def linear_predict(norm_df,mask):
    arr=norm_df.to_numpy(float); s=mask.start_pos; L=mask.length; H=np.array(mask.hidden); out=np.empty((L,len(H)))
    for j,t in enumerate(H):
        a=arr[s-1,t]; b=arr[s+L,t]
        for p in range(L): out[p,j]=a+(b-a)*(p+1)/(L+1)
    return out

def peer_predict(norm_df,mask):
    arr=norm_df.to_numpy(float); s=mask.start_pos; L=mask.length; H=np.array(mask.hidden); peers=np.setdiff1d(np.arange(arr.shape[1]),H); vals=np.nanmedian(arr[s:s+L][:,peers],axis=1)
    return np.repeat(vals[:,None],len(H),axis=1)

def svd_complete_predict(norm_df,mask,rank,n_iter=20):
    date=pd.Timestamp(mask.start_ts).date(); day=norm_df[norm_df.index.date==date]; X=day.to_numpy(float).copy(); ts=pd.Timestamp(mask.start_ts); loc=np.where(day.index==ts)[0]
    if len(loc)!=1: raise RuntimeError('Mask start not unique in day')
    s=int(loc[0]); H=np.array(mask.hidden); L=mask.length; artificial=np.zeros(X.shape,bool); artificial[s:s+L,H]=True; X[artificial]=np.nan; miss=~np.isfinite(X); original=X.copy(); rowmed=np.nanmedian(X,axis=1); colmed=np.nanmedian(X,axis=0); glob=np.nanmedian(X)
    for i in range(X.shape[0]):
        for j in np.where(~np.isfinite(X[i]))[0]:
            v=rowmed[i]
            if not np.isfinite(v): v=colmed[j]
            if not np.isfinite(v): v=glob
            X[i,j]=v
    for _ in range(n_iter):
        mu=np.mean(X,axis=0,keepdims=True); U,S,Vt=np.linalg.svd(X-mu,full_matrices=False); r=min(rank,len(S)); R=(U[:,:r]*S[:r])@Vt[:r,:]+mu; X[miss]=R[miss]; X[~miss]=original[~miss]
    return X[s:s+L][:,H]

def evaluate_pred(truth,pred):
    e=pred-truth; mae=float(np.mean(np.abs(e))); rmse=float(np.sqrt(np.mean(e**2))); tsum=float(np.sum(truth)); signed=100*(float(np.sum(pred))-tsum)/tsum if abs(tsum)>1e-15 else np.nan; rhos=[]; tops=[]; nonconst=[]
    if truth.shape[1]>=2:
        for a,b in zip(truth,pred):
            nc=(np.nanmax(a)-np.nanmin(a))>1e-12; nonconst.append(nc)
            if nc and (np.nanmax(b)-np.nanmin(b))>1e-12:
                r=spearmanr(a,b).statistic
                if np.isfinite(r): rhos.append(float(r))
            tops.append(float(np.argmax(a)==np.argmax(b)))
    return {'mae':mae,'rmse':rmse,'energy_abs_pct':abs(signed) if np.isfinite(signed) else np.nan,'energy_signed_pct':signed,'spearman':float(np.mean(rhos)) if rhos else np.nan,'top1':float(np.mean(tops)) if tops else np.nan,'nonconstant_rank_fraction':float(np.mean(nonconst)) if nonconst else np.nan}

def winner_set(series,mode='min',tol=1e-12):
    s=series.dropna()
    if s.empty: return set()
    best=s.min() if mode=='min' else s.max()
    return set(s.index[np.isclose(s.to_numpy(float),best,atol=tol,rtol=0)])

def weighted_knn_predict(dist,ind,ytrain,k):
    d=dist[:,:k]; ii=ind[:,:k]; yy=ytrain[ii]; out=np.empty(len(d))
    for r in range(len(d)):
        z=d[r]<=1e-12
        if np.any(z): out[r]=float(np.mean(yy[r,z]))
        else:
            w=1.0/d[r]; out[r]=float(np.sum(w*yy[r])/np.sum(w))
    return out

def fit_models(Xtr,Xctr,ytr,Xv,Xcv,yv,cfg):
    tuning={}; imp=SimpleImputer(strategy='median'); Xtri=imp.fit_transform(Xtr); Xvi=imp.transform(Xv); scaler=StandardScaler(); Xtrs=scaler.fit_transform(Xtri); Xvs=scaler.transform(Xvi); best=None
    for a in cfg['ridge_alphas']:
        m=Ridge(alpha=float(a)); m.fit(Xtrs,ytr); sc=float(np.mean(np.abs(m.predict(Xvs)-yv))); tuning.setdefault('ridge',[]).append({'alpha':a,'val_mae':sc}); best=(sc,a,m) if best is None or sc<best[0] else best
    ridge=(imp,scaler,best[2]); tuning['ridge_selected_alpha']=best[1]
    rng=np.random.default_rng(cfg['seed']+31); cap=min(cfg['knn_train_cap'],len(ytr)); sel=np.arange(len(ytr)); sel=rng.choice(sel,size=cap,replace=False) if len(sel)>cap else sel; impk=SimpleImputer(strategy='median'); Xki=impk.fit_transform(Xtr[sel]); Xvi2=impk.transform(Xv); sck=StandardScaler(); Xks=sck.fit_transform(Xki); Xvs2=sck.transform(Xvi2); nn=NearestNeighbors(n_neighbors=max(cfg['knn_k']),n_jobs=-1).fit(Xks); dist,ind=nn.kneighbors(Xvs2); bestk=None
    for k in cfg['knn_k']:
        sc=float(np.mean(np.abs(weighted_knn_predict(dist,ind,ytr[sel],int(k))-yv))); tuning.setdefault('knn',[]).append({'k':k,'val_mae':sc}); bestk=(sc,int(k)) if bestk is None or sc<bestk[0] else bestk
    knn=(impk,sck,nn,ytr[sel],bestk[1]); tuning['knn_selected_k']=bestk[1]; p=cfg['lgbm']
    masked=lgb.LGBMRegressor(objective='mae',n_estimators=p['n_estimators'],learning_rate=p['learning_rate'],num_leaves=p['num_leaves'],random_state=cfg['seed'],n_jobs=-1,verbosity=-1); masked.fit(Xtr,ytr,eval_set=[(Xv,yv)],callbacks=[lgb.early_stopping(p['early_stopping_rounds'],verbose=False)]); tuning['masked_context_best_iteration']=int(masked.best_iteration_ or p['n_estimators'])
    corrm=lgb.LGBMRegressor(objective='mae',n_estimators=p['n_estimators'],learning_rate=p['learning_rate'],num_leaves=p['num_leaves'],random_state=cfg['seed']+1,n_jobs=-1,verbosity=-1); corrm.fit(Xctr,ytr,eval_set=[(Xcv,yv)],callbacks=[lgb.early_stopping(p['early_stopping_rounds'],verbose=False)]); tuning['correlation_summary_best_iteration']=int(corrm.best_iteration_ or p['n_estimators'])
    return {'ridge':ridge,'knn':knn,'masked':masked,'corr':corrm},tuning

def predict_learned(models,X,Xc):
    imp,sc,m=models['ridge']; pr=m.predict(sc.transform(imp.transform(X))); impk,sck,nn,yk,k=models['knn']; Xs=sck.transform(impk.transform(X)); d,ind=nn.kneighbors(Xs); pk=weighted_knn_predict(d,ind,yk,k)
    return {'Ridge Context':pr,'Context KNN':pk,'Masked Context':models['masked'].predict(X),'Correlation Summary':models['corr'].predict(Xc)}

def tune_svd(norm_df,val_masks,ranks):
    rows=[]; best=None
    for r in ranks:
        es=[]
        for m in val_masks:
            truth=norm_df.to_numpy(float)[m.start_pos:m.start_pos+m.length][:,list(m.hidden)]; es.append(np.mean(np.abs(svd_complete_predict(norm_df,m,int(r))-truth)))
        sc=float(np.mean(es)); rows.append({'rank':int(r),'val_macro_mae':sc}); best=(sc,int(r)) if best is None or sc<best[0] else best
    return best[1],rows

def aggregate(mm):
    return pd.DataFrame([{'method':m,'macro_mae':g.mae.mean(),'macro_rmse':g.rmse.mean(),'median_energy_abs_pct':g.energy_abs_pct.median(),'mean_spearman':g.spearman.mean(),'mean_top1':g.top1.mean(),'n_masks':len(g)} for m,g in mm.groupby('method')]).sort_values('method')

def agreement_tables(mm):
    per=[]
    for mid,g in mm.groupby('mask_id'):
        s=g.set_index('method'); pw=winner_set(s.mae,'min'); ew=winner_set(s.energy_abs_pct,'min'); rw=winner_set(s.spearman,'max'); tw=winner_set(s.top1,'max'); row=g.iloc[0]
        per.append({'mask_id':mid,'date':row.date,'breadth':row.breadth,'length':row.length,'point_winners':'|'.join(sorted(pw)),'energy_winners':'|'.join(sorted(ew)),'spearman_winners':'|'.join(sorted(rw)),'top1_winners':'|'.join(sorted(tw)),'point_energy_agree':int(bool(pw&ew)) if ew else np.nan,'point_spearman_agree':int(bool(pw&rw)) if rw else np.nan,'point_top1_agree':int(bool(pw&tw)) if tw else np.nan})
    per=pd.DataFrame(per); regs=[]
    for (b,L),g in mm.groupby(['breadth','length']):
        a=aggregate(g).set_index('method'); pw=winner_set(a.macro_mae,'min'); ew=winner_set(a.median_energy_abs_pct,'min'); rw=winner_set(a.mean_spearman,'max'); tw=winner_set(a.mean_top1,'max')
        regs.append({'breadth':b,'length':L,'point_winners':'|'.join(sorted(pw)),'energy_winners':'|'.join(sorted(ew)),'spearman_winners':'|'.join(sorted(rw)),'top1_winners':'|'.join(sorted(tw)),'point_energy_agree':int(bool(pw&ew)) if ew else np.nan,'point_spearman_agree':int(bool(pw&rw)) if rw else np.nan,'point_top1_agree':int(bool(pw&tw)) if tw else np.nan})
    return per,pd.DataFrame(regs)

def bootstrap_day_agreement(per,cols,reps,seed):
    rng=np.random.default_rng(seed); days=sorted(per.date.unique()); out={}
    for col in cols:
        vals=[]
        for _ in range(reps):
            sam=rng.choice(days,size=len(days),replace=True); x=pd.concat([per[per.date==d] for d in sam],ignore_index=True)[col].dropna()
            if len(x): vals.append(float(x.mean()))
        out[col]={'estimate':float(per[col].dropna().mean()) if per[col].notna().any() else None,'bootstrap_2.5':float(np.quantile(vals,.025)) if vals else None,'bootstrap_97.5':float(np.quantile(vals,.975)) if vals else None,'reps':len(vals)}
    return out

def sensitivity_from_cells(cells,meta,exclude_target=None,mask_ids=None):
    c=cells.copy()
    if exclude_target is not None: c=c[c.target_inverter!=exclude_target]
    if mask_ids is not None: c=c[c.mask_id.isin(mask_ids)]
    rows=[]
    for (mid,method),g in c.groupby(['mask_id','method']):
        truth=g.truth.to_numpy(); pred=g.pred.to_numpy(); tsum=truth.sum(); signed=100*(pred.sum()-tsum)/tsum if abs(tsum)>1e-15 else np.nan; rhos=[]; tops=[]
        for _,h in g.groupby('timestamp'):
            if h.target_inverter.nunique()<2: continue
            h=h.sort_values('target_inverter'); a=h.truth.to_numpy(); b=h.pred.to_numpy()
            if np.ptp(a)>1e-12 and np.ptp(b)>1e-12:
                r=spearmanr(a,b).statistic
                if np.isfinite(r): rhos.append(float(r))
            tops.append(float(np.argmax(a)==np.argmax(b)))
        md=meta.loc[mid]; rows.append({'mask_id':mid,'method':method,'date':md['date'],'breadth':md['breadth'],'length':md['length'],'mae':float(np.mean(np.abs(pred-truth))),'rmse':float(np.sqrt(np.mean((pred-truth)**2))),'energy_abs_pct':abs(signed) if np.isfinite(signed) else np.nan,'energy_signed_pct':signed,'spearman':np.mean(rhos) if rhos else np.nan,'top1':np.mean(tops) if tops else np.nan})
    return aggregate(pd.DataFrame(rows)) if rows else pd.DataFrame()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--output-dir',required=True); ap.add_argument('--raw-dir',default='raw'); ap.add_argument('--electrical-file',default=None); args=ap.parse_args(); cfg=json.load(open(args.config)); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); raw=Path(args.raw_dir); raw.mkdir(parents=True,exist_ok=True); t0=time.time(); src=Path(args.electrical_file) if args.electrical_file else raw/'2107_electrical_data.csv'
    if not src.exists(): download(cfg['source']['electrical_url'],src)
    source_hash=sha256_file(src); size=src.stat().st_size; df,cols,dups,header=load_ac_power(src,cfg['source']['expected_inverters']); cadence=infer_cadence_minutes(df.index); dates=admitted_dates_raw(df); trd,vad,ted=split_dates(dates,cfg['split_fractions']); scales=robust_scales(df,trd,cfg['normalization_quantile']); norm=df.div(scales,axis=1); corr=corr_matrix_train(norm,trd)
    inventory={'source_url':cfg['source']['electrical_url'],'s3_key':cfg['source']['s3_key'],'sha256':source_hash,'bytes':size,'raw_rows_after_duplicate_exclusion':int(len(df)),'duplicate_timestamp_rows_excluded':dups,'raw_columns':len(header),'ac_power_channels':len(cols),'first_timestamp':str(df.index.min()),'last_timestamp':str(df.index.max()),'inferred_cadence_minutes':cadence,'admitted_dates':len(dates),'train_dates':len(trd),'validation_dates':len(vad),'test_dates':len(ted),'train_first_last':[str(trd[0].date()),str(trd[-1].date())],'validation_first_last':[str(vad[0].date()),str(vad[-1].date())],'test_first_last':[str(ted[0].date()),str(ted[-1].date())]}; json.dump(inventory,open(out/'source_inventory.json','w'),indent=2); scales.rename('training_p995_scale').to_csv(out/'training_scales.csv'); pd.DataFrame(corr,index=cols,columns=cols).to_csv(out/'training_correlations.csv')
    val_masks,val_counts=generate_masks(norm,vad,cfg['breadths'],cfg['gap_samples'],cfg['validation_masks_per_regime'],cfg['seed']+10,cfg['mask_buffer_samples'],cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,'val'); test_masks,test_counts=generate_masks(norm,ted,cfg['breadths'],cfg['gap_samples'],cfg['test_masks_per_regime'],cfg['seed']+20,cfg['mask_buffer_samples'],cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,'test'); pd.DataFrame([asdict(m) for m in val_masks]).to_csv(out/'validation_mask_ledger.csv',index=False); pd.DataFrame([asdict(m) for m in test_masks]).to_csv(out/'test_mask_ledger.csv',index=False); json.dump({'validation':val_counts,'test':test_counts},open(out/'mask_regime_counts.json','w'),indent=2)
    Xtr,Xctr,ytr=random_training_cells(norm,trd,cfg['breadths'],cfg['gap_samples'],cfg['train_cells_target'],cfg['seed']+101,cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,corr,'train'); Xv,Xcv,yv=random_training_cells(norm,vad,cfg['breadths'],cfg['gap_samples'],cfg['validation_cells_target'],cfg['seed']+102,cfg['min_unhidden_peer_fraction'],cfg['primary_output_range'],cadence,corr,'learnval'); models,tuning=fit_models(Xtr,Xctr,ytr,Xv,Xcv,yv,cfg); svd_rank,svd_tuning=tune_svd(norm,val_masks,cfg['svd_ranks']); tuning['svd']=svd_tuning; tuning['svd_selected_rank']=svd_rank; json.dump(tuning,open(out/'validation_tuning.json','w'),indent=2)
    rows=[]; cells=[]; arr=norm.to_numpy(float); methods=['Linear Interpolation','Peer Median','Iterative SVD','Ridge Context','Context KNN','Masked Context','Correlation Summary']
    for m in test_masks:
        H=list(m.hidden); truth=arr[m.start_pos:m.start_pos+m.length][:,H]; preds={'Linear Interpolation':linear_predict(norm,m),'Peer Median':peer_predict(norm,m),'Iterative SVD':svd_complete_predict(norm,m,svd_rank)}; X,_,meta=feature_rows(norm,m,corr,False); Xc,_,_=feature_rows(norm,m,corr,True); learned=predict_learned(models,X,Xc)
        for name,v in learned.items(): preds[name]=v.reshape(m.length,len(H))
        site=float(np.nanmedian(arr[m.start_pos:m.start_pos+m.length]))
        for method in methods:
            met=evaluate_pred(truth,preds[method]); rows.append({'mask_id':m.mask_id,'date':m.date,'start_ts':m.start_ts,'breadth':m.breadth,'length':m.length,'hidden':'|'.join(map(str,H)),'site_median_norm_output':site,'method':method,**met})
            for p in range(m.length):
                for j,target in enumerate(H): cells.append({'mask_id':m.mask_id,'date':m.date,'timestamp':str(norm.index[m.start_pos+p]),'breadth':m.breadth,'length':m.length,'target_inverter':int(target),'method':method,'truth':float(truth[p,j]),'pred':float(preds[method][p,j])})
    mm=pd.DataFrame(rows); cells=pd.DataFrame(cells); mm.to_csv(out/'per_mask_metrics.csv',index=False); cells.to_csv(out/'per_cell_predictions.csv',index=False); agg=aggregate(mm); agg.to_csv(out/'aggregate_metrics.csv',index=False); per,regs=agreement_tables(mm); per.to_csv(out/'mask_level_agreement.csv',index=False); regs.to_csv(out/'regime_level_agreement.csv',index=False); boot=bootstrap_day_agreement(per,['point_energy_agree','point_spearman_agree','point_top1_agree'],cfg['bootstrap_reps'],cfg['seed']+999); json.dump(boot,open(out/'day_cluster_bootstrap.json','w'),indent=2)
    sr=cfg['stop_rules']; ranking_good=0
    for _,g in mm[(mm.breadth>=2)&(mm.method=='Linear Interpolation')].groupby(['breadth','length']):
        if (g.nonconstant_rank_fraction>=sr['min_nonconstant_rank_timestamp_fraction']).sum()>=sr['min_ranking_masks_per_regime']: ranking_good+=1
    stops=[]
    if len(test_masks)<sr['min_total_test_masks']: stops.append(f'total_test_masks={len(test_masks)} < {sr["min_total_test_masks"]}')
    if any(v<sr['min_masks_per_regime'] for v in test_counts.values()): stops.append('one_or_more_regimes_below_minimum_masks')
    if ranking_good<sr['min_ranking_regimes']: stops.append(f'ranking_good_regimes={ranking_good} < {sr["min_ranking_regimes"]}')
    aa=agg.set_index('method'); aw={'point':sorted(winner_set(aa.macro_mae,'min')),'energy':sorted(winner_set(aa.median_energy_abs_pct,'min')),'spearman':sorted(winner_set(aa.mean_spearman,'max')),'top1':sorted(winner_set(aa.mean_top1,'max'))}; reg_disagree=bool(((regs.point_energy_agree==0)|(regs.point_spearman_agree==0)|(regs.point_top1_agree==0)).any()); aggregate_diff=not (set(aw['point'])==set(aw['energy'])==set(aw['spearman'])==set(aw['top1'])); decision={'stop_rules_pass':not stops,'stop_reasons':stops,'ranking_good_regimes':ranking_good,'aggregate_winners':aw,'aggregate_winners_differ':aggregate_diff,'any_regime_disagreement':reg_disagree,'candidate_main_paper_external_result':bool((not stops) and (aggregate_diff or reg_disagree)),'interpretation_rule':'Supports transferable use-oriented principle only if downstream preferences/agreements differ, or otherwise documents a reproducible transfer boundary; never requires Qatar winner identity.'}; json.dump(decision,open(out/'contribution_decision.json','w'),indent=2)
    meta=mm.drop_duplicates('mask_id').set_index('mask_id')[['date','breadth','length','site_median_norm_output']]; loo=[]
    for inv in range(len(cols)):
        a=sensitivity_from_cells(cells,meta,exclude_target=inv)
        if not a.empty: a['excluded_inverter']=inv; loo.append(a)
    if loo: pd.concat(loo,ignore_index=True).to_csv(out/'sensitivity_leave_one_inverter_out.csv',index=False)
    one=per.sort_values(['date','mask_id']).groupby('date').head(1).mask_id.tolist(); sensitivity_from_cells(cells,meta,mask_ids=one).to_csv(out/'sensitivity_one_mask_per_day.csv',index=False); low=meta[meta.site_median_norm_output<=0.80].index.tolist(); sensitivity_from_cells(cells,meta,mask_ids=low).to_csv(out/'sensitivity_remove_high_output.csv',index=False)
    import sklearn; json.dump({'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'scipy':__import__('scipy').__version__,'scikit_learn':sklearn.__version__,'lightgbm':lgb.__version__},open(out/'environment.json','w'),indent=2)
    with open(out/'RESULTS_SUMMARY.md','w') as f:
        f.write(f"# PVDAQ 2107 External-Transfer Results\n\nProtocol: `{cfg['protocol_version']}`  \nSource SHA-256: `{source_hash}`  \nCadence: {cadence:g} min  \nTest masks: {len(test_masks)}  \n\n## Aggregate metrics\n\n{agg.to_markdown(index=False)}\n\n## Contribution decision\n\n```json\n{json.dumps(decision,indent=2)}\n```\n\n## Day-cluster agreement\n\n```json\n{json.dumps(boot,indent=2)}\n```\n")
    qa={'elapsed_seconds':time.time()-t0,'protocol_version':cfg['protocol_version'],'finite_metric_checks':{'aggregate_macro_mae_all_finite':bool(np.isfinite(agg.macro_mae).all()),'aggregate_energy_all_finite':bool(np.isfinite(agg.median_energy_abs_pct).all()),'test_masks':len(test_masks),'methods':len(methods)}}; qa['outputs']={p.name:{'bytes':p.stat().st_size,'sha256':sha256_file(p)} for p in out.iterdir() if p.is_file()}; json.dump(qa,open(out/'qa_manifest.json','w'),indent=2); print(json.dumps({'inventory':inventory,'tuning':tuning,'decision':decision,'elapsed_seconds':qa['elapsed_seconds']},indent=2))
if __name__=='__main__': main()
