from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / 'datasets'
OUT.mkdir(exist_ok=True)
SCENS = ['Baseline','Downside','Severe']

# -----------------------------------------------------------------------------
# Fixed parameter sets: PD, LGD and CCF can be fixed by product and category.
# -----------------------------------------------------------------------------
rows=[]
def add_fixed(set_id,label,product,param,base_by_cat,field='ALL',mult=(1.0,1.25,1.65)):
    for scen,m in zip(SCENS,mult):
        for cat,v in base_by_cat.items():
            rows.append(dict(parameter_set_id=set_id,parameter_set_label=label,product_type=product,
                             parameter_type=param,scenario=scen,category_field=field,
                             category_value=cat,value=float(np.clip(v*m,0,0.99)),
                             parameter_version='V2',source_type='SYNTHETIC_DEMO'))

add_fixed('FIXED_PD_PERSONAL_V2','Personal loan PD by FICO band','Personal Loan','PD_12M',
          {'Prime':0.012,'Near Prime':0.035,'Subprime':0.085},'fico_band',(1,1.35,1.9))
add_fixed('FIXED_PD_EQUIPMENT_V2','Equipment lease PD by Moody\'s band','Equipment Lease','PD_12M',
          {'Aaa-A':0.006,'Baa':0.014,'Ba':0.040,'B':0.085,'Caa':0.18},'moodys_band',(1,1.35,1.8))
add_fixed('FIXED_LGD_SECURED_V2','Secured LGD','*','LGD',{'ALL':0.32},'ALL',(1,1.08,1.18))
add_fixed('FIXED_LGD_UNSECURED_V2','Unsecured LGD','*','LGD',{'ALL':0.68},'ALL',(1,1.05,1.10))
add_fixed('FIXED_LGD_CRE_V2','CRE LGD','Commercial Real Estate','LGD',{'ALL':0.38},'ALL',(1,1.12,1.24))
add_fixed('FIXED_CCF_CARD_V2','Credit card CCF','Credit Card','CCF',{'ALL':0.55},'ALL',(1,1.08,1.15))
add_fixed('FIXED_CCF_REVOLVING_V2','Commercial revolving CCF','Revolving Credit Facility','CCF',{'ALL':0.65},'ALL',(1,1.08,1.16))
pd.DataFrame(rows).to_csv(OUT/'fixed_parameter_values.csv',index=False)

# -----------------------------------------------------------------------------
# Prepayment curves by product, scenario, and optional risk bucket.
# -----------------------------------------------------------------------------
pp=[]
def add_pp(curve_id,label,product,bucket_field,buckets,max_month,base_cpr):
    for scen,sm in zip(SCENS,[1.0,0.82,0.62]):
        for bi,b in enumerate(buckets):
            bucket_mult=max(0.65,1.10-0.13*bi)
            surv=1.0
            for month in range(1,max_month+1):
                ramp=min(month/18,1.0)
                seasoning=1.0 + 0.10*np.sin(month/12)
                cpr=float(np.clip(base_cpr*ramp*seasoning*sm*bucket_mult,0.002,0.30))
                smm=1-(1-cpr)**(1/12)
                surv*=1-smm
                pp.append(dict(curve_id=curve_id,curve_label=label,product_type=product,
                               bucket_field=bucket_field,bucket_value=b,scenario=scen,month=month,
                               annual_cpr=cpr,monthly_smm=smm,cumulative_survival=surv,
                               curve_version='V2',source_type='SYNTHETIC_DEMO'))
add_pp('PP_MORTGAGE_FICO_V2','Mortgage prepayment by FICO','Mortgage','fico_band',['Prime','Near Prime','Subprime'],120,0.10)
add_pp('PP_AUTO_FICO_V2','Auto prepayment by FICO','Auto Loan','fico_band',['Prime','Near Prime','Subprime'],60,0.15)
add_pp('PP_COMM_MOODYS_V2','Commercial term prepayment by Moody\'s','Commercial Term Loan','moodys_band',['Aaa-A','Baa','Ba','B','Caa'],84,0.065)
add_pp('PP_EQUIPMENT_ALL_V2','Equipment lease prepayment','Equipment Lease','ALL',['ALL'],60,0.055)
pd.DataFrame(pp).to_csv(OUT/'prepayment_curves.csv',index=False)

