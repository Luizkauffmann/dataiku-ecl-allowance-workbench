from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from openpyxl import Workbook

SEED=90210
rng=np.random.default_rng(SEED)
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'datasets'; OUT.mkdir(exist_ok=True)
DATES=pd.to_datetime(['2026-06-30','2026-07-31','2026-08-31'])
PRODUCTS=['Mortgage','Auto Loan','Personal Loan','Credit Card','Commercial Term Loan','Commercial Real Estate','Equipment Lease','Revolving Credit Facility']
RETAIL=set(PRODUCTS[:4]); SCENS=['Baseline','Downside','Severe']

# Counterparties
n_ind,n_cor=1700,650
base=[]
for i in range(n_ind):
    base.append(dict(counterparty_id=f'CP-I-{i+1:05d}',counterparty_type='INDIVIDUAL',state=rng.choice(['NC','TX','CA','FL','NY','GA','VA']),annual_income=float(np.exp(rng.normal(np.log(90000),.45))),fico_score=int(np.clip(rng.normal(710,55),500,840)),dti=float(np.clip(rng.beta(3,5)*.75,.05,.75)),annual_revenue=np.nan,total_assets=np.nan,total_liabilities=np.nan,ebitda=np.nan,number_employees=np.nan,industry=np.nan,rating_notch=np.nan,sp_rating=np.nan,moodys_rating=np.nan,debt_to_equity=np.nan,interest_coverage_ratio=np.nan,current_ratio=np.nan))
ratings=['AAA','AA','A','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC']; moodys=['Aaa','Aa2','A2','Baa1','Baa2','Baa3','Ba1','Ba2','Ba3','B1','B2','B3','Caa1']
for i in range(n_cor):
    rev=float(np.exp(rng.normal(np.log(45e6),.9))); assets=rev*rng.uniform(.7,1.7); lev=float(np.clip(rng.lognormal(.45,.45),.2,8)); cov=float(np.clip(rng.lognormal(.9,.55),.3,15)); notch=int(np.clip(round(4.5+1.3*np.log1p(lev)-.55*np.log1p(cov)+rng.normal(0,1.2)),1,13))
    base.append(dict(counterparty_id=f'CP-C-{i+1:05d}',counterparty_type='CORPORATE',state=rng.choice(['NC','TX','CA','FL','NY','GA','VA']),annual_income=np.nan,fico_score=np.nan,dti=np.nan,annual_revenue=rev,total_assets=assets,total_liabilities=assets*lev/(1+lev),ebitda=rev*rng.uniform(.06,.25),number_employees=int(max(8,rev/rng.uniform(150000,350000))),industry=rng.choice(['Manufacturing','Retail','Healthcare','Technology','Construction','Transportation','Hospitality','Real Estate']),rating_notch=notch,sp_rating=ratings[notch-1],moodys_rating=moodys[notch-1],debt_to_equity=lev,interest_coverage_ratio=cov,current_ratio=float(np.clip(rng.normal(1.6,.5),.4,4))))
base=pd.DataFrame(base)
cp=[]
for di,d in enumerate(DATES):
    x=base.copy(); x['as_of_date']=d.date().isoformat(); stressed=rng.random(len(x)) < [.08,.13,.20][di]; ind=x.counterparty_type.eq('INDIVIDUAL'); cor=~ind
    x.loc[ind,'fico_score']=(x.loc[ind,'fico_score']-stressed[ind]*rng.uniform(5,28,ind.sum())+rng.normal(0,2,ind.sum())).clip(480,850)
    x.loc[ind,'dti']=(x.loc[ind,'dti']+stressed[ind]*rng.uniform(.01,.08,ind.sum())).clip(.02,.9)
    x.loc[cor,'rating_notch']=(x.loc[cor,'rating_notch']+stressed[cor]*rng.integers(0,3,cor.sum())).clip(1,13)
    x.loc[cor,'debt_to_equity']*=1+stressed[cor]*rng.uniform(.02,.20,cor.sum()); x.loc[cor,'interest_coverage_ratio']*=1-stressed[cor]*rng.uniform(.02,.22,cor.sum())
    for j in x.index[cor]:
        n=int(x.at[j,'rating_notch']); x.at[j,'sp_rating']=ratings[n-1]; x.at[j,'moodys_rating']=moodys[n-1]
    cp.append(x)
counterparty_snapshot=pd.concat(cp,ignore_index=True)

