# ECL Allowance Workbench V3
## Configurable IFRS 9 / CECL risk methods, math contracts, execution routing, and governance

V3 is an additive evolution of the working Dataiku ECL Allowance Workbench. It is designed to demonstrate how one governed application can orchestrate multiple credit-loss methodologies without forcing every portfolio into the same PD/LGD/EAD technique.

> **Important:** the original root `webapp/` remains the stable V1 demo. Everything in this directory is isolated under `v3/` so you can test and copy it into a separate Dataiku Standard Webapp without breaking the application that already works.

> **Demo only:** all data, formulas, curves, matrices, assumptions, workflows, and model mappings are synthetic/illustrative. They are not validated IFRS 9 or CECL accounting methodologies.

## What V3 adds

V3 introduces four layers that are intentionally independent:

1. **Risk parameter sourcing** — each portfolio can source PD, LGD, EAD, and prepayment differently.
2. **ECL Math Engine** — a UDL-style calculation contract defines calculation grain, hierarchy, horizon, discounting, and formula semantics.
3. **Execution routing** — the run records whether calculation was requested in DSS Python, SQL/in-database, Auto, or a warehouse DSS Scenario; the demo safely falls back to DSS Python until a warehouse Flow is wired.
4. **Governance and release** — sandbox runs can move through a mock Govern lifecycle and produce an immutable GitHub/Bitbucket-style release manifest without changing an external repository.

## Risk methods supported by the configuration model

### PD

- `FORMULA` — deterministic demo formula.
- `FIXED` — fixed PD values, optionally segmented by a field such as FICO band or Moody's band and by economic scenario.
- `SAVED_MODEL` — Dataiku Saved Model / Visual ML integration point.
- `LIFETIME_PD_CURVE` — month-by-month marginal and cumulative PD curves selected by a configurable risk bucket.
- `TRANSITION_MATRIX` — migration matrix selected by a configurable state field such as FICO band, Moody's band, internal rating, risk grade, or delinquency status.

### LGD

- `FORMULA`
- `FIXED`
- `SAVED_MODEL`

### EAD

- `CONTRACTUAL`
- `CCF_FIXED`
- `SAVED_MODEL`

### Prepayment

- `NONE`
- `CURVE`

This allows portfolios to be deliberately heterogeneous. For example:

| Portfolio | PD | LGD | EAD | Prepayment |
|---|---|---|---|---|
| Mortgage | Lifetime PD curve by FICO band | Fixed secured LGD | Contractual | Curve by FICO band |
| Auto | Transition matrix by FICO band | Fixed secured LGD | Contractual | Curve by FICO band |
| Personal Loan | Fixed PD by FICO band | Fixed unsecured LGD | Contractual | None |
| Credit Card | Saved Model placeholder | Fixed unsecured LGD | Fixed CCF | None |
| Commercial Term | Transition matrix by Moody's band | Saved Model placeholder | Contractual | Curve by Moody's band |
| CRE | Lifetime PD curve by Moody's band | Fixed CRE LGD | Contractual | None |
| Equipment Lease | Fixed PD by Moody's band | Fixed secured LGD | Contractual | Curve |
| Revolving Facility | Lifetime PD curve by Moody's band | Saved Model placeholder | Fixed CCF | None |

## UDL-style ECL Math Engine

The math layer is intentionally separate from parameter sourcing. A configuration can say, for example:

```text
Portfolio             Mortgage
Loop level             INSTRUMENT_MONTH
Parent key             counterparty_id
Entity key             instrument_id
Child key              installment_id
Time step              MONTHLY
Horizon                 IFRS9_STAGE_OR_CECL_LIFETIME
PD application          MARGINAL_OR_CUMULATIVE_BY_METHOD
Discount method         EFFECTIVE_INTEREST_RATE
Discount rate field     interest_rate
Formula                 MARGINAL_PD * LGD * EAD * DISCOUNT_FACTOR
Aggregation             INSTRUMENT_THEN_PORTFOLIO
```

Commercial portfolios can instead use a hierarchy such as:

```text
counterparty_id
      ↓
instrument_id
      ↓
month / installment
      ↓
ECL(t)
```

The supplied demo runtime uses a vectorized equivalent for speed and backward compatibility. A future warehouse Flow can implement the exact month-by-month or installment-by-installment expansion while keeping the same configuration contract.

## Architecture

