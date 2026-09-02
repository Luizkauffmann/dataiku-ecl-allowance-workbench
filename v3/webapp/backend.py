import hashlib
import json
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from flask import jsonify, request
import dataiku

# ----------------------------------------------------------------------------
# Dataset names. Change here if your DSS datasets use different names.
# ----------------------------------------------------------------------------
NAMES = {
    k: k for k in [
        'portfolio_snapshot', 'counterparty_snapshot', 'macroeconomic_scenarios',
        'scenario_config', 'stage_rules', 'model_group_config',
        'cecl_run_manifest', 'cecl_instrument_results', 'cecl_attribution_results',
        'prepayment_curves', 'lifetime_pd_curves', 'transition_matrices',
        'fixed_parameter_values', 'ecl_method_config', 'ecl_math_config',
        'ecl_execution_profiles', 'ecl_run_requests',
        'cecl_governance_status', 'cecl_release_log'
    ]
}

SCENARIOS = ['Baseline', 'Downside', 'Severe']


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def current_user():
    try:
        info = dataiku.api_client().get_auth_info()
        return info.get('authIdentifier') or info.get('displayName') or 'webapp.user'
    except Exception:
        return 'webapp.user'


def df(name):
    return dataiku.Dataset(NAMES[name]).get_dataframe()


def maybe_df(name, columns=None):
    try:
        return df(name)
    except Exception:
        return pd.DataFrame(columns=columns or [])


def write(name, frame):
    dataiku.Dataset(NAMES[name]).write_with_schema(frame)


