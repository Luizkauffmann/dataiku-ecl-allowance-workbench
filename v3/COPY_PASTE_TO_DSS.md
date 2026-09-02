# Copy V3 into Dataiku DSS

This page is the shortest path from GitHub to a separate V3 test webapp in DSS.

## 1. Import the V3 CSV datasets

Open [`v3/datasets/`](datasets/) and import these files into your Dataiku project using the **file name without `.csv` as the DSS dataset name**:

```text
fixed_parameter_values
prepayment_curves
lifetime_pd_curves
transition_matrices
ecl_method_config
ecl_math_config
ecl_execution_profiles
ecl_run_requests
cecl_governance_status
cecl_release_log
```

Keep the original operational datasets already used by the working demo.

## 2. Create a new Standard Webapp

Recommended name:

```text
ECL_ALLOWANCE_WORKBENCH_V3
```

Do not replace your currently working webapp until V3 has been tested.

## 3. Copy the four source files

Open each GitHub file, select its entire contents, and paste it into the matching DSS webapp editor.

- [`webapp/body.html`](webapp/body.html) → **HTML**
- [`webapp/style.css`](webapp/style.css) → **CSS**
- [`webapp/app.js`](webapp/app.js) → **JavaScript**
- [`webapp/backend.py`](webapp/backend.py) → **Python backend**

Restart the Python backend.

## 4. Test in this order

1. Open **Risk Methods** and select `METHODCFG_V2`.
2. Open **ECL Math Engine** and select `MATHCFG_V2`.
3. Open **Configure & Run**.
4. Use `EXEC_DSS_PYTHON` for the first run.
5. Create a descriptive SANDBOX run.
6. Verify it in **Overview** and **Versions**.
7. Open **Governance & Release** and test Submit → Approve → Mock Git release.
8. Only after reconciliation should you test warehouse execution profiles.

## 5. What the method selectors mean

### `FIXED`
The app looks up a value in `fixed_parameter_values`. It can be a single portfolio assumption or a scenario/category lookup such as FICO band.

### `SAVED_MODEL`
Represents a Dataiku Saved Model / Visual ML model. The public V3 runtime keeps this as a safe integration point; wire it to a Scoring Recipe for the warehouse version.

### `LIFETIME_PD_CURVE`
Uses `lifetime_pd_curves` by curve ID + risk bucket + scenario + month.

### `TRANSITION_MATRIX`
Uses `transition_matrices` by matrix ID + scenario + the configured `state_field`, for example `fico_band` or `moodys_band`.

### `CURVE` prepayment
Uses `prepayment_curves` to provide CPR/SMM behavior by product/category/scenario/month.

## 6. Recommended DSS Flow zones

```text
01_SOURCE_DATA
02_RISK_METHOD_CONFIG
03_MODEL_FACTORY
04_ECL_MATH_CONFIG
05_ECL_EXECUTION
06_ECL_RESULTS
07_GOVERNANCE_RELEASE
08_WEBAPP
```

See the full docs in [`v3/README.md`](README.md).
