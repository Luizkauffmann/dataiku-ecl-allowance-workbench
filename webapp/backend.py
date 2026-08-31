import json, uuid
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from flask import request, jsonify
import dataiku

NAMES={k:k for k in ['portfolio_snapshot','counterparty_snapshot','macroeconomic_scenarios','scenario_config','stage_rules','model_group_config','cecl_run_manifest','cecl_instrument_results','cecl_attribution_results']}

def df(name): return dataiku.Dataset(NAMES[name]).get_dataframe()
def write(name,x): dataiku.Dataset(NAMES[name]).write_with_schema(x)
def safe(v):
    if pd.isna(v): return None
    if isinstance(v,(np.integer,)): return int(v)
    if isinstance(v,(np.floating,)): return float(v)
    return v

def records(x,limit=None):
    if limit: x=x.head(limit)
    return [{k:safe(v) for k,v in r.items()} for r in x.to_dict('records')]

def models():
    try:
        p=dataiku.api_client().get_default_project(); out=[]
        for m in p.list_saved_models():
            obj=p.get_saved_model(m['id']); versions=[]
            try:
                for v in obj.list_versions(): versions.append({'id':v.get('id'),'label':v.get('id')})
            except Exception: pass
            out.append({'id':m['id'],'name':m.get('name',m['id']),'versions':versions})
        return out
    except Exception: return []

@app.route('/context')
def context():
    p=df('portfolio_snapshot'); return jsonify({'as_of_dates':sorted(p.as_of_date.astype(str).unique().tolist()),'products':sorted(p.product_type.unique().tolist()),'models':models(),'model_group':records(df('model_group_config'))})

@app.route('/runs')
def runs():
    x=df('cecl_run_manifest').sort_values(['as_of_date','created_at'],ascending=[False,False]); return jsonify(records(x))

@app.route('/overview/<run_id>')
def overview(run_id):
    m=df('cecl_run_manifest'); r=df('cecl_instrument_results'); meta=m[m.run_id.eq(run_id)]
    if meta.empty: return jsonify({'error':'Run not found'}),404
    x=r[r.run_id.eq(run_id)].copy(); one=x.sort_values('scenario').drop_duplicates('instrument_id')
    portfolio=x.groupby('product_type',as_index=False).weighted_ecl.sum().sort_values('weighted_ecl',ascending=False)
    stage=x.groupby('stage',as_index=False).weighted_ecl.sum(); scen=x.groupby('scenario',as_index=False).agg(scenario_ecl=('scenario_ecl','sum'),weight=('scenario_weight','first'))
    top=x.groupby(['instrument_id','product_type','stage'],as_index=False).agg(ead=('ead','max'),ecl=('weighted_ecl','sum')).nlargest(10,'ecl')
    mm=meta.iloc[0]; return jsonify({'meta':{k:safe(v) for k,v in mm.items()},'instruments':int(one.instrument_id.nunique()),'portfolio':records(portfolio),'stage':records(stage),'scenario':records(scen),'top':records(top)})

@app.route('/compare')
def compare():
    fr=request.args.get('from'); to=request.args.get('to'); m=df('cecl_run_manifest').set_index('run_id'); a=m.loc[fr]; b=m.loc[to]
    att=df('cecl_attribution_results'); z=att[(att.from_run_id.eq(fr))&(att.to_run_id.eq(to))]
    return jsonify({'from_ecl':float(a.total_ecl),'to_ecl':float(b.total_ecl),'delta':float(b.total_ecl-a.total_ecl),'rows':records(z.sort_values(['level','sort_order']))})