```text
                              ECL ALLOWANCE WORKBENCH

DATA                                  CONFIGURATION
----                                  -------------
portfolio_snapshot ----------------+  ecl_method_config
counterparty_snapshot -------------|  fixed_parameter_values
installment_schedule --------------|  lifetime_pd_curves
macroeconomic_scenarios -----------|  transition_matrices
                                   |  prepayment_curves
                                   |  ecl_math_config
                                   |  ecl_execution_profiles
                                   +-----------+
                                               |
                                               v
                                     CONFIGURE & RUN
                                               |
                                  +------------+-------------+
                                  |                          |
                                  v                          v
                         DSS Python fallback         Warehouse/SQL intent
                                  |                          |
                                  +------------+-------------+
                                               v
                                  cecl_instrument_results
                                               |
                                  cecl_run_manifest
                                               |
                       +-----------------------+--------------------+
                       |                       |                    |
                       v                       v                    v
                    Compare                 Versions        Governance/Release
```

## Repository structure

```text
v3/
├── README.md
├── SETUP.md
├── ARCHITECTURE.md
├── DATASETS.md
├── WAREHOUSE_EXECUTION.md
├── EXTENDING_DATA_MODEL.md
├── generate_v3_csvs.py
├── datasets/
│   ├── fixed_parameter_values.csv
│   ├── prepayment_curves.csv
│   ├── lifetime_pd_curves.csv
│   ├── transition_matrices.csv
│   ├── ecl_method_config.csv
│   ├── ecl_math_config.csv
│   ├── ecl_execution_profiles.csv
│   ├── ecl_run_requests.csv
│   ├── cecl_governance_status.csv
│   └── cecl_release_log.csv
└── webapp/
    ├── body.html
    ├── style.css
    ├── app.js
    └── backend.py
```

The V3 build workflow materializes the webapp and synthetic CSVs into the repository so the files can be opened and copied directly into Dataiku DSS.

## Quick start in Dataiku

1. Keep your currently working webapp as-is.
2. Import the V3 CSVs from `v3/datasets/` using the exact dataset names.
3. Create a **new Standard Webapp**, for example `ECL Workbench V3`.
4. Copy:
   - `v3/webapp/body.html` → HTML tab
   - `v3/webapp/style.css` → CSS tab
   - `v3/webapp/app.js` → JavaScript tab
   - `v3/webapp/backend.py` → Python backend
5. Restart the Python backend.
6. In **Risk Methods**, start with `METHODCFG_V2`.
7. In **ECL Math Engine**, start with `MATHCFG_V2`.
8. In **Configure & Run**, start with `EXEC_DSS_PYTHON`.
9. Create a SANDBOX run and verify Overview and Versions.
10. Test the mock Govern flow before wiring any real external integration.

See [SETUP.md](SETUP.md) for the complete procedure.

## What is real vs. mocked in V3

### Implemented in the demo

- Dataset-driven fixed parameter values.
- Lifetime PD curve lookup.
- Transition-matrix lookup by configurable risk/state field.
- Prepayment curve configuration.
- Product-level method configuration.
- UDL-style math contract storage and display.
- Immutable run creation and parent-run lineage.
- Framework-aware official versioning.
- Requested vs. actual execution-engine tracking.
- Safe DSS Python calculation fallback.
- Mock Govern workflow persisted in DSS datasets.
- Mock GitHub/Bitbucket release manifest persisted in DSS datasets.

### Integration points intentionally left safe

- `SAVED_MODEL` currently records the model selection and uses the deterministic fallback unless you wire direct predictor scoring or, preferably, a Dataiku Scoring Recipe.
- `EXEC_SQL_IN_DB` records SQL/in-database intent but uses the safe Python fallback until a SQL execution adapter is enabled.
- `EXEC_WAREHOUSE_FLOW` is designed to call a DSS Scenario such as `ECL_WAREHOUSE_RUN`; until that Scenario is wired, the app falls back safely.
- Mock Govern does not call a real Govern artifact workflow yet.
- Mock Git release does not push to a real Git remote from the webapp.

## Recommended productionization path

```text
V3 demo
  ↓
Real Dataiku Saved Models / Scoring Recipes
  ↓
Warehouse ECL Flow + ECL_WAREHOUSE_RUN Scenario
  ↓
Real Govern blueprint and sign-off
  ↓
Project bundle / Deployer promotion
  ↓
Optional Git release manifests / external PR workflow
```

## Documentation

- [SETUP.md](SETUP.md) — installation and migration steps.
- [ARCHITECTURE.md](ARCHITECTURE.md) — conceptual architecture and calculation lifecycle.
- [DATASETS.md](DATASETS.md) — detailed dataset catalog and expected grains.
- [EXTENDING_DATA_MODEL.md](EXTENDING_DATA_MODEL.md) — recommended additional datasets for a more complete bank implementation.
- [WAREHOUSE_EXECUTION.md](WAREHOUSE_EXECUTION.md) — recommended Snowflake/Databricks execution design.

## Public-repository safety

No SAS document, proprietary bank data, or third-party proprietary economic dataset is included in this repository. The synthetic macro scenarios, parameter curves, transition matrices, and portfolio examples exist only to demonstrate architecture and workflow.