# -----------------------------------------------------------------------------
# Lifetime PD curves. Curves are cumulative/marginal, bucketed by a chosen field.
# -----------------------------------------------------------------------------
lpd=[]
def add_lpd(curve_id,label,product,bucket_field,bucket_rates,max_month):
    for scen,sm in zip(SCENS,[1.0,1.45,2.15]):
        for bucket,annual_pd in bucket_rates.items():
            surv=1.0
            for month in range(1,max_month+1):
                # slight hazard seasoning, converted from annual to monthly hazard
                seasonal=1.0 + 0.18*(1-np.exp(-month/24))
                annual=float(np.clip(annual_pd*sm*seasonal,0.0002,0.65))
                hazard=1-(1-annual)**(1/12)
                marginal=surv*hazard
                surv*=1-hazard
                lpd.append(dict(curve_id=curve_id,curve_label=label,product_type=product,
                                bucket_field=bucket_field,risk_bucket=bucket,scenario=scen,month=month,
                                marginal_pd=marginal,cumulative_pd=1-surv,curve_version='V2',source_type='SYNTHETIC_DEMO'))
add_lpd('LPD_MORTGAGE_FICO_V2','Mortgage lifetime PD by FICO','Mortgage','fico_band',
        {'Prime':0.006,'Near Prime':0.018,'Subprime':0.065},120)
add_lpd('LPD_CRE_MOODYS_V2','CRE lifetime PD by Moody\'s','Commercial Real Estate','moodys_band',
        {'Aaa-A':0.004,'Baa':0.010,'Ba':0.030,'B':0.070,'Caa':0.18},120)
add_lpd('LPD_REVOLVING_MOODYS_V2','Revolving lifetime PD by Moody\'s','Revolving Credit Facility','moodys_band',
        {'Aaa-A':0.005,'Baa':0.014,'Ba':0.040,'B':0.090,'Caa':0.20},84)
pd.DataFrame(lpd).to_csv(OUT/'lifetime_pd_curves.csv',index=False)

# -----------------------------------------------------------------------------
# Transition matrices. State field is configurable (FICO or Moody's bands).
# -----------------------------------------------------------------------------
tm=[]
def normalize(v):
    a=np.array(v,dtype=float); a=np.clip(a,0,None); return a/a.sum()
def add_matrix(matrix_id,label,product,state_field,states,baseline_rows):
    for scen,stress in zip(SCENS,[1.0,1.25,1.65]):
        for fs,base in baseline_rows.items():
            vals=np.array(base,dtype=float)
            if fs!='Default':
                # Increase default probability under stress and take mass mainly from staying probability.
                d_idx=states.index('Default'); extra=vals[d_idx]*(stress-1)
                vals[d_idx]+=extra
                stay_idx=states.index(fs)
                vals[stay_idx]=max(0.001,vals[stay_idx]-extra)
            vals=normalize(vals)
            for ts,p in zip(states,vals):
                tm.append(dict(matrix_id=matrix_id,matrix_label=label,product_type=product,
                               state_field=state_field,scenario=scen,from_state=fs,to_state=ts,
                               annual_probability=float(p),matrix_version='V2',source_type='SYNTHETIC_DEMO'))

states=['Prime','Near Prime','Subprime','Default']
add_matrix('TM_AUTO_FICO_V2','Auto transition by FICO band','Auto Loan','fico_band',states,{
    'Prime':[0.90,0.075,0.018,0.007],
    'Near Prime':[0.15,0.72,0.095,0.035],
    'Subprime':[0.04,0.12,0.70,0.14],
    'Default':[0,0,0,1],
})
add_matrix('TM_MORTGAGE_FICO_V2','Mortgage transition by FICO band','Mortgage','fico_band',states,{
    'Prime':[0.93,0.055,0.010,0.005],
    'Near Prime':[0.16,0.75,0.065,0.025],
    'Subprime':[0.05,0.14,0.71,0.10],
    'Default':[0,0,0,1],
})

states2=['Aaa-A','Baa','Ba','B','Caa','Default']
add_matrix('TM_COMM_MOODYS_V2','Commercial term transition by Moody\'s band','Commercial Term Loan','moodys_band',states2,{
    'Aaa-A':[0.91,0.075,0.010,0.002,0.001,0.002],
    'Baa':[0.055,0.84,0.075,0.020,0.004,0.006],
    'Ba':[0.010,0.075,0.79,0.090,0.020,0.015],
    'B':[0.002,0.015,0.090,0.75,0.090,0.053],
    'Caa':[0.001,0.004,0.015,0.090,0.64,0.25],
    'Default':[0,0,0,0,0,1],
})
add_matrix('TM_EQUIPMENT_MOODYS_V2','Equipment lease transition by Moody\'s band','Equipment Lease','moodys_band',states2,{
    'Aaa-A':[0.92,0.068,0.007,0.001,0.001,0.003],
    'Baa':[0.050,0.85,0.070,0.018,0.004,0.008],
    'Ba':[0.010,0.070,0.80,0.080,0.020,0.020],
    'B':[0.002,0.012,0.080,0.76,0.085,0.061],
    'Caa':[0.001,0.003,0.012,0.080,0.65,0.254],
    'Default':[0,0,0,0,0,1],
})
pd.DataFrame(tm).to_csv(OUT/'transition_matrices.csv',index=False)

