# V3 Dataset Catalog

This document separates **operational source data**, **risk/method configuration**, and **run/audit outputs**. A real implementation should be able to replace synthetic sources without redesigning the workbench.

## Core operational datasets

### `portfolio_snapshot`
**Grain:** `as_of_date × instrument_id`

Central balance-sheet / loan population. Recommended fields include instrument and counterparty IDs, product/segment, origination and maturity dates, balances, undrawn amount, effective interest rate, DPD, watchlist/forbearance/default flags, collateral/LTV, rating, currency and geography.

Useful enterprise additions include legal entity, facility/account IDs, accounting classification, origination PD/rating, internal rating, credit limit, amortization type, payment frequency, modification flags, POCI/nonaccrual flags and remaining term.

### `counterparty_snapshot`
**Grain:** `as_of_date × counterparty_id`

Supports individuals and companies. Retail attributes can include FICO, income and DTI. Commercial attributes can include revenue, assets, liabilities, EBITDA, employees, industry, S&P/Moody's/internal ratings, leverage, interest coverage and liquidity ratios.

### `installment_schedule`
**Grain:** `instrument_id × installment_id`

Contractual cash-flow schedule: scheduled date/principal/interest/payment, actual payment fields, remaining balance, amortization type and frequency.

### `default_recovery_history`
**Grain:** default/recovery event

Supports LGD and recovery modeling: default date/balance, recovery dates/amounts, costs, collateral proceeds, recovery type and months since default.

### `macroeconomic_scenarios`
**Grain:** `forecast_vintage × scenario × period × geography × variable`

Examples: unemployment, GDP, HPI, commercial property prices, BBB spread, corporate default rate, interest rates, inflation and personal income. Demo values are synthetic.

## Accounting / scenario configuration

### `scenario_config`
Scenario weights, reasonable-and-supportable horizon, and reversion assumptions.

### `stage_rules`
Versioned IFRS 9 SICR/stage rules such as DPD thresholds, PD-ratio thresholds, rating deterioration, watchlist and forbearance.

### `model_group_config`
Earlier model-group mapping retained for compatibility. V3's richer abstraction lives in `ecl_method_config`.

## V3 risk-method datasets

### `fixed_parameter_values`
**Purpose:** fixed PD, LGD, CCF, or other lookup parameters.

Key dimensions:
```text
parameter_set_id
product_type
parameter_type
scenario
category_field
category_value
value
parameter_version
```

A fixed assumption can still be segmented by FICO band, Moody's band, collateral type, geography, etc.

### `prepayment_curves`
**Grain:** `curve × bucket × scenario × month`

Stores annual CPR, monthly SMM, and cumulative survival.

### `lifetime_pd_curves`
**Grain:** `curve × risk_bucket × scenario × month`

Stores marginal and cumulative PD.

### `transition_matrices`
**Grain:** `matrix × scenario × from_state × to_state`

`state_field` identifies the source/derived variable that selects the current state, for example `fico_band`, `moodys_band`, `risk_grade`, `delinquency_state`, or `internal_rating`.

### `ecl_method_config`
**Grain:** `config_version × product_type`

Product-level orchestration for PD/LGD/EAD/prepayment method and source IDs.

### `ecl_math_config`
**Grain:** `math_config_version × product_type`

UDL-style calculation contract:
```text
loop_level
parent_key
entity_key
child_key
time_step
horizon_method
pd_application
discount_method
discount_rate_field
ecl_formula
aggregation_level
execution_semantics
```

### `ecl_execution_profiles`
Execution-routing choices exposed by the webapp.

### `ecl_run_requests`
Request queue / orchestration contract for a future DSS Scenario-driven warehouse calculation.

## Run and result datasets

### `cecl_run_manifest`
One row per immutable run and the authoritative configuration fingerprint.

Recommended V3+ fields:
```text
run_id
run_label
framework
as_of_date
status
is_official
parent_run_id
scenario weights
stage_rule_version
method_config_version
math_config_version
requested_execution_engine
actual_execution_engine
execution_note
management_overlay
solution_bundle_version
created_by
created_at
configuration_fingerprint
total_exposure
total_ecl
```

For stronger reproducibility, also store explicit Saved Model versions, source snapshot IDs, and macro scenario version IDs.

### `cecl_instrument_results`
Normally `run_id × instrument_id × scenario`; contains stage, PD, LGD, EAD, scenario ECL and weighted ECL. A full installment engine should use a separate detailed cash-flow result table rather than indefinitely widening this table.

### `cecl_attribution_results`
Hierarchical waterfall attribution between runs.

### `cecl_feature_contributions`
Optional model explanation / SHAP or driver-attribution storage.

## Governance and release

### `cecl_governance_status`
Tracks the mock Govern lifecycle today and can later store real Govern artifact/sign-off identifiers.

### `cecl_release_log`
Stores mock GitHub/Bitbucket release-manifest events today; a production version can hold external commit/PR/release references.

See [EXTENDING_DATA_MODEL.md](EXTENDING_DATA_MODEL.md) for recommended additional datasets such as collateral, guarantees, origination risk, overlays and detailed loan-month cash flows.
