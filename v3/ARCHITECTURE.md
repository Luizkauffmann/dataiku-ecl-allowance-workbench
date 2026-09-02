# V3 Architecture

V3 is built around five principles: **method agnostic**, **configuration driven**, **reproducible**, **execution independent**, and **governed**.

## End-to-end architecture

```text
                                    DATAIKU DSS

┌──────────────────────────── DATA FOUNDATION ──────────────────────────────┐
│ portfolio_snapshot         counterparty_snapshot      installment_schedule │
│ default/recovery history   macroeconomic_scenarios   collateral/etc.      │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────── RISK PARAMETER LAYER ─────────────────────────┐
│ PD: Formula | Fixed | Saved Model | Lifetime Curve | Transition Matrix    │
│ LGD: Formula | Fixed | Saved Model                                        │
│ EAD: Contractual | Fixed CCF | Saved Model                                │
│ Prepayment: None | Curve                                                  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────── ECL MATH CONTRACT ────────────────────────────┐
│ Loop level          Parent / entity / child keys                          │
│ Monthly/quarterly   Stage/lifetime horizon                                │
│ Discounting         ECL formula                                           │
│ Aggregation level   Execution semantics                                   │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────── EXECUTION ROUTING ────────────────────────────┐
│ EXEC_DSS_PYTHON     EXEC_SQL_IN_DB     EXEC_WAREHOUSE_FLOW     AUTO       │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
                      ┌──────────────┴──────────────┐
                      ▼                             ▼
              Safe Python runtime          Future Flow/Scenario
                                            SQL / Snowflake /
                                            Databricks / Spark
                      └──────────────┬──────────────┘
                                     ▼
┌──────────────────────────── RESULT / AUDIT LAYER ─────────────────────────┐
│ cecl_instrument_results   cecl_run_manifest   attribution   contributions │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
           Compare                Versions           Govern / Release
```

## Parameter-source abstraction

The calculation runtime should consume normalized risk parameters rather than care where the value came from:

```text
resolve_pd(instrument, scenario, horizon, method_config)
resolve_lgd(instrument, scenario, horizon, method_config)
resolve_ead(instrument, scenario, horizon, method_config)
resolve_prepayment(instrument, scenario, horizon, method_config)
```

That makes a fixed PD and an ML PD interchangeable from the ECL engine's perspective.

### Fixed PD example

```text
Personal Loan
fico_band = Near Prime
scenario = Downside
    ↓
fixed_parameter_values
    ↓
PD
```

### Transition-matrix example

```text
Commercial Term Loan
moodys_band = Ba
scenario = Severe
    ↓
TM_COMM_MOODYS_V2
    ↓
Migration probabilities
    ↓
Default probability / future state distribution
```

### Lifetime-PD example

```text
Mortgage
fico_band = Prime
scenario = Baseline
    ↓
LPD_MORTGAGE_FICO_V2
    ↓
month 1 ... month T marginal/cumulative PD
```

### Dataiku Saved Model example

```text
Credit Card
    ↓
PD_RETAIL Saved Model + exact version
    ↓
Scoring Recipe / predictor
    ↓
PD
```

## Prepayment and EAD

Prepayment is independent from PD. For contractual term loans, a future exact engine can project:

```text
Beginning balance
  - scheduled principal
  - expected prepayment
  = projected ending balance / EAD
```

If a curve provides annual CPR:

```text
SMM = 1 - (1 - CPR)^(1/12)
```

For revolving facilities:

```text
EAD = Drawn + CCF × Undrawn
```

where CCF can itself be fixed or model-driven.

## ECL math contract

The core monthly form is represented as:

```text
ECL(t) = MarginalPD(t) × LGD(t) × EAD(t) × DiscountFactor(t)
```

and then aggregated over the appropriate horizon. The contract stored in `ecl_math_config` describes *how* the engine should execute rather than allowing arbitrary Python inside the webapp.

## IFRS 9 vs CECL

The same infrastructure supports both frameworks while preserving framework-specific rules.

Typical IFRS 9 configuration:

```text
Stage 1 -> 12-month ECL
Stage 2 -> lifetime ECL
Stage 3 -> credit-impaired/lifetime treatment
```

Typical CECL configuration:

```text
Lifetime expected credit loss for in-scope assets
```

Official version uniqueness should include at least `framework + as_of_date`; a real enterprise implementation may also include legal entity and portfolio scope.

## Version hierarchy

```text
Application bundle ECL_APP_1.2.0
       │
       ├── Method config METHODCFG_V2
       ├── Math config   MATHCFG_V2
       ├── Stage config  IFRS9_STAGE_V1
       ├── Macro vintage 2026-08-31
       ├── Saved Model versions
       └── Run IFRS9_20260831_xxx
```

Approved historical runs remain immutable even when the application or models evolve.
