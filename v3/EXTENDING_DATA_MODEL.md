# Extending the ECL Data Model

V3 intentionally keeps the required data footprint manageable. A bank implementation can add the following datasets without changing the core architecture.

## Recommended optional datasets

### `collateral_snapshot`
Use when collateral is many-to-many with instruments or needs independent valuation history.

Suggested grain: `as_of_date × collateral_id` with collateral type, valuation date, market value, haircut, source, location and lien position. Add `instrument_collateral_link` when needed.

### `guarantee_snapshot`
Captures guarantors, coverage limits/percentages, guarantee type and guarantor risk attributes.

### `facility_commitment_snapshot`
Separates facility-level committed amounts from loan/account-level draws; useful for CCF/EAD on revolving facilities.

### `origination_risk_snapshot`
Highly recommended for IFRS 9 SICR. Store origination PD/lifetime PD, rating, FICO, LTV and date so current risk can be compared with initial recognition.

### `rating_history`
Monthly or event-based internal/external rating history for transition matrices, SICR, calibration and attribution.

### `payment_history`
Actual payments, misses, cures, partial payments and delinquency transitions for behavioral PD, roll-rate and prepayment analysis.

### `loan_modification_history`
Restructuring, concessions, extensions, refinancing, covenant changes and forbearance history.

### `writeoff_chargeoff_history`
Separate accounting write-offs/charge-offs from default and recovery definitions when required.

### `recovery_curves`
Time-dependent LGD/recovery assumptions by segment/scenario/month-since-default, analogous to lifetime PD curves.

### `cure_rate_curves`
For delinquent/defaulted portfolios where cure behavior materially changes expected cash flows.

### `discount_rate_curves`
Useful when effective interest rate is not simply stored on the instrument; can provide rates or discount factors by product/cohort/currency/month.

### `exchange_rates`
Needed for multi-currency consolidated allowance reporting.

### `portfolio_hierarchy`
Maps exposures to legal entity, business unit, portfolio, subportfolio, region, regulatory segment and accounting segment.

### `model_registry_config`
Business-facing mapping around Dataiku Saved Models / MLflow models: model role, portfolio, Saved Model ID/version, approval status, validity dates and validation ID. This prevents arbitrary unapproved model versions from entering an official run.

### `model_validation_results`
Validation metrics, limitations, calibration/drift tests and approval dates so the run configuration can display governance readiness.

### `management_overlays`
Replace one scalar overlay with a governed table containing overlay ID, as-of date, portfolio, driver, amount, rationale, proposer, approver and status. This makes overlays fully attributable.

### `stage_assignment_results`
Persist stage reason codes by instrument: stage, primary/secondary reason, PD ratio, rating deterioration and DPD. This dramatically improves SICR review.

### `ecl_cashflow_results`
For a true month-by-month UDL/warehouse engine.

**Grain:** `run_id × instrument_id × scenario × period`

```text
period
opening_balance
scheduled_principal
prepayment
closing_balance
ead
marginal_pd
cumulative_pd
lgd
discount_factor
marginal_ecl
```

Keep `cecl_instrument_results` aggregated for application performance.

### `scenario_variable_mapping`
Maps model feature names to approved macro series, lags, transformations and geography levels when many models use different macroeconomic inputs.

### `data_quality_results`
Store data-quality checks by run/as-of date so approval can be blocked when critical controls fail.

## Recommended expansion sequence

The highest-value additions after V3 are:

1. `origination_risk_snapshot`
2. `collateral_snapshot`
3. `management_overlays`
4. `stage_assignment_results`
5. `ecl_cashflow_results`
6. `model_registry_config`

These improve staging, explainability, governance and auditability without forcing the first demo to become too large.