# -----------------------------------------------------------------------------
# Method configuration: every portfolio can mix fixed, Visual ML, curve/matrix,
# and prepayment techniques. Saved Model IDs are placeholders if not present.
# -----------------------------------------------------------------------------
method_rows=[
 dict(product_type='Mortgage',pd_method='LIFETIME_PD_CURVE',pd_source_id='LPD_MORTGAGE_FICO_V2',pd_source_version='V2',pd_category_field='fico_band',transition_matrix_id='',transition_state_field='',lgd_method='FIXED',lgd_source_id='FIXED_LGD_SECURED_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='CURVE',prepayment_curve_id='PP_MORTGAGE_FICO_V2',prepayment_category_field='fico_band'),
 dict(product_type='Auto Loan',pd_method='TRANSITION_MATRIX',pd_source_id='',pd_source_version='',pd_category_field='fico_band',transition_matrix_id='TM_AUTO_FICO_V2',transition_state_field='fico_band',lgd_method='FIXED',lgd_source_id='FIXED_LGD_SECURED_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='CURVE',prepayment_curve_id='PP_AUTO_FICO_V2',prepayment_category_field='fico_band'),
 dict(product_type='Personal Loan',pd_method='FIXED',pd_source_id='FIXED_PD_PERSONAL_V2',pd_source_version='V2',pd_category_field='fico_band',transition_matrix_id='',transition_state_field='',lgd_method='FIXED',lgd_source_id='FIXED_LGD_UNSECURED_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='NONE',prepayment_curve_id='',prepayment_category_field=''),
 dict(product_type='Credit Card',pd_method='SAVED_MODEL',pd_source_id='PD_RETAIL',pd_source_version='LATEST',pd_category_field='',transition_matrix_id='',transition_state_field='',lgd_method='FIXED',lgd_source_id='FIXED_LGD_UNSECURED_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CCF_FIXED',ead_source_id='FIXED_CCF_CARD_V2',ead_source_version='V2',prepayment_method='NONE',prepayment_curve_id='',prepayment_category_field=''),
 dict(product_type='Commercial Term Loan',pd_method='TRANSITION_MATRIX',pd_source_id='',pd_source_version='',pd_category_field='moodys_band',transition_matrix_id='TM_COMM_MOODYS_V2',transition_state_field='moodys_band',lgd_method='SAVED_MODEL',lgd_source_id='LGD_COMMERCIAL',lgd_source_version='LATEST',lgd_category_field='',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='CURVE',prepayment_curve_id='PP_COMM_MOODYS_V2',prepayment_category_field='moodys_band'),
 dict(product_type='Commercial Real Estate',pd_method='LIFETIME_PD_CURVE',pd_source_id='LPD_CRE_MOODYS_V2',pd_source_version='V2',pd_category_field='moodys_band',transition_matrix_id='',transition_state_field='',lgd_method='FIXED',lgd_source_id='FIXED_LGD_CRE_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='NONE',prepayment_curve_id='',prepayment_category_field=''),
 dict(product_type='Equipment Lease',pd_method='FIXED',pd_source_id='FIXED_PD_EQUIPMENT_V2',pd_source_version='V2',pd_category_field='moodys_band',transition_matrix_id='',transition_state_field='',lgd_method='FIXED',lgd_source_id='FIXED_LGD_SECURED_V2',lgd_source_version='V2',lgd_category_field='ALL',ead_method='CONTRACTUAL',ead_source_id='',ead_source_version='',prepayment_method='CURVE',prepayment_curve_id='PP_EQUIPMENT_ALL_V2',prepayment_category_field='ALL'),
 dict(product_type='Revolving Credit Facility',pd_method='LIFETIME_PD_CURVE',pd_source_id='LPD_REVOLVING_MOODYS_V2',pd_source_version='V2',pd_category_field='moodys_band',transition_matrix_id='',transition_state_field='',lgd_method='SAVED_MODEL',lgd_source_id='LGD_COMMERCIAL',lgd_source_version='LATEST',lgd_category_field='',ead_method='CCF_FIXED',ead_source_id='FIXED_CCF_REVOLVING_V2',ead_source_version='V2',prepayment_method='NONE',prepayment_curve_id='',prepayment_category_field=''),
]
md=pd.DataFrame(method_rows)
md.insert(0,'config_version','METHODCFG_V2')
md['created_at']='2026-09-02T00:00:00Z'; md['created_by']='demo.generator'; md['notes']='Mixed fixed / Saved Model / curve / transition-matrix configuration'
md.to_csv(OUT/'ecl_method_config.csv',index=False)

# -----------------------------------------------------------------------------
# ECL math config: this is the UDL-style calculation contract.
# The demo backend uses an equivalent vectorized runtime, while a warehouse Flow
# can implement the same contract with visual/SQL recipes.
# -----------------------------------------------------------------------------
math=[]
for p in ['Mortgage','Auto Loan','Personal Loan','Credit Card','Commercial Term Loan','Commercial Real Estate','Equipment Lease','Revolving Credit Facility']:
    commercial=p in ['Commercial Term Loan','Commercial Real Estate','Equipment Lease','Revolving Credit Facility']
    math.append(dict(math_config_version='MATHCFG_V2',product_type=p,
        loop_level='COUNTERPARTY_INSTRUMENT_MONTH' if commercial else 'INSTRUMENT_MONTH',
        parent_key='counterparty_id',entity_key='instrument_id',child_key='installment_id' if p not in ['Credit Card','Revolving Credit Facility'] else '',
        time_step='MONTHLY',horizon_method='IFRS9_STAGE_OR_CECL_LIFETIME',pd_application='MARGINAL_OR_CUMULATIVE_BY_METHOD',
        discount_method='EFFECTIVE_INTEREST_RATE',discount_rate_field='interest_rate',
        ecl_formula='MARGINAL_PD * LGD * EAD * DISCOUNT_FACTOR',aggregation_level='INSTRUMENT_THEN_PORTFOLIO',
        execution_semantics='VECTORIZED_EQUIVALENT_IN_DEMO',status='APPROVED_DEMO',
        notes='UDL-style math contract; warehouse recipe/scenario may implement exact month-by-month expansion'))
pd.DataFrame(math).to_csv(OUT/'ecl_math_config.csv',index=False)

# -----------------------------------------------------------------------------
# Execution profiles. Warehouse profiles are safe opt-ins and fall back to DSS
# Python unless a scenario is explicitly wired in the backend/project.
# -----------------------------------------------------------------------------
exec_rows=[
 dict(profile_id='EXEC_AUTO',profile_label='Auto - prefer warehouse when wired',engine_type='AUTO',scenario_id='',connection_mode='PORTFOLIO_DATASET',allow_python_fallback=1,enabled=1,notes='Safe default. Uses DSS Python now; can route to warehouse scenario later.'),
 dict(profile_id='EXEC_DSS_PYTHON',profile_label='DSS Python - current working engine',engine_type='DSS_PYTHON',scenario_id='',connection_mode='DSS',allow_python_fallback=1,enabled=1,notes='Always available and preserves current behavior.'),
 dict(profile_id='EXEC_SQL_IN_DB',profile_label='SQL in-database - eligibility / future adapter',engine_type='SQL_IN_DATABASE',scenario_id='',connection_mode='PORTFOLIO_DATASET',allow_python_fallback=1,enabled=1,notes='Records SQL intent; safe Python fallback unless SQL adapter is explicitly enabled.'),
 dict(profile_id='EXEC_WAREHOUSE_FLOW',profile_label='Warehouse Flow / Scenario',engine_type='DSS_SCENARIO',scenario_id='ECL_WAREHOUSE_RUN',connection_mode='PORTFOLIO_DATASET',allow_python_fallback=1,enabled=1,notes='Wire this scenario to Visual/SQL recipes with Snowflake/Databricks engines. If missing, webapp falls back safely.'),
]
pd.DataFrame(exec_rows).to_csv(OUT/'ecl_execution_profiles.csv',index=False)

# Empty request queue for future scenario orchestration.
pd.DataFrame(columns=['request_id','requested_at','requested_by','framework','as_of_date','method_config_version','math_config_version','execution_profile_id','status','payload_json']).to_csv(OUT/'ecl_run_requests.csv',index=False)

print('Generated', len(list(OUT.glob('*.csv'))), 'CSV files')