def formula_run(cfg):
    asof=cfg['as_of_date']; weights=cfg['weights']; p=df('portfolio_snapshot'); c=df('counterparty_snapshot'); macro=df('macroeconomic_scenarios')
    p=p[p.as_of_date.astype(str).eq(asof)].merge(c[c.as_of_date.astype(str).eq(asof)],on='counterparty_id',how='left')
    stage=np.where((p.default_flag.eq(1))|(p.days_past_due>=cfg.get('stage3_dpd',90)),3,np.where((p.days_past_due>=cfg.get('stage2_dpd',30))|(p.watchlist_flag.eq(1))|(p.forbearance_flag.eq(1)),2,1))
    retail=p.segment.eq('RETAIL'); raw=np.where(retail,-3.4+.012*(700-p.fico_score.fillna(700))+.018*p.days_past_due+1.3*p.dti.fillna(.35),-3.2+.22*(p.rating_notch.fillna(5)-5)+.09*p.debt_to_equity.fillna(1.5)-.06*p.interest_coverage_ratio.fillna(2.5)+.018*p.days_past_due)
    rid=f"{cfg.get('framework','IFRS9')}_{asof.replace('-','')}_{datetime.now(timezone.utc).strftime('%H%M%S')}_{uuid.uuid4().hex[:5]}"
    out=[]
    for s,w in weights.items():
        mm=macro[(macro.forecast_vintage.astype(str).eq(asof))&(macro.scenario.eq(s))].groupby('variable').value.mean()
        un=float(mm.get('unemployment_rate',4.1)); gdp=float(mm.get('real_gdp_growth',2.2)); hpi=float(mm.get('hpi_growth',3)); spread=float(mm.get('bbb_spread',1.7))
        shift=np.where(retail,.16*(un-4.1)-.04*(hpi-3),.12*(un-4.1)-.12*(gdp-2.2)+.17*(spread-1.7)); pd12=np.clip(1/(1+np.exp(-(raw+shift))),.0003,.65)
        life=np.clip(1-(1-pd12)**np.where(stage==1,1,5),pd12,.95); lgd=np.clip(np.where(p.collateral_value.fillna(0)>0,.2+.55*np.clip(p.ltv.fillna(1)-.6,0,1),.62)+.03*(un-4.1),.08,.95); ead=p.current_balance+.6*p.undrawn_amount.fillna(0); ecl=ead*life*lgd
        out.append(pd.DataFrame({'run_id':rid,'as_of_date':asof,'instrument_id':p.instrument_id,'counterparty_id':p.counterparty_id,'product_type':p.product_type,'scenario':s,'scenario_weight':w,'stage':stage,'pd_12m':pd12,'pd_applied':life,'lgd':lgd,'ead':ead,'scenario_ecl':ecl,'weighted_ecl':ecl*w}))
    res=pd.concat(out,ignore_index=True); overlay=float(cfg.get('management_overlay',0)); total=float(res.weighted_ecl.sum()+overlay); exp=float(res.drop_duplicates('instrument_id').ead.sum())
    return rid,res,total,exp

@app.route('/run',methods=['POST'])
def run():
    cfg=request.get_json(force=True); rid,res,total,exp=formula_run(cfg); manifests=df('cecl_run_manifest')
    row={'run_id':rid,'framework':cfg.get('framework','IFRS9'),'as_of_date':cfg['as_of_date'],'status':'SANDBOX','is_official':0,'parent_run_id':cfg.get('parent_run_id',''),'scenario_weights':json.dumps(cfg['weights']),'stage_rule_version':'WEBAPP','model_group_version':cfg.get('model_group_version','CUSTOM'),'management_overlay':float(cfg.get('management_overlay',0)),'solution_bundle_version':cfg.get('bundle_version','ECL_APP_DEV'),'created_by':'webapp','created_at':datetime.now(timezone.utc).isoformat(),'configuration_fingerprint':uuid.uuid4().hex[:16],'total_exposure':exp,'total_ecl':total}
    write('cecl_run_manifest',pd.concat([manifests,pd.DataFrame([row])],ignore_index=True)); write('cecl_instrument_results',pd.concat([df('cecl_instrument_results'),res],ignore_index=True)); return jsonify(row)

@app.route('/promote/<run_id>',methods=['POST'])
def promote(run_id):
    m=df('cecl_run_manifest'); hit=m.run_id.eq(run_id)
    if not hit.any(): return jsonify({'error':'Run not found'}),404
    asof=m.loc[hit,'as_of_date'].iloc[0]; current=(m.as_of_date.astype(str).eq(str(asof)))&(m.status.eq('PRODUCTION')); m.loc[current,'status']='SUPERSEDED'; m.loc[current,'is_official']=0; m.loc[hit,'status']='PRODUCTION'; m.loc[hit,'is_official']=1; write('cecl_run_manifest',m); return jsonify({'ok':True,'run_id':run_id})