# Instruments and monthly portfolio
ind_ids=base.loc[base.counterparty_type.eq('INDIVIDUAL'),'counterparty_id'].to_numpy(); cor_ids=base.loc[base.counterparty_type.eq('CORPORATE'),'counterparty_id'].to_numpy(); inst=[]
for i in range(2800):
    p=rng.choice(PRODUCTS,p=[.27,.13,.10,.14,.13,.08,.07,.08]); retail=p in RETAIL; cp_id=rng.choice(ind_ids if retail else cor_ids)
    if p=='Mortgage': bal=np.exp(rng.normal(np.log(300000),.55)); term=360; coll='Residential Real Estate'
    elif p=='Auto Loan': bal=np.exp(rng.normal(np.log(34000),.45)); term=60; coll='Vehicle'
    elif p=='Personal Loan': bal=np.exp(rng.normal(np.log(18000),.5)); term=48; coll='Unsecured'
    elif p=='Credit Card': bal=np.exp(rng.normal(np.log(9000),.6)); term=120; coll='Unsecured'
    elif p=='Commercial Term Loan': bal=np.exp(rng.normal(np.log(1.5e6),.85)); term=84; coll='Business Assets'
    elif p=='Commercial Real Estate': bal=np.exp(rng.normal(np.log(3.8e6),.9)); term=180; coll='Commercial Real Estate'
    elif p=='Equipment Lease': bal=np.exp(rng.normal(np.log(650000),.75)); term=60; coll='Equipment'
    else: bal=np.exp(rng.normal(np.log(900000),.8)); term=120; coll='Unsecured'
    inst.append(dict(instrument_id=f'LN-{i+1:06d}',counterparty_id=cp_id,product_type=p,segment='RETAIL' if retail else 'COMMERCIAL',original_balance=float(bal),term_months=term,interest_rate=float(rng.uniform(.04,.22)),collateral_type=coll,origination_date=(DATES[0]-pd.Timedelta(days=int(rng.integers(30,2500)))).date().isoformat(),credit_limit=float(bal*rng.uniform(1.1,2.2)) if p in ['Credit Card','Revolving Credit Facility'] else np.nan))
inst=pd.DataFrame(inst); rows=[]
for di,d in enumerate(DATES):
    active=inst.copy()
    if di: active=active.loc[rng.random(len(active))>[.018,.025][di-1]].copy()
    new_n=[0,150,230][di]
    if new_n:
        samp=inst.sample(new_n,replace=True,random_state=SEED+di).copy(); samp['instrument_id']=[f'NEW-{di}-{i:05d}' for i in range(new_n)]; samp['origination_date']=(d-pd.Timedelta(days=10)).date().isoformat(); active=pd.concat([active,samp],ignore_index=True)
    cp_d=counterparty_snapshot[counterparty_snapshot.as_of_date.eq(d.date().isoformat())]; m=active.merge(cp_d,on='counterparty_id',how='left',suffixes=('','_cp')); age=((d-pd.to_datetime(m.origination_date)).dt.days/30.4).clip(lower=0); amort=np.minimum(age/m.term_months,.92)
    balance=m.original_balance*(1-.8*amort)*rng.uniform(.96,1.04,len(m)); rev=m.product_type.isin(['Credit Card','Revolving Credit Facility']); balance.loc[rev]=m.loc[rev,'credit_limit']*rng.uniform(.2,.85,rev.sum()); stress=((m.fico_score.fillna(710)<660)|(m.rating_notch.fillna(5)>8))
    dpd=np.where(rng.random(len(m))<(.03+.10*stress),rng.choice([15,30,45,60,90,120],len(m),p=[.25,.25,.15,.13,.13,.09]),0)
    if di==2: dpd=np.where(rng.random(len(m))<.035,np.maximum(dpd,30),dpd)
    default=(dpd>=90)|(rng.random(len(m))<(.003+.012*stress)); collateral=np.where(m.collateral_type.eq('Unsecured'),0,balance*rng.uniform(.75,1.45,len(m)))
    rows.append(pd.DataFrame(dict(as_of_date=d.date().isoformat(),instrument_id=m.instrument_id,counterparty_id=m.counterparty_id,product_type=m.product_type,segment=m.segment,origination_date=m.origination_date,maturity_date=(pd.to_datetime(m.origination_date)+pd.to_timedelta(m.term_months*30.4,unit='D')).dt.date.astype(str),original_balance=m.original_balance,current_balance=balance,undrawn_amount=np.where(rev,(m.credit_limit-balance).clip(lower=0),0),interest_rate=m.interest_rate,days_past_due=dpd,watchlist_flag=((dpd>=30)|stress).astype(int),forbearance_flag=((dpd>=60)&(rng.random(len(m))<.35)).astype(int),default_flag=default.astype(int),chargeoff_flag=((dpd>=120)&(rng.random(len(m))<.45)).astype(int),collateral_type=m.collateral_type,collateral_value=collateral,ltv=np.where(collateral>0,balance/collateral,np.nan),risk_grade=np.where(m.segment.eq('COMMERCIAL'),m.sp_rating,np.nan),state=m.state)))
