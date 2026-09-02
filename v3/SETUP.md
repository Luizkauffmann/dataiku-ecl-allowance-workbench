# V3 Setup Guide for Dataiku DSS

This guide adds V3 alongside the already-working ECL Workbench. The safest approach is to **create a separate V3 Standard Webapp** and preserve the existing app until V3 has been validated in your DSS project.

## 1. Prerequisites

The original project should already contain the base datasets used by the working demo, especially:

- `portfolio_snapshot`
- `counterparty_snapshot`
- `installment_schedule`
- `default_recovery_history`
- `macroeconomic_scenarios`
- `scenario_config`
- `stage_rules`
- `model_group_config`
- `cecl_run_manifest`
- `cecl_instrument_results`
- `cecl_attribution_results`

V3 reads the same base datasets and adds configuration/audit datasets. These can be filesystem datasets for a quick demo or SQL-backed tables on Snowflake/Databricks.

## 2. Import the V3 datasets

Import the CSV files in `v3/datasets/` using these exact DSS dataset names:

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

### If a dataset already exists

Do not blindly overwrite a production-like dataset. For the demo:

1. Export or duplicate the current dataset.
2. Compare its schema with the V3 CSV.
3. Add any missing columns.
4. Append or replace only synthetic V1/V2 rows as appropriate.
5. Keep the exact DSS dataset name expected by `backend.py`.

The V3 backend is defensive around several earlier schemas, but the new functionality requires the new configuration columns.

## 3. Where to store the datasets

For the fastest test, they can live anywhere DSS can read/write.

For the future warehouse version, it is preferable to put the calculation-facing datasets on the **same Snowflake or Databricks connection** as the portfolio tables so Dataiku can maximize SQL/Spark pushdown.

Good candidates for warehouse storage include:

```text
portfolio_snapshot
counterparty_snapshot
installment_schedule
macroeconomic_scenarios
fixed_parameter_values
prepayment_curves
lifetime_pd_curves
transition_matrices
ecl_method_config
ecl_math_config
cecl_instrument_results
cecl_run_manifest
```

## 4. Create a separate Standard Webapp

Create a new Dataiku Standard Webapp, for example:

```text
ECL_ALLOWANCE_WORKBENCH_V3
```

Copy the repository files into the corresponding editor tabs:

| Repository file | Dataiku tab |
|---|---|
| `v3/webapp/body.html` | HTML |
| `v3/webapp/style.css` | CSS |
| `v3/webapp/app.js` | JavaScript |
| `v3/webapp/backend.py` | Python backend |

Restart the Python backend after pasting the Python code.

## 5. First validation

Open the app and validate these tabs in order.

### Risk Methods

Select `METHODCFG_V2` and verify the mixed methods:

- Mortgage → lifetime PD curve by `fico_band`
- Auto → transition matrix by `fico_band`
- Personal Loan → fixed PD by `fico_band`
- Credit Card → Saved Model placeholder + fixed CCF
- Commercial Term → transition matrix by `moodys_band`
- CRE → lifetime PD curve by `moodys_band`
- Equipment Lease → fixed PD by `moodys_band`
- Revolving Facility → lifetime PD curve + fixed CCF

Open the supporting panels and verify fixed parameters, prepayment curves, lifetime PD curves, and transition matrices.

### ECL Math Engine

Select `MATHCFG_V2` and confirm the loop configuration appears for each portfolio.

### Configure & Run

For the first run use:

```text
Method configuration: METHODCFG_V2
Math configuration:   MATHCFG_V2
Execution profile:    EXEC_DSS_PYTHON
```

Give the run a descriptive name such as `August V3 mixed-method test` and save it as SANDBOX.

### Overview and Versions

Confirm the new run appears, ECL totals load, methodology mix displays, and the existing official result remains unchanged.

## 6. Test mock governance

Open **Governance & Release** for the SANDBOX run.

```text
SANDBOX
  ↓ Submit to Govern
REVIEW
  ↓ Mock approve
APPROVED
  ↓ Mock push release manifest
APPROVED + release record
  ↓ Make official
PRODUCTION
```

The GitHub/Bitbucket controls in V3 are intentionally mock controls. They store a release record and JSON manifest but do not change an external repository.

## 7. Permissions

The webapp needs read access to all base/config datasets and write access to at least:

```text
cecl_run_manifest
cecl_instrument_results
ecl_method_config
ecl_run_requests
cecl_governance_status
cecl_release_log
```

## 8. Saved Models

The backend discovers project Saved Models so they can appear as choices. In V3, `SAVED_MODEL` remains a safe integration point. Recommended next step:

1. train PD/LGD models in Visual ML;
2. deploy champion versions as Saved Models;
3. implement a standard Scoring Recipe branch in the Flow;
4. have the warehouse Scenario build that branch;
5. store the exact Saved Model/version in the run manifest.

## 9. Warehouse execution

Keep `EXEC_DSS_PYTHON` until V3 is validated. Then create a DSS Scenario named `ECL_WAREHOUSE_RUN` and implement the Flow described in [WAREHOUSE_EXECUTION.md](WAREHOUSE_EXECUTION.md).

## 10. Rollback strategy

Keep two rollback mechanisms independent:

- **Calculation rollback:** make a prior immutable run official again.
- **Application rollback:** reactivate a prior Dataiku project bundle/application release.

A calculation rollback should not require changing webapp code, and a webapp deployment rollback should never mutate historical approved ECL results.