def safe(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    return v


def records(frame, limit=None):
    if limit:
        frame = frame.head(limit)
    return [{k: safe(v) for k, v in r.items()} for r in frame.to_dict('records')]


def coalesce(row, *names, default=None):
    for name in names:
        if name in row and pd.notna(row[name]) and str(row[name]) != '':
            return row[name]
    return default


def models():
    try:
        p = dataiku.api_client().get_default_project()
        out = []
        for m in p.list_saved_models():
            obj = p.get_saved_model(m['id'])
            versions = []
            try:
                for v in obj.list_versions():
                    vid = v.get('id') if isinstance(v, dict) else str(v)
                    versions.append({'id': vid, 'label': vid})
            except Exception:
                pass
            out.append({'id': m['id'], 'name': m.get('name', m['id']), 'versions': versions})
        return out
    except Exception:
        return []


def normalize_manifest(m):
    if m.empty:
        return m
    m = m.copy()
    # Support both the original repository schema and the richer schema already
    # created in some DSS projects.
    if 'created_at' not in m.columns and 'run_timestamp' in m.columns:
        m['created_at'] = m['run_timestamp']
    if 'run_timestamp' not in m.columns and 'created_at' in m.columns:
        m['run_timestamp'] = m['created_at']
    if 'run_label' not in m.columns:
        m['run_label'] = m['run_id']
    if 'is_official' not in m.columns:
        m['is_official'] = (m.get('status', '') == 'PRODUCTION').astype(int)
    if 'solution_bundle_version' not in m.columns:
        m['solution_bundle_version'] = ''
    if 'created_by' not in m.columns:
        m['created_by'] = 'unknown'
    if 'management_overlay' not in m.columns:
        m['management_overlay'] = 0.0
    if 'model_group_version' not in m.columns:
        m['model_group_version'] = ''
    if 'method_config_version' not in m.columns:
        m['method_config_version'] = ''
    if 'math_config_version' not in m.columns:
        m['math_config_version'] = ''
    if 'requested_execution_engine' not in m.columns:
        m['requested_execution_engine'] = ''
    if 'actual_execution_engine' not in m.columns:
        m['actual_execution_engine'] = ''
    if 'execution_note' not in m.columns:
        m['execution_note'] = ''
    return m


def upsert_by_key(frame, key, row):
    frame = frame.copy()
    for c in row:
        if c not in frame.columns:
            frame[c] = np.nan
    for c in frame.columns:
        if c not in row:
            row[c] = np.nan
    if key in frame.columns and (frame[key].astype(str) == str(row[key])).any():
        hit = frame[key].astype(str) == str(row[key])
        for c, v in row.items():
            frame.loc[hit, c] = v
        return frame
    return pd.concat([frame, pd.DataFrame([row])[frame.columns]], ignore_index=True)


def add_manifest_row(manifests, row):
    manifests = manifests.copy()
    for c in row:
        if c not in manifests.columns:
            manifests[c] = np.nan
    for c in manifests.columns:
        if c not in row:
            row[c] = np.nan
    return pd.concat([manifests, pd.DataFrame([row])[manifests.columns]], ignore_index=True)


def scenario_weights_from_row(r):
    vals = {}
    for scen, col in [('Baseline', 'baseline_weight'), ('Downside', 'downside_weight'), ('Severe', 'severe_weight')]:
        if col in r and pd.notna(r[col]):
            vals[scen] = float(r[col])
    if len(vals) == 3:
        return vals
    raw = coalesce(r, 'scenario_weights', default='')
    if isinstance(raw, str) and raw:
        try:
            z = json.loads(raw)
            if isinstance(z, dict):
                return {s: float(z.get(s, 0)) for s in SCENARIOS}
        except Exception:
            parts = raw.replace('|', '/').split('/')
            if len(parts) == 3:
                try:
                    return dict(zip(SCENARIOS, map(float, parts)))
                except Exception:
                    pass
    return {'Baseline': .55, 'Downside': .30, 'Severe': .15}


# ----------------------------------------------------------------------------
# Catalog and run APIs
# ----------------------------------------------------------------------------
@app.route('/context')
def context():
    p = df('portfolio_snapshot')
    c = df('counterparty_snapshot')
    method_cfg = maybe_df('ecl_method_config')
    math_cfg = maybe_df('ecl_math_config')
    exec_cfg = maybe_df('ecl_execution_profiles')
    versions = [] if method_cfg.empty else sorted(method_cfg.config_version.astype(str).unique().tolist(), reverse=True)
    math_versions = [] if math_cfg.empty else sorted(math_cfg.math_config_version.astype(str).unique().tolist(), reverse=True)
    base_fields = sorted(set(p.columns.astype(str)).union(set(c.columns.astype(str))))
    derived = ['fico_band', 'moodys_band', 'delinquency_state']
    category_fields = [x for x in ['fico_band','moodys_band','moodys_rating','sp_rating','rating_notch','risk_grade','delinquency_state','state','industry','product_type','segment'] if x in base_fields or x in derived]
    return jsonify({
        'as_of_dates': sorted(p.as_of_date.astype(str).unique().tolist()),
        'products': sorted(p.product_type.astype(str).unique().tolist()),
        'models': models(),
        'model_group': records(maybe_df('model_group_config')),
        'method_config_versions': versions,
        'math_config_versions': math_versions,
        'execution_profiles': records(exec_cfg[exec_cfg.enabled.fillna(1).astype(int).eq(1)] if not exec_cfg.empty and 'enabled' in exec_cfg.columns else exec_cfg),
        'category_fields': category_fields,
        'current_user': current_user()
    })

@app.route('/runs')
def runs():
    m = normalize_manifest(df('cecl_run_manifest'))
    m['_sort'] = pd.to_datetime(m['created_at'], errors='coerce')
    m = m.sort_values(['as_of_date', '_sort'], ascending=[False, False]).drop(columns=['_sort'])
    gov = maybe_df('cecl_governance_status')
    rel = maybe_df('cecl_release_log')
    if not gov.empty:
        keep = [c for c in ['run_id', 'govern_status', 'mock_artifact_id'] if c in gov.columns]
        m = m.merge(gov[keep].drop_duplicates('run_id', keep='last'), on='run_id', how='left')
    if not rel.empty:
        keep = [c for c in ['run_id', 'provider', 'commit_hash', 'status'] if c in rel.columns]
        r = rel[keep].drop_duplicates('run_id', keep='last').rename(columns={'status': 'git_status'})
        m = m.merge(r, on='run_id', how='left')
    return jsonify(records(m))


@app.route('/overview/<run_id>')
def overview(run_id):
    m = normalize_manifest(df('cecl_run_manifest'))
    r = df('cecl_instrument_results')
    meta = m[m.run_id.astype(str).eq(str(run_id))]
    if meta.empty:
        return jsonify({'error': 'Run not found'}), 404
    x = r[r.run_id.astype(str).eq(str(run_id))].copy()
    if x.empty:
        return jsonify({'error': 'No instrument results for run'}), 404
    one = x.sort_values('scenario').drop_duplicates('instrument_id')
    portfolio = x.groupby('product_type', as_index=False).weighted_ecl.sum().sort_values('weighted_ecl', ascending=False)
    stage = x.groupby('stage', as_index=False).weighted_ecl.sum()
    scen = x.groupby('scenario', as_index=False).agg(scenario_ecl=('scenario_ecl', 'sum'), weight=('scenario_weight', 'first'))
    top = x.groupby(['instrument_id', 'product_type', 'stage'], as_index=False).agg(ead=('ead', 'max'), ecl=('weighted_ecl', 'sum')).nlargest(10, 'ecl')
    method = pd.DataFrame()
    if 'pd_method' in x.columns:
        method = x.groupby(['product_type', 'pd_method'], as_index=False).weighted_ecl.sum()
    mm = meta.iloc[0]
    return jsonify({
        'meta': {k: safe(v) for k, v in mm.items()},
        'instruments': int(one.instrument_id.nunique()),
        'portfolio': records(portfolio), 'stage': records(stage),
        'scenario': records(scen), 'top': records(top), 'methods': records(method)
    })


@app.route('/compare')
def compare():
    fr = request.args.get('from')
    to = request.args.get('to')
    m = normalize_manifest(df('cecl_run_manifest')).set_index('run_id')
    if fr not in m.index or to not in m.index:
        return jsonify({'error': 'Run not found'}), 404
    a, b = m.loc[fr], m.loc[to]
    att = maybe_df('cecl_attribution_results')
    z = pd.DataFrame()
    if not att.empty and {'from_run_id', 'to_run_id'}.issubset(att.columns):
        z = att[(att.from_run_id.astype(str).eq(str(fr))) & (att.to_run_id.astype(str).eq(str(to)))]
    if z.empty:
        delta = float(b.total_ecl - a.total_ecl)
        z = pd.DataFrame([{'level': 1, 'sort_order': 1, 'category': 'Net ECL change', 'parent_category': '', 'amount': delta}])
    return jsonify({
        'from_ecl': float(a.total_ecl), 'to_ecl': float(b.total_ecl),
        'delta': float(b.total_ecl - a.total_ecl),
        'rows': records(z.sort_values([c for c in ['level', 'sort_order'] if c in z.columns]))
    })


# ----------------------------------------------------------------------------
# Methodology, math, and execution configuration APIs
# ----------------------------------------------------------------------------
@app.route('/methodologies')
def methodologies():
    pp = maybe_df('prepayment_curves')
    lp = maybe_df('lifetime_pd_curves')
    tm = maybe_df('transition_matrices')
    fx = maybe_df('fixed_parameter_values')
    cfg = maybe_df('ecl_method_config')
    def cat(frame, cols):
        return records(frame[[c for c in cols if c in frame.columns]].drop_duplicates() if not frame.empty else frame)
    return jsonify({
        'prepayment_catalog': cat(pp, ['curve_id','curve_label','product_type','bucket_field']),
        'lifetime_pd_catalog': cat(lp, ['curve_id','curve_label','product_type','bucket_field']),
        'transition_catalog': cat(tm, ['matrix_id','matrix_label','product_type','state_field']),
        'fixed_catalog': cat(fx, ['parameter_set_id','parameter_set_label','product_type','parameter_type','category_field']),
        'config_versions': sorted(cfg.config_version.astype(str).unique().tolist(), reverse=True) if not cfg.empty else [],
        'models': models()
    })


@app.route('/method-config/<version>')
def get_method_config(version):
    cfg = maybe_df('ecl_method_config')
    z = cfg[cfg.config_version.astype(str).eq(str(version))] if not cfg.empty else cfg
    return jsonify(records(z.sort_values('product_type') if not z.empty else z))


@app.route('/method-config', methods=['POST'])
def save_method_config():
    payload = request.get_json(force=True)
    rows = payload.get('rows', [])
    if not rows:
        return jsonify({'error': 'No configuration rows supplied'}), 400
    existing = maybe_df('ecl_method_config')
    version = payload.get('config_version') or ('METHODCFG_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    stamp = now_iso()
    out = []
    for row in rows:
        r = dict(row)
        r['config_version'] = version
        r['created_at'] = stamp
        r['created_by'] = current_user()
        r.setdefault('notes', payload.get('notes', 'Saved from ECL Workbench'))
        out.append(r)
    new = pd.DataFrame(out)
    if existing.empty:
        write('ecl_method_config', new)
    else:
        for c in new.columns:
            if c not in existing.columns:
                existing[c] = np.nan
        for c in existing.columns:
            if c not in new.columns:
                new[c] = np.nan
        write('ecl_method_config', pd.concat([existing, new[existing.columns]], ignore_index=True))
    return jsonify({'ok': True, 'config_version': version})


@app.route('/math-configs')
def math_configs():
    x = maybe_df('ecl_math_config')
    if x.empty:
        return jsonify({'versions': [], 'rows': []})
    version = request.args.get('version')
    if version:
        x = x[x.math_config_version.astype(str).eq(str(version))]
    return jsonify({
        'versions': sorted(maybe_df('ecl_math_config').math_config_version.astype(str).unique().tolist(), reverse=True),
        'rows': records(x.sort_values('product_type'))
    })


@app.route('/execution-profiles')
def execution_profiles():
    x = maybe_df('ecl_execution_profiles')
    return jsonify(records(x))


def dataset_sql_meta(name):
    try:
        ds = dataiku.Dataset(NAMES[name])
        loc = ds.get_location_info() or {}
        info = loc.get('info', {}) or {}
        return {
            'dataset': name,
            'sql_table': bool(info.get('quotedResolvedTableName')),
            'connection': info.get('connectionName') or info.get('connection') or '',
            'table': info.get('quotedResolvedTableName') or ''
        }
    except Exception as e:
        return {'dataset': name, 'sql_table': False, 'connection': '', 'table': '', 'error': str(e)}


@app.route('/engine-readiness')
def engine_readiness():
    names = ['portfolio_snapshot','counterparty_snapshot','macroeconomic_scenarios','prepayment_curves','lifetime_pd_curves','transition_matrices','fixed_parameter_values']
    metas = [dataset_sql_meta(n) for n in names]
    required = metas[:2]
    same = bool(required and all(x.get('sql_table') for x in required) and len({x.get('connection') for x in required}) == 1)
    scenario_ids=[]
    try:
        scenario_ids=[x.id for x in dataiku.api_client().get_default_project().list_scenarios()]
    except Exception:
        pass
    return jsonify({
        'datasets': metas,
        'base_sql_ready': same,
        'scenario_ids': scenario_ids,
        'message': 'Warehouse execution is best wired through a DSS Scenario/Flow branch. This package keeps DSS Python as a safe fallback.'
    })


@app.route('/curve/prepayment')
def prepayment_curve():
    cid, scen = request.args.get('curve_id'), request.args.get('scenario', 'Baseline')
    bucket = request.args.get('bucket')
    x = maybe_df('prepayment_curves')
    z = x[(x.curve_id.astype(str).eq(str(cid))) & (x.scenario.astype(str).eq(str(scen)))] if not x.empty else x
    if bucket and not z.empty and 'bucket_value' in z.columns:
        z = z[z.bucket_value.astype(str).eq(str(bucket))]
    buckets = sorted(z.bucket_value.astype(str).unique().tolist()) if not z.empty and 'bucket_value' in z.columns else []
    return jsonify({'buckets': buckets, 'rows': records(z.sort_values(['bucket_value','month']) if not z.empty and 'bucket_value' in z.columns else z.sort_values('month'))})


@app.route('/curve/lifetime-pd')
def lifetime_curve():
    cid = request.args.get('curve_id')
    scen = request.args.get('scenario', 'Baseline')
    bucket = request.args.get('risk_bucket')
    x = maybe_df('lifetime_pd_curves')
    z = x[(x.curve_id.astype(str).eq(str(cid))) & (x.scenario.astype(str).eq(str(scen)))] if not x.empty else x
    if bucket and not z.empty:
        z = z[z.risk_bucket.astype(str).eq(str(bucket))]
    buckets = sorted(z.risk_bucket.astype(str).unique().tolist()) if not z.empty else []
    return jsonify({'buckets': buckets, 'rows': records(z.sort_values(['risk_bucket', 'month']) if not z.empty else z)})


@app.route('/matrix')
def matrix():
    mid, scen = request.args.get('matrix_id'), request.args.get('scenario', 'Baseline')
    x = maybe_df('transition_matrices')
    z = x[(x.matrix_id.astype(str).eq(str(mid))) & (x.scenario.astype(str).eq(str(scen)))] if not x.empty else x
    return jsonify(records(z))


@app.route('/fixed-values')
def fixed_values():
    sid = request.args.get('parameter_set_id')
    scen = request.args.get('scenario')
    x = maybe_df('fixed_parameter_values')
    if sid and not x.empty:
        x = x[x.parameter_set_id.astype(str).eq(str(sid))]
    if scen and not x.empty:
        x = x[x.scenario.astype(str).eq(str(scen))]
    return jsonify(records(x))


# ----------------------------------------------------------------------------
# Calculation helpers
# ----------------------------------------------------------------------------
def macro_values(macro, asof, scenario):
    z = macro[(macro.forecast_vintage.astype(str).eq(str(asof))) & (macro.scenario.astype(str).eq(str(scenario)))]
    if z.empty:
        return {'unemployment_rate': 4.1, 'real_gdp_growth': 2.2, 'hpi_growth': 3.0, 'bbb_spread': 1.7}
    mm = z.groupby('variable').value.mean()
    return {
        'unemployment_rate': float(mm.get('unemployment_rate', 4.1)),
        'real_gdp_growth': float(mm.get('real_gdp_growth', 2.2)),
        'hpi_growth': float(mm.get('hpi_growth', 3.0)),
        'bbb_spread': float(mm.get('bbb_spread', 1.7)),
    }


def enrich_categories(frame):
    x = frame.copy()
    fico = x.get('fico_score', pd.Series(700, index=x.index)).fillna(700)
    x['fico_band'] = np.where(fico >= 720, 'Prime', np.where(fico >= 660, 'Near Prime', 'Subprime'))
    notch = x.get('rating_notch', pd.Series(5, index=x.index)).fillna(5).astype(float)
    x['moodys_band'] = np.select(
        [notch <= 3, notch <= 6, notch <= 9, notch <= 12],
        ['Aaa-A', 'Baa', 'Ba', 'B'], default='Caa'
    )
    dpd = x.get('days_past_due', pd.Series(0, index=x.index)).fillna(0)
    x['delinquency_state'] = np.where(dpd >= 90, 'Default', np.where(dpd >= 60, '60-89 DPD', np.where(dpd >= 30, '30-59 DPD', 'Current')))
    return x


def category_array(frame, field, default='ALL'):
    if not field or str(field).upper() == 'ALL':
        return np.array([default] * len(frame), dtype=object)
    if field in frame.columns:
        return frame[field].fillna(default).astype(str).to_numpy(dtype=object)
    return np.array([default] * len(frame), dtype=object)


def horizons_months(frame, framework, stage):
    asof = pd.to_datetime(frame.as_of_date.astype(str), errors='coerce')
    maturity = pd.to_datetime(frame.maturity_date.astype(str), errors='coerce')
    remaining = ((maturity - asof).dt.days / 30.44).fillna(60).clip(lower=1, upper=120).astype(int).to_numpy()
    if framework == 'CECL':
        return remaining
    return np.where(stage == 1, np.minimum(12, remaining), remaining)


def fixed_values_for_rows(fixed, set_id, parameter_type, scenario, categories):
    out = np.full(len(categories), np.nan, dtype=float)
    if not set_id or fixed.empty:
        return out
    z = fixed[(fixed.parameter_set_id.astype(str).eq(str(set_id))) &
              (fixed.parameter_type.astype(str).eq(str(parameter_type))) &
              (fixed.scenario.astype(str).eq(str(scenario)))]
    if z.empty:
        return out
    all_rows = z[z.category_value.astype(str).eq('ALL')] if 'category_value' in z.columns else z.iloc[0:0]
    all_val = float(all_rows.value.iloc[-1]) if not all_rows.empty else np.nan
    out[:] = all_val
    for cat in np.unique(categories):
        q = z[z.category_value.astype(str).eq(str(cat))]
        if not q.empty:
            out[np.asarray(categories) == cat] = float(q.value.iloc[-1])
    return out


def prepayment_factor(curves, curve_id, scenario, categories, horizons):
    out = np.ones(len(horizons), dtype=float)
    if not curve_id or curves.empty:
        return out
    z0 = curves[(curves.curve_id.astype(str).eq(str(curve_id))) & (curves.scenario.astype(str).eq(str(scenario)))]
    if z0.empty:
        return out
    bucket_col = 'bucket_value' if 'bucket_value' in z0.columns else None
    for cat in np.unique(categories):
        mask = np.asarray(categories) == cat
        z = z0
        if bucket_col:
            q = z0[z0[bucket_col].astype(str).eq(str(cat))]
            if q.empty:
                q = z0[z0[bucket_col].astype(str).eq('ALL')]
            z = q
        z = z.sort_values('month')
        if z.empty:
            continue
        if 'cumulative_survival' in z.columns:
            surv = z.cumulative_survival.to_numpy(dtype=float)
        else:
            surv = np.cumprod(1 - z.monthly_smm.to_numpy(dtype=float))
        avg_surv = np.cumsum(surv) / np.arange(1, len(surv)+1)
        h = np.clip(np.asarray(horizons)[mask].astype(int), 1, len(avg_surv))
        out[mask] = avg_surv[h-1]
    return out


def lifetime_pd_from_curve(curves, curve_id, scenario, categories, horizons):
    out = np.full(len(horizons), np.nan, dtype=float)
    if not curve_id or curves.empty:
        return out
    z0 = curves[(curves.curve_id.astype(str).eq(str(curve_id))) & (curves.scenario.astype(str).eq(str(scenario)))]
    if z0.empty:
        return out
    for cat in np.unique(categories):
        mask = np.asarray(categories) == cat
        z = z0[z0.risk_bucket.astype(str).eq(str(cat))].sort_values('month')
        if z.empty:
            z = z0[z0.risk_bucket.astype(str).eq('ALL')].sort_values('month')
        if z.empty:
            continue
        months = z.month.to_numpy(dtype=float)
        cum = z.cumulative_pd.to_numpy(dtype=float)
        out[mask] = np.interp(np.asarray(horizons)[mask], months, cum, left=cum[0], right=cum[-1])
    return np.clip(out, .0001, .98)


def transition_pd_from_matrix(matrices, matrix_id, scenario, states, horizons):
    out = np.full(len(horizons), np.nan, dtype=float)
    if not matrix_id or matrices.empty:
        return out
    z = matrices[(matrices.matrix_id.astype(str).eq(str(matrix_id))) & (matrices.scenario.astype(str).eq(str(scenario)))]
    if z.empty:
        return out
    for state in np.unique(states):
        mask = np.asarray(states) == state
        row = z[(z.from_state.astype(str).eq(str(state))) & (z.to_state.astype(str).eq('Default'))]
        p_ann = float(row.annual_probability.iloc[-1]) if not row.empty else np.nan
        if np.isnan(p_ann):
            continue
        years = np.maximum(np.asarray(horizons)[mask] / 12.0, 1/12)
        out[mask] = 1 - (1 - p_ann) ** years
    return np.clip(out, .0001, .98)


def resolve_execution_profile(profile_id):
    x = maybe_df('ecl_execution_profiles')
    if x.empty:
        return {'profile_id': profile_id or 'EXEC_DSS_PYTHON', 'engine_type': 'DSS_PYTHON', 'allow_python_fallback': 1, 'notes': ''}
    z = x[x.profile_id.astype(str).eq(str(profile_id))]
    if z.empty:
        z = x[x.profile_id.astype(str).eq('EXEC_AUTO')]
    if z.empty:
        z = x.iloc[[0]]
    return z.iloc[-1].to_dict()


def engine_route(cfg):
    profile = resolve_execution_profile(cfg.get('execution_profile_id', 'EXEC_AUTO'))
    requested = str(profile.get('engine_type', 'DSS_PYTHON'))
    actual = 'DSS_PYTHON'
    note = 'Current vectorized DSS Python engine.'
    if requested in ['SQL_IN_DATABASE','DSS_SCENARIO','AUTO']:
        readiness = dataset_sql_meta('portfolio_snapshot')
        if requested == 'DSS_SCENARIO':
            sid = str(profile.get('scenario_id','') or '')
            note = f'Warehouse scenario requested ({sid or "not configured"}); safe Python fallback used in this package.'
        elif requested == 'SQL_IN_DATABASE':
            note = 'In-database SQL requested; safe Python fallback used until a warehouse Flow/scenario adapter is wired.'
        else:
            note = 'AUTO profile selected; safe Python runtime used. Wire a warehouse scenario to route eligible runs in-database.'
        if readiness.get('sql_table'):
            note += f" Portfolio is SQL-backed on connection {readiness.get('connection') or 'unknown'}."
    return requested, actual, note


def calculate_run(cfg):
    asof = cfg['as_of_date']
    framework = cfg.get('framework', 'IFRS9')
    weights = cfg['weights']
    requested_engine, actual_engine, execution_note = engine_route(cfg)
    p = df('portfolio_snapshot')
    c = df('counterparty_snapshot')
    macro = df('macroeconomic_scenarios')
    p = p[p.as_of_date.astype(str).eq(str(asof))].merge(
        c[c.as_of_date.astype(str).eq(str(asof))], on='counterparty_id', how='left', suffixes=('','_cp')
    )
    p['as_of_date'] = asof
    p = enrich_categories(p)
    stage = np.where((p.default_flag.eq(1)) | (p.days_past_due >= cfg.get('stage3_dpd', 90)), 3,
                     np.where((p.days_past_due >= cfg.get('stage2_dpd', 30)) |
                              (p.watchlist_flag.eq(1)) | (p.forbearance_flag.eq(1)), 2, 1))
    retail = p.segment.astype(str).eq('RETAIL')
    raw = np.where(
        retail,
        -3.4 + .012 * (700 - p.fico_score.fillna(700)) + .018 * p.days_past_due + 1.3 * p.dti.fillna(.35),
        -3.2 + .22 * (p.rating_notch.fillna(5) - 5) + .09 * p.debt_to_equity.fillna(1.5)
        - .06 * p.interest_coverage_ratio.fillna(2.5) + .018 * p.days_past_due
    )
    horizons = horizons_months(p, framework, stage)

    method_cfg = maybe_df('ecl_method_config')
    version = cfg.get('method_config_version')
    if version and not method_cfg.empty:
        method_cfg = method_cfg[method_cfg.config_version.astype(str).eq(str(version))]
    if method_cfg.empty:
        method_cfg = pd.DataFrame({'product_type': p.product_type.unique(), 'pd_method': 'FORMULA', 'lgd_method':'FORMULA', 'ead_method':'CONTRACTUAL', 'prepayment_method':'NONE'})
    method_cfg = method_cfg.drop_duplicates('product_type', keep='last').set_index('product_type')

    prepay = maybe_df('prepayment_curves')
    lpcurves = maybe_df('lifetime_pd_curves')
    matrices = maybe_df('transition_matrices')
    fixed = maybe_df('fixed_parameter_values')

    rid = f"{framework}_{asof.replace('-', '')}_{datetime.now(timezone.utc).strftime('%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
    out = []
    for scenario, weight in weights.items():
        mv = macro_values(macro, asof, scenario)
        un, gdp, hpi, spread = mv['unemployment_rate'], mv['real_gdp_growth'], mv['hpi_growth'], mv['bbb_spread']
        shift = np.where(retail, .16 * (un - 4.1) - .04 * (hpi - 3), .12 * (un - 4.1) - .12 * (gdp - 2.2) + .17 * (spread - 1.7))
        pd12_formula = np.clip(1 / (1 + np.exp(-(raw + shift))), .0003, .65)
        lifetime_formula = np.clip(1 - (1 - pd12_formula) ** np.maximum(horizons / 12.0, 1.0), pd12_formula, .95)
        applied_formula = np.where((framework == 'IFRS9') & (stage == 1), pd12_formula, lifetime_formula)
        lgd_formula = np.clip(np.where(p.collateral_value.fillna(0) > 0,
                               .2 + .55 * np.clip(p.ltv.fillna(1) - .6, 0, 1), .62) + .03 * (un - 4.1), .08, .95)

        n=len(p)
        pd_applied=np.zeros(n); lgd=np.zeros(n); ead=np.zeros(n); prepay_factor_arr=np.ones(n)
        pd_method=np.empty(n,dtype=object); lgd_method=np.empty(n,dtype=object); ead_method=np.empty(n,dtype=object); pp_method=np.empty(n,dtype=object)
        pd_source=np.empty(n,dtype=object); lgd_source=np.empty(n,dtype=object); ead_source=np.empty(n,dtype=object); pp_source=np.empty(n,dtype=object); tm_source=np.empty(n,dtype=object)
        calc_source=np.empty(n,dtype=object)

        for product in p.product_type.astype(str).unique():
            mask = p.product_type.astype(str).eq(product).to_numpy()
            mc = method_cfg.loc[product] if product in method_cfg.index else pd.Series(dtype=object)
            pdm=str(mc.get('pd_method','FORMULA') or 'FORMULA').upper(); psrc=str(mc.get('pd_source_id','') or '')
            pfield=str(mc.get('pd_category_field','') or '')
            tm_id=str(mc.get('transition_matrix_id','') or ''); tm_field=str(mc.get('transition_state_field',pfield) or pfield)
            lgdm=str(mc.get('lgd_method','FORMULA') or 'FORMULA').upper(); lsrc=str(mc.get('lgd_source_id','') or ''); lfield=str(mc.get('lgd_category_field','ALL') or 'ALL')
            eadm=str(mc.get('ead_method','CONTRACTUAL') or 'CONTRACTUAL').upper(); esrc=str(mc.get('ead_source_id','') or '')
            pp_id=str(mc.get('prepayment_curve_id','') or '')
            default_pp='CURVE' if pp_id else 'NONE'
            ppm=str(mc.get('prepayment_method',default_pp) or default_pp).upper(); pp_field=str(mc.get('prepayment_category_field','ALL') or 'ALL')

            # PD
            cats = category_array(p.loc[mask], pfield)
            if pdm == 'LIFETIME_PD_CURVE':
                vals = lifetime_pd_from_curve(lpcurves, psrc, scenario, cats, horizons[mask])
                vals = np.where(np.isnan(vals), applied_formula[mask], vals)
            elif pdm == 'TRANSITION_MATRIX':
                states = category_array(p.loc[mask], tm_field)
                vals = transition_pd_from_matrix(matrices, tm_id, scenario, states, horizons[mask])
                vals = np.where(np.isnan(vals), applied_formula[mask], vals)
            elif pdm == 'FIXED':
                fvals = fixed_values_for_rows(fixed, psrc, 'PD_12M', scenario, cats)
                fvals = np.where(np.isnan(fvals), pd12_formula[mask], fvals)
                life = np.clip(1-(1-fvals)**np.maximum(horizons[mask]/12.0,1.0),fvals,.98)
                vals = np.where((framework=='IFRS9') & (stage[mask]==1), fvals, life)
            elif pdm == 'SAVED_MODEL':
                vals = applied_formula[mask]
            else:
                vals = applied_formula[mask]
            pd_applied[mask]=vals

            # LGD
            lcats=category_array(p.loc[mask], lfield)
            if lgdm == 'FIXED':
                lv=fixed_values_for_rows(fixed, lsrc, 'LGD', scenario, lcats)
                lv=np.where(np.isnan(lv),lgd_formula[mask],lv)
            elif lgdm == 'SAVED_MODEL':
                lv=lgd_formula[mask]
            else:
                lv=lgd_formula[mask]
            lgd[mask]=np.clip(lv,.01,.99)

            # Prepayment
            ppcats=category_array(p.loc[mask], pp_field)
            pf=prepayment_factor(prepay,pp_id,scenario,ppcats,horizons[mask]) if ppm=='CURVE' else np.ones(mask.sum())
            prepay_factor_arr[mask]=pf

            # EAD
            current=p.loc[mask,'current_balance'].fillna(0).to_numpy(float)
            undrawn=p.loc[mask,'undrawn_amount'].fillna(0).to_numpy(float)
            if eadm in ['CCF_FIXED','CCF_60']:
                ecats=np.array(['ALL']*mask.sum(),dtype=object)
                if eadm == 'CCF_FIXED':
                    ccf=fixed_values_for_rows(fixed,esrc,'CCF',scenario,ecats)
                    ccf=np.where(np.isnan(ccf),.60,ccf)
                else:
                    ccf=np.full(mask.sum(),.60)
                ev=current+ccf*undrawn
            elif eadm == 'SAVED_MODEL':
                ev=current+.60*undrawn
            else:
                ev=current
            ead[mask]=ev*pf

            pd_method[mask]=pdm; lgd_method[mask]=lgdm; ead_method[mask]=eadm; pp_method[mask]=ppm
            pd_source[mask]=psrc; lgd_source[mask]=lsrc; ead_source[mask]=esrc; pp_source[mask]=pp_id; tm_source[mask]=tm_id
            fallback = (pdm=='SAVED_MODEL') or (lgdm=='SAVED_MODEL') or (eadm=='SAVED_MODEL')
            calc_source[mask]='SAVED_MODEL_CONFIG_WITH_DEMO_FALLBACK' if fallback else 'CONFIGURED_METHOD'

        ecl = ead * pd_applied * lgd
        out.append(pd.DataFrame({
            'run_id': rid, 'as_of_date': asof, 'instrument_id': p.instrument_id,
            'counterparty_id': p.counterparty_id, 'product_type': p.product_type,
            'scenario': scenario, 'scenario_weight': float(weight), 'stage': stage,
            'pd_12m': pd12_formula, 'pd_applied': pd_applied, 'lgd': lgd,
            'ead': ead, 'scenario_ecl': ecl, 'weighted_ecl': ecl * float(weight),
            'pd_method': pd_method, 'pd_source_id': pd_source,
            'lgd_method': lgd_method, 'lgd_source_id': lgd_source,
            'ead_method': ead_method, 'ead_source_id': ead_source,
            'prepayment_method': pp_method, 'prepayment_curve_id': pp_source,
            'transition_matrix_id': tm_source, 'prepayment_factor': prepay_factor_arr,
            'method_config_version': version or '',
            'math_config_version': cfg.get('math_config_version',''),
            'requested_execution_engine': requested_engine,
            'actual_execution_engine': actual_engine,
            'calculation_source': calc_source
        }))

    res = pd.concat(out, ignore_index=True)
    overlay = float(cfg.get('management_overlay', 0) or 0)
    total = float(res.weighted_ecl.sum() + overlay)
    exp = float(res.sort_values('scenario').drop_duplicates('instrument_id').ead.sum())
    return rid, res, total, exp, requested_engine, actual_engine, execution_note


def next_label(manifests, framework, asof):
    m = normalize_manifest(manifests)
    z = m[(m.framework.astype(str).eq(str(framework))) & (m.as_of_date.astype(str).eq(str(asof)))]
    n = len(z) + 1
    month = pd.Timestamp(asof).strftime('%B %Y')
    return f'{month} {framework} - Rerun {n:02d}'


@app.route('/run', methods=['POST'])
def run():
    cfg = request.get_json(force=True)
    rid, res, total, exp, requested_engine, actual_engine, execution_note = calculate_run(cfg)
    manifests = normalize_manifest(df('cecl_run_manifest'))
    user = current_user()
    stamp = now_iso()
    label = (cfg.get('run_label') or '').strip() or next_label(manifests, cfg.get('framework', 'IFRS9'), cfg['as_of_date'])
    weights = cfg['weights']
    row = {
        'run_id': rid, 'run_label': label, 'framework': cfg.get('framework', 'IFRS9'),
        'as_of_date': cfg['as_of_date'], 'run_timestamp': stamp, 'created_at': stamp,
        'status': 'SANDBOX', 'parent_run_id': cfg.get('parent_run_id', ''), 'is_official': 0,
        'scenario_config_version': cfg.get('scenario_config_version', 'CUSTOM_' + cfg['as_of_date'].replace('-', '')),
        'baseline_weight': float(weights.get('Baseline', 0)), 'downside_weight': float(weights.get('Downside', 0)),
        'severe_weight': float(weights.get('Severe', 0)), 'scenario_weights': json.dumps(weights),
        'reasonable_supportable_months': int(cfg.get('reasonable_supportable_months', 24)),
        'reversion_method': cfg.get('reversion_method', 'STRAIGHT_LINE'),
        'reversion_months': int(cfg.get('reversion_months', 24)),
        'stage_rule_version': cfg.get('stage_rule_version', 'IFRS9_STAGE_V1'),
        'model_group_version': cfg.get('model_group_version', 'WEBAPP_MODEL_GROUP'),
        'method_config_version': cfg.get('method_config_version', ''),
        'math_config_version': cfg.get('math_config_version', ''),
        'requested_execution_engine': requested_engine,
        'actual_execution_engine': actual_engine,
        'execution_note': execution_note,
        'management_overlay': float(cfg.get('management_overlay', 0) or 0),
        'solution_bundle_version': cfg.get('bundle_version', 'ECL_APP_DEV'),
        'created_by': user, 'configuration_fingerprint': uuid.uuid4().hex[:16],
        'total_exposure': exp, 'total_ecl': total
    }
    write('cecl_run_manifest', add_manifest_row(manifests, row))
    existing = df('cecl_instrument_results')
    for c in res.columns:
        if c not in existing.columns:
            existing[c] = np.nan
    for c in existing.columns:
        if c not in res.columns:
            res[c] = np.nan
    write('cecl_instrument_results', pd.concat([existing, res[existing.columns]], ignore_index=True))
    return jsonify(row)


# ----------------------------------------------------------------------------
# Mock Govern workflow
# ----------------------------------------------------------------------------
GOV_COLS = ['run_id', 'govern_mode', 'govern_status', 'mock_artifact_id', 'submitted_at', 'submitted_by',
            'approved_at', 'approved_by', 'rejected_at', 'rejected_by', 'comments']
REL_COLS = ['run_id', 'provider', 'repository', 'branch', 'release_path', 'commit_hash', 'pushed_at',
            'pushed_by', 'status', 'release_json']


def gov_row(run_id):
    g = maybe_df('cecl_governance_status', GOV_COLS)
    z = g[g.run_id.astype(str).eq(str(run_id))] if not g.empty else g
    return z.iloc[-1].to_dict() if not z.empty else {
        'run_id': run_id, 'govern_mode': 'MOCK', 'govern_status': 'NOT_SUBMITTED', 'mock_artifact_id': ''
    }


def update_manifest_status(run_id, status):
    m = normalize_manifest(df('cecl_run_manifest'))
    hit = m.run_id.astype(str).eq(str(run_id))
    if hit.any():
        m.loc[hit, 'status'] = status
        write('cecl_run_manifest', m)


@app.route('/govern/<run_id>')
def get_govern(run_id):
    g = gov_row(run_id)
    rel = maybe_df('cecl_release_log', REL_COLS)
    r = rel[rel.run_id.astype(str).eq(str(run_id))] if not rel.empty else rel
    return jsonify({'governance': {k: safe(v) for k, v in g.items()}, 'release': records(r.tail(1))[0] if not r.empty else None})


@app.route('/govern/submit/<run_id>', methods=['POST'])
def govern_submit(run_id):
    g = maybe_df('cecl_governance_status', GOV_COLS)
    stamp = now_iso()
    artifact = 'MOCK-GOV-' + hashlib.sha1((run_id + stamp).encode()).hexdigest()[:10].upper()
    row = {'run_id': run_id, 'govern_mode': 'MOCK', 'govern_status': 'REVIEW', 'mock_artifact_id': artifact,
           'submitted_at': stamp, 'submitted_by': current_user(), 'approved_at': '', 'approved_by': '',
           'rejected_at': '', 'rejected_by': '', 'comments': 'Submitted from ECL Workbench mock workflow'}
    write('cecl_governance_status', upsert_by_key(g, 'run_id', row))
    update_manifest_status(run_id, 'REVIEW')
    return jsonify(row)


@app.route('/govern/approve/<run_id>', methods=['POST'])
def govern_approve(run_id):
    g = maybe_df('cecl_governance_status', GOV_COLS)
    current = gov_row(run_id)
    current.update({'run_id': run_id, 'govern_mode': 'MOCK', 'govern_status': 'APPROVED',
                    'approved_at': now_iso(), 'approved_by': current_user(), 'rejected_at': '', 'rejected_by': ''})
    write('cecl_governance_status', upsert_by_key(g, 'run_id', current))
    update_manifest_status(run_id, 'APPROVED')
    return jsonify(current)


@app.route('/govern/reject/<run_id>', methods=['POST'])
def govern_reject(run_id):
    g = maybe_df('cecl_governance_status', GOV_COLS)
    current = gov_row(run_id)
    current.update({'run_id': run_id, 'govern_mode': 'MOCK', 'govern_status': 'REJECTED',
                    'rejected_at': now_iso(), 'rejected_by': current_user()})
    write('cecl_governance_status', upsert_by_key(g, 'run_id', current))
    update_manifest_status(run_id, 'REJECTED')
    return jsonify(current)


# ----------------------------------------------------------------------------
# Mock GitHub / Bitbucket release
# ----------------------------------------------------------------------------
def release_manifest(run_id):
    m = normalize_manifest(df('cecl_run_manifest'))
    z = m[m.run_id.astype(str).eq(str(run_id))]
    if z.empty:
        return None
    r = z.iloc[0]
    gov = gov_row(run_id)
    return {
        'run_id': str(run_id), 'run_label': str(r.get('run_label', run_id)),
        'framework': str(r.get('framework', '')), 'as_of_date': str(r.get('as_of_date', '')),
        'status': str(r.get('status', '')), 'total_exposure': float(r.get('total_exposure', 0) or 0),
        'total_ecl': float(r.get('total_ecl', 0) or 0),
        'scenario_weights': scenario_weights_from_row(r),
        'stage_rule_version': str(r.get('stage_rule_version', '')),
        'model_group_version': str(r.get('model_group_version', '')),
        'method_config_version': str(r.get('method_config_version', '')),
        'math_config_version': str(r.get('math_config_version', '')),
        'requested_execution_engine': str(r.get('requested_execution_engine', '')),
        'actual_execution_engine': str(r.get('actual_execution_engine', '')),
        'execution_note': str(r.get('execution_note', '')),
        'management_overlay': float(r.get('management_overlay', 0) or 0),
        'parent_run_id': str(r.get('parent_run_id', '') or ''),
        'governance': {
            'mode': gov.get('govern_mode', 'MOCK'), 'status': gov.get('govern_status', 'NOT_SUBMITTED'),
            'artifact_id': gov.get('mock_artifact_id', '')
        },
        'application_bundle': str(r.get('solution_bundle_version', '')),
        'generated_at': now_iso()
    }


@app.route('/release/push/<run_id>', methods=['POST'])
def release_push(run_id):
    gov = gov_row(run_id)
    if gov.get('govern_status') != 'APPROVED':
        return jsonify({'error': 'Mock Govern approval is required before pushing a release manifest'}), 409
    payload = request.get_json(force=True) or {}
    provider = payload.get('provider', 'GitHub')
    repository = payload.get('repository', 'bank/ecl-allowance-config')
    branch = payload.get('branch', 'main')
    manifest = release_manifest(run_id)
    if manifest is None:
        return jsonify({'error': 'Run not found'}), 404
    asof = manifest['as_of_date'].replace('-', '/')
    release_path = f"releases/{asof}/{run_id}.json"
    stamp = now_iso()
    commit = hashlib.sha1((run_id + provider + repository + branch + stamp).encode()).hexdigest()[:10]
    row = {'run_id': run_id, 'provider': provider, 'repository': repository, 'branch': branch,
           'release_path': release_path, 'commit_hash': commit, 'pushed_at': stamp,
           'pushed_by': current_user(), 'status': 'PUSHED_MOCK',
           'release_json': json.dumps(manifest, sort_keys=True)}
    rel = maybe_df('cecl_release_log', REL_COLS)
    write('cecl_release_log', pd.concat([rel, pd.DataFrame([row])], ignore_index=True))
    return jsonify(row)


@app.route('/release-manifest/<run_id>')
def get_release_manifest(run_id):
    manifest = release_manifest(run_id)
    if manifest is None:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify(manifest)


# ----------------------------------------------------------------------------
# Promotion / rollback. Official scope is framework + as_of_date.
# ----------------------------------------------------------------------------
@app.route('/promote/<run_id>', methods=['POST'])
def promote(run_id):
    m = normalize_manifest(df('cecl_run_manifest'))
    hit = m.run_id.astype(str).eq(str(run_id))
    if not hit.any():
        return jsonify({'error': 'Run not found'}), 404
    gov = gov_row(run_id)
    if gov.get('govern_status') != 'APPROVED':
        return jsonify({'error': 'Mock Govern approval is required before making this run official'}), 409
    asof = str(m.loc[hit, 'as_of_date'].iloc[0])
    framework = str(m.loc[hit, 'framework'].iloc[0])
    current = (m.as_of_date.astype(str).eq(asof)) & (m.framework.astype(str).eq(framework)) & m.status.astype(str).eq('PRODUCTION')
    m.loc[current, 'status'] = 'SUPERSEDED'
    m.loc[current, 'is_official'] = 0
    m.loc[hit, 'status'] = 'PRODUCTION'
    m.loc[hit, 'is_official'] = 1
    write('cecl_run_manifest', m)
    return jsonify({'ok': True, 'run_id': run_id, 'framework': framework, 'as_of_date': asof})