portfolio_snapshot=pd.concat(rows,ignore_index=True)

# Installments
install=[]
for _,r in inst[~inst.product_type.isin(['Credit Card','Revolving Credit Facility'])].sample(1000,random_state=SEED).iterrows():
    bal=r.original_balance; rate=r.interest_rate/12; n=min(int(r.term_months),36); pmt=bal*rate/(1-(1+rate)**(-r.term_months)) if rate else bal/r.term_months; start=pd.Timestamp(r.origination_date)+pd.offsets.MonthEnd(1)
    for k in range(n):
        interest=bal*rate; principal=max(0,min(bal,pmt-interest)); bal-=principal
        install.append(dict(instrument_id=r.instrument_id,installment_id=f'{r.instrument_id}-{k+1:03d}',scheduled_payment_date=(start+pd.offsets.MonthEnd(k)).date().isoformat(),scheduled_principal=principal,scheduled_interest=interest,scheduled_payment=principal+interest,actual_payment_date='',actual_payment=0,remaining_balance_after_payment=bal,amortization_type='AMORTIZING',payment_frequency='MONTHLY'))
installment_schedule=pd.DataFrame(install)

# Default/recovery history
defhist=[]
for i in range(550):
    p=rng.choice(PRODUCTS); secured=p not in ['Credit Card','Personal Loan','Revolving Credit Facility']; db=float(np.exp(rng.normal(np.log(100000 if p in RETAIL else 900000),.9))); lgd=float(np.clip(rng.beta(2.2,3.2)+(0 if secured else .18),.05,.98)); rec=db*(1-lgd)
    defhist.append(dict(default_event_id=f'DEF-{i+1:05d}',instrument_id=f'HIST-{i+1:06d}',product_type=p,default_date=(pd.Timestamp('2023-01-01')+pd.Timedelta(days=int(rng.integers(0,1200)))).date().isoformat(),default_balance=db,recovery_amount=rec,collection_cost=rec*rng.uniform(.01,.08),collateral_proceeds=rec*rng.uniform(.25,.85) if secured else 0,recovery_horizon_months=int(rng.integers(2,30)),realized_lgd=lgd))
default_recovery_history=pd.DataFrame(defhist)

# Macro scenarios and configs
vars_=['unemployment_rate','real_gdp_growth','hpi_growth','commercial_property_price_growth','bbb_spread','corporate_default_rate']; basevals=dict(unemployment_rate=4.1,real_gdp_growth=2.2,hpi_growth=3.0,commercial_property_price_growth=1.0,bbb_spread=1.7,corporate_default_rate=2.0); macro=[]
for d in DATES:
    for s in SCENS:
        sev={'Baseline':0,'Downside':1,'Severe':2}[s]
        for q in range(1,13):
            period=(d+pd.offsets.QuarterEnd(q)).to_period('Q').strftime('%YQ%q')
            for v in vars_:
                impact={'unemployment_rate':1.3,'real_gdp_growth':-1.8,'hpi_growth':-4.0,'commercial_property_price_growth':-5.2,'bbb_spread':1.2,'corporate_default_rate':1.6}[v]; val=basevals[v]+impact*sev*(1-np.exp(-q/4))
                if d==DATES[2]: val+=({'unemployment_rate':.35,'real_gdp_growth':-.4,'hpi_growth':-.8,'commercial_property_price_growth':-1.2,'bbb_spread':.25,'corporate_default_rate':.3}[v])*max(sev,1)
                macro.append(dict(forecast_vintage=d.date().isoformat(),scenario=s,period=period,geography='US',variable=v,value=float(val)))
macroeconomic_scenarios=pd.DataFrame(macro)
scenario_config=pd.DataFrame([dict(as_of_date=d.date().isoformat(),scenario=s,weight=w,rs_horizon_months=24,reversion_method='STRAIGHT_LINE',reversion_months=24) for d,weights in zip(DATES,[(.7,.2,.1),(.65,.23,.12),(.55,.28,.17)]) for s,w in zip(SCENS,weights)])
stage_rules=pd.DataFrame([dict(rule_version='IFRS9_STAGE_V1',stage2_dpd=30,stage3_dpd=90,pd_ratio_trigger=2.0,rating_downgrade_notches=3,watchlist_trigger=1,forbearance_trigger=1)]); ratings_mapping=pd.DataFrame(dict(rating_notch=range(1,14),sp_rating=ratings,moodys_rating=moodys)); model_group_config=pd.DataFrame([dict(product_type=p,pd_model='DEMO_FORMULA',pd_version='formula-v1',lgd_model='DEMO_FORMULA',lgd_version='formula-v1',ead_method='CCF_60' if p in ['Credit Card','Revolving Credit Facility'] else 'CONTRACTUAL',ead_model='',ead_version='') for p in PRODUCTS])

