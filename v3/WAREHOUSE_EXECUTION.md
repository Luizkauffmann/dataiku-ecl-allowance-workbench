# Warehouse Execution Design
## Snowflake / Databricks without breaking the webapp

The webapp should be the **configuration and orchestration plane**. The Dataiku Flow should be the **execution plane**.

The recommended production pattern is not to have the browser dynamically rewrite a recipe engine. Instead, the browser records a run request and triggers a governed DSS Scenario that builds a predesigned Flow branch.

## Target architecture

```text
ECL Workbench
    │
    │ writes request / parameters
    ▼
ecl_run_requests
    │
    │ trigger
    ▼
DSS Scenario: ECL_WAREHOUSE_RUN
    │
    ├── Build filtered portfolio snapshot
    ├── Join counterparty attributes
    ├── Derive FICO / Moody's / rating / DPD bands
    ├── Apply stage rules
    ├── Expand time horizon where required
    ├── Join curves / matrices / fixed parameters
    ├── Run Saved Model scoring recipes where required
    ├── Project EAD and prepayment
    ├── Calculate discount factors and ECL
    ├── Aggregate instrument/scenario results
    └── Append manifest / audit records
    │
    ▼
cecl_instrument_results
cecl_run_manifest
```

## Why this is preferable

- Recipe engines remain visible and governed in the Flow.
- Dataiku can choose SQL/Spark-compatible execution paths where supported.
- Snowflake/Databricks compute stays close to the data.
- A failed run is visible in Scenario history.
- Model scoring can use standard Dataiku Scoring Recipes.
- The webapp does not need warehouse credentials or raw SQL connection logic.
- The same webapp configuration can route to different execution profiles.

## Execution profiles in V3

### `EXEC_DSS_PYTHON`
Current safe behavior and the right profile for validating the application.

### `EXEC_SQL_IN_DB`
Represents an in-database request. In the public V3 demo it records the request but falls back to Python until a SQL adapter/Flow is wired.

### `EXEC_WAREHOUSE_FLOW`
Designed for a DSS Scenario named `ECL_WAREHOUSE_RUN`. This should become the main production path for warehouse-backed portfolios.

### `EXEC_AUTO`
Future policy: prefer warehouse execution when prerequisites are satisfied, otherwise fall back to Python.

## Snowflake design

Put base inputs, configuration tables and outputs on the same Snowflake connection where practical. Use Prepare/Join/Group/Window/SQL recipes with in-database execution. For model-based branches, prefer an eligible Dataiku Scoring Recipe rather than direct webapp predictor scoring when pushdown is desired.

A useful physical organization could be:

```text
ECL_SOURCE schema
ECL_CONFIG schema
ECL_WORK schema
ECL_RESULTS schema
```

Persist run IDs and as-of dates in every work/result table.

## Databricks design

Use the same logical Flow with warehouse/Delta-backed DSS datasets and compatible SQL/Spark engines. Avoid moving large loan-month expansion datasets into the webapp backend; expansion and aggregation belong in the warehouse/cluster.

## Exact monthly ECL branch

A future exact UDL-style branch can create `ecl_cashflow_work`:

```text
run_id
scenario
instrument_id
month
opening_balance
scheduled_principal
prepayment
closing_balance
ead
marginal_pd
lgd
discount_factor
marginal_ecl
```

Then aggregate instrument/scenario ECL, scenario-weighted instrument ECL, and portfolio ECL.

## Transition matrices in the warehouse

1. Derive the configured state field (`fico_band`, `moodys_band`, etc.).
2. Join `transition_matrices` on matrix ID + scenario + from-state.
3. Use direct default-transition probability for a simple approach, or iterate state distributions across periods for a full transition model.
4. Convert resulting default probabilities into marginal/cumulative PD as required by the math contract.

## Lifetime curves in the warehouse

Join on:

```text
curve_id
scenario
risk_bucket
month
```

The normalized curve shape is intentionally SQL-friendly.

## Fixed parameters in the warehouse

Join on:

```text
parameter_set_id
scenario
category_field/category_value
```

This behaves like a transparent lookup model and is ideal for in-database execution.

## Saved Models in the warehouse

Prefer:

```text
portfolio features
    ↓
Dataiku Scoring Recipe
    ↓
scored PD/LGD/EAD dataset
```

Keep model selection/version in the run configuration regardless of the scoring engine.

## Scenario orchestration contract

The webapp can write a request such as:

```json
{
  "run_id": "IFRS9_20260831_...",
  "framework": "IFRS9",
  "as_of_date": "2026-08-31",
  "method_config_version": "METHODCFG_V2",
  "math_config_version": "MATHCFG_V2",
  "execution_profile_id": "EXEC_WAREHOUSE_FLOW"
}
```

The Scenario consumes the request, builds outputs, and marks the request `COMPLETED` or `FAILED`.

## Safe migration approach

1. Validate V3 with `EXEC_DSS_PYTHON`.
2. Build a separate warehouse Flow branch.
3. Reconcile one run against Python.
4. Wire `ECL_WAREHOUSE_RUN`.
5. Keep `allow_python_fallback=1` while testing.
6. After reconciliation and governance, optionally disable fallback for production profiles.
