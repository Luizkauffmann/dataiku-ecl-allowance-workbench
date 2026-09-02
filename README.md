# Dataiku ECL Allowance Workbench

A synthetic end-to-end **IFRS 9 / CECL** demonstration for Dataiku DSS. The project separates model development and governance from the monthly allowance workbench: users develop PD/LGD/EAD models in Dataiku, deploy them as Saved Models, bind exact model versions to portfolios, run scenario-based ECL calculations, compare reporting dates, perform what-if reruns, and control the official version of truth.

> **Demo only.** All data in this repository is synthetic. The calculation engine, stage rules, scenario assumptions, and accounting treatments are illustrative and are not a validated IFRS 9 or CECL methodology, accounting policy, or regulatory interpretation.

## V3 — Configurable ECL Engine

The repository now contains an **additive V3 implementation under [`v3/`](v3/README.md)**. The original root `webapp/` remains the stable version that was already tested in Dataiku DSS.

V3 adds:

- PD sources that can be **fixed values, Dataiku Saved Models, lifetime PD curves, transition matrices, or formula logic**.
- Configurable transition-matrix state fields such as **FICO band, Moody's band, internal rating, risk grade, or delinquency state**.
- Dataset-driven **prepayment curves**.
- A UDL-style **ECL Math Engine** that stores calculation grain, hierarchy, time step, horizon, discounting, ECL formula, and aggregation logic.
- Execution profiles for **DSS Python, SQL/in-database intent, warehouse DSS Scenario intent, and Auto**.
- Mock **Dataiku Govern** submission/approval workflow.
- Mock **GitHub/Bitbucket release manifests** for approved calculation configurations.
- Extensive documentation for Snowflake/Databricks execution and additional datasets that can be added in a bank implementation.

Start here:

- [V3 Overview](v3/README.md)
- [V3 DSS Setup](v3/SETUP.md)
- [V3 Architecture](v3/ARCHITECTURE.md)
- [V3 Dataset Catalog](v3/DATASETS.md)
- [Optional Data Model Extensions](v3/EXTENDING_DATA_MODEL.md)
- [Snowflake / Databricks Execution Design](v3/WAREHOUSE_EXECUTION.md)

The V3 assets are generated into `v3/webapp/` and `v3/datasets/` so they can be opened directly in GitHub and copied into Dataiku DSS.

## What the demo shows

- Longitudinal portfolio snapshots for June, July, and August 2026
- Retail and commercial banking products in the same allowance process
- Counterparty snapshots for individuals and companies
- Installment/cash-flow schedules and default/recovery history
- Baseline, Downside, and Severe macroeconomic scenario paths
- Configurable IFRS 9 stage rules and CECL/IFRS 9 framework selection
- Product-level model groups using exact Dataiku Saved Model versions
- Loan-by-loan and scenario-level ECL results
- Period-over-period waterfall attribution with macro and credit-driver drilldown
- What-if reruns that create new immutable SANDBOX versions
- Promotion, supersession, and controlled calculation rollback
- Independent Dataiku project-bundle versioning for application deployment

## Architecture

```text
Data foundation
  Portfolio snapshots + counterparties + installments + defaults/recoveries + macro scenarios
        |
        v
Dataiku model factory
  PD + LGD + optional EAD/CCF Saved Models
        |
        v
ECL Allowance Workbench
  As-of date + framework + model group + stage rules + scenarios + forecast/reversion + overlays
        |
        v
Loan/scenario ECL engine
        |
        v
Results + attribution + reruns + version history
        |
        v
Governed production truth / rollback
```

## Repository contents

```text
.
├── README.md
├── DATAIKU_SETUP.md
├── DEPLOYMENT_AND_VERSIONING.md
├── ECL_demo_data_dictionary.xlsx
├── dataset_summary.json
├── generate_demo_data.py
├── requirements.txt
├── datasets/                 # original operational demo datasets
├── webapp/                   # stable original webapp
└── v3/
    ├── README.md
    ├── SETUP.md
    ├── ARCHITECTURE.md
    ├── DATASETS.md
    ├── EXTENDING_DATA_MODEL.md
    ├── WAREHOUSE_EXECUTION.md
    ├── datasets/             # V3 method/math/governance configuration CSVs
    └── webapp/               # V3 copy-paste DSS webapp
```

## Synthetic portfolio

The demo includes:

- Mortgage
- Auto Loan
- Personal Loan
- Credit Card
- Commercial Term Loan
- Commercial Real Estate
- Equipment Lease
- Revolving Credit Facility

The same `instrument_id` persists across monthly snapshots when the exposure remains on book. The generator intentionally introduces new originations, amortization, payoffs, utilization changes, delinquency migration, FICO/rating deterioration, defaults, collateral changes, and macro forecast changes so the period-over-period allowance waterfall has an explainable story.

## Official seeded runs

The generated data includes these reference runs:

- `IFRS9_20260630_FINAL_V1`
- `IFRS9_20260731_FINAL_V1`
- `IFRS9_20260831_FINAL_V1`
- `IFRS9_20260831_WHATIF_V1`

The deterministic seed makes the demo reproducible. See `dataset_summary.json` and the run manifest after generation for the exact generated totals.

## Fastest Dataiku setup — original version

1. Import the CSV files in `datasets/` into one Dataiku project using the same dataset names.
2. Create a **Standard Webapp**.
3. Paste `webapp/body.html`, `webapp/style.css`, `webapp/app.js`, and `webapp/backend.py` into the matching tabs.
4. Enable/restart the Python backend.
5. Keep **Allow demo fallback** enabled for the first run.
6. Open the August official run and compare July -> August.
7. Create an August what-if rerun by changing scenario weights or stage thresholds.
8. Train Dataiku PD/LGD models and replace `DEMO_FORMULA` model-group assignments with exact Saved Model versions.

Full instructions: [DATAIKU_SETUP.md](DATAIKU_SETUP.md)

## Recommended first Saved Models

Start small:

- `PD_MORTGAGE` — binary classification
- `PD_COMMERCIAL` — binary classification
- `LGD_SECURED` — regression
- `LGD_UNSECURED` — regression

Use contractual balance projection for term-loan EAD initially and a CCF-style approach for revolving exposures. Additional product-specific models can be introduced later without redesigning the workbench.

## Model-version principle

A run should reference an exact model version, not merely a model name. For example:

```text
PD model: PD_COMMERCIAL
Saved Model version: 11
```

A September retrain must not mutate an approved August allowance run.

## Version-control principle

The demo intentionally separates two concepts:

1. **Calculation version** — portfolio snapshot, model versions, scenario vintage/weights, stage rules, overlays, and resulting ECL.
2. **Application version** — Dataiku Flow/webapp/calculation code promoted through project bundles and Deployer.

An accounting rerun should not require application rollback, and an application rollback should not rewrite historical signed-off calculations.

See [DEPLOYMENT_AND_VERSIONING.md](DEPLOYMENT_AND_VERSIONING.md).

## Regenerating the original data

Locally:

```bash
pip install -r requirements.txt
python generate_demo_data.py
```

The repository also includes a manual GitHub Actions workflow, **Regenerate synthetic demo data**, which regenerates the original CSV datasets, data dictionary, and summary using the deterministic seed.

## Public-repository note

No proprietary bank data or third-party source documents are included in this repository. **The SAS IFRS 9 reference document is not published in this repository.** The macroeconomic series, transition matrices, PD/prepayment curves, and other configuration data are synthetic and designed only to demonstrate the structure of a configurable expected-credit-loss platform.