# ECL engine
def macro_val(vintage,scenario,var):
    z=macroeconomic_scenarios.query('forecast_vintage==@vintage and scenario==@scenario and variable==@var'); return float(z.iloc[:4].value.mean())

def calc_run(asof,weights,run_id,status='PRODUCTION',overlay=0):
    p=portfolio_snapshot[portfolio_snapshot.as_of_date.eq(asof)].copy(); c=counterparty_snapshot[counterparty_snapshot.as_of_date.eq(asof)]; p=p.merge(c,on='counterparty_id',how='left')
    risk=np.where(p.segment.eq('RETAIL'),-3.4+.012*(700-p.fico_score.fillna(700))+.018*p.days_past_due+1.3*p.dti.fillna(.35),-3.2+.22*(p.rating_notch.fillna(5)-5)+.09*p.debt_to_equity.fillna(1.5)-.06*p.interest_coverage_ratio.fillna(2.5)+.018*p.days_past_due); stage=np.where((p.default_flag.eq(1))|(p.days_past_due>=90),3,np.where((p.days_past_due>=30)|(p.watchlist_flag.eq(1))|(p.forbearance_flag.eq(1)),2,1)); out=[]
    for s,w in zip(SCENS,weights):
        un=macro_val(asof,s,'unemployment_rate'); gdp=macro_val(asof,s,'real_gdp_growth'); hpi=macro_val(asof,s,'hpi_growth'); spread=macro_val(asof,s,'bbb_spread'); macro_shift=np.where(p.segment.eq('RETAIL'),.16*(un-4.1)-.04*(hpi-3),.12*(un-4.1)-.12*(gdp-2.2)+.17*(spread-1.7)); pd12=np.clip(1/(1+np.exp(-(risk+macro_shift))),.0003,.65); lifetime=np.clip(1-(1-pd12)**np.where(stage==1,1,np.minimum(8,np.maximum(2,(pd.to_datetime(p.maturity_date)-pd.Timestamp(asof)).dt.days/365))),pd12,.95); lgd=np.clip(np.where(p.collateral_value.fillna(0)>0,.2+.55*np.clip(p.ltv.fillna(1)-.6,0,1),.62)+.03*(un-4.1),.08,.95); ead=p.current_balance+.6*p.undrawn_amount.fillna(0); ecl=ead*lifetime*lgd
        out.append(pd.DataFrame(dict(run_id=run_id,as_of_date=asof,instrument_id=p.instrument_id,counterparty_id=p.counterparty_id,product_type=p.product_type,scenario=s,scenario_weight=w,stage=stage,pd_12m=pd12,pd_applied=lifetime,lgd=lgd,ead=ead,scenario_ecl=ecl,weighted_ecl=ecl*w)))
    r=pd.concat(out,ignore_index=True); total=r.weighted_ecl.sum()+overlay; return r,total,float(r.drop_duplicates('instrument_id').ead.sum())

runs=[]; results=[]; run_specs=[('2026-06-30',[.7,.2,.1],'IFRS9_20260630_FINAL_V1','PRODUCTION',0),('2026-07-31',[.65,.23,.12],'IFRS9_20260731_FINAL_V1','PRODUCTION',4e5),('2026-08-31',[.55,.28,.17],'IFRS9_20260831_FINAL_V1','PRODUCTION',9e5),('2026-08-31',[.45,.30,.25],'IFRS9_20260831_WHATIF_V1','SANDBOX',9e5)]
for asof,w,rid,status,overlay in run_specs:
    rr,ecl,exp=calc_run(asof,w,rid,status,overlay); results.append(rr); cfg=json.dumps(dict(asof=asof,weights=w,overlay=overlay),sort_keys=True); runs.append(dict(run_id=rid,framework='IFRS9',as_of_date=asof,status=status,is_official=int(status=='PRODUCTION'),parent_run_id='',scenario_weights='/'.join(map(str,w)),stage_rule_version='IFRS9_STAGE_V1',model_group_version='DEMO_V1',management_overlay=overlay,solution_bundle_version='ECL_APP_1.0.0',created_by='demo',created_at='2026-08-31T12:00:00Z',configuration_fingerprint=hashlib.sha256(cfg.encode()).hexdigest()[:16],total_exposure=exp,total_ecl=ecl))
cecl_run_manifest=pd.DataFrame(runs); cecl_instrument_results=pd.concat(results,ignore_index=True)

def attr(fr,to):
    a=cecl_run_manifest.set_index('run_id').loc[fr]; b=cecl_run_manifest.set_index('run_id').loc[to]; delta=b.total_ecl-a.total_ecl; shares=np.array([.24,.15,.43,.13,.05]); vals=delta*shares; cats=['Portfolio / Exposure','Credit quality','Macroeconomic scenario paths','Scenario weights','Management overlay']; rows=[dict(comparison_id=f'{fr}__{to}',from_run_id=fr,to_run_id=to,level=1,parent_category='',category=c,amount=float(v),sort_order=i+1) for i,(c,v) in enumerate(zip(cats,vals))]
    for s,sh in zip(SCENS,[.2,.45,.35]): rows.append(dict(comparison_id=f'{fr}__{to}',from_run_id=fr,to_run_id=to,level=2,parent_category='Macroeconomic scenario paths',category=s,amount=float(vals[2]*sh),sort_order=1))
    drivers=['Unemployment','GDP','House Price Index','Commercial Property Prices','BBB Spread','Corporate Default Rate']
    for s,sh in zip(SCENS,[.2,.45,.35]):
        for j,d in enumerate(drivers): rows.append(dict(comparison_id=f'{fr}__{to}',from_run_id=fr,to_run_id=to,level=3,parent_category=f'Macroeconomic scenario paths::{s}',category=d,amount=float(vals[2]*sh/len(drivers)),sort_order=j+1))
    for j,d in enumerate(['FICO','DTI','Delinquency','Watchlist / forbearance','Rating','Leverage','Interest coverage','LTV']): rows.append(dict(comparison_id=f'{fr}__{to}',from_run_id=fr,to_run_id=to,level=2,parent_category='Credit quality',category=d,amount=float(vals[1]/8),sort_order=j+1))
    return rows
cecl_attribution_results=pd.DataFrame(attr('IFRS9_20260630_FINAL_V1','IFRS9_20260731_FINAL_V1')+attr('IFRS9_20260731_FINAL_V1','IFRS9_20260831_FINAL_V1')); cecl_feature_contributions=pd.DataFrame([dict(run_id='IFRS9_20260831_FINAL_V1',model_family='PD',feature_name=f,contribution=v) for f,v in [('FICO',.22),('Delinquency',.20),('Rating',.18),('Unemployment',.16),('Leverage',.13),('HPI',.11)]])

# Write datasets and data dictionary
datasets=locals().copy(); names=['portfolio_snapshot','counterparty_snapshot','installment_schedule','default_recovery_history','macroeconomic_scenarios','scenario_config','stage_rules','ratings_mapping','model_group_config','cecl_run_manifest','cecl_instrument_results','cecl_feature_contributions','cecl_attribution_results']
for n in names: datasets[n].to_csv(OUT/f'{n}.csv',index=False)
summary={n:{'rows':len(datasets[n]),'columns':len(datasets[n].columns)} for n in names}; (ROOT/'dataset_summary.json').write_text(json.dumps(summary,indent=2))
wb=Workbook(); ws=wb.active; ws.title='Catalog'; ws.append(['Dataset','Rows','Columns','Grain / purpose']); purpose={'portfolio_snapshot':'as_of_date + instrument_id','counterparty_snapshot':'as_of_date + counterparty_id','installment_schedule':'instrument_id + installment_id','default_recovery_history':'default event','macroeconomic_scenarios':'vintage + scenario + period + variable','cecl_run_manifest':'one row per run','cecl_instrument_results':'run + instrument + scenario'}
for n in names: ws.append([n,len(datasets[n]),len(datasets[n].columns),purpose.get(n,'configuration / reference / analysis')])
for n in names:
    sh=wb.create_sheet(n[:31]); sh.append(['Column','Example','dtype']); frame=datasets[n]
    for c in frame.columns:
        vals=frame[c].dropna(); sh.append([c,str(vals.iloc[0])[:100] if len(vals) else '',str(frame[c].dtype)])
wb.save(ROOT/'ECL_demo_data_dictionary.xlsx'); print(json.dumps(summary,indent=2)); print(cecl_run_manifest[['run_id','total_exposure','total_ecl']].to_string(index=False))
