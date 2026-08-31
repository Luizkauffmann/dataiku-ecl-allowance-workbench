# Dataiku Setup

## 1. Import the CSV datasets

Create Dataiku datasets with these exact names for the easiest setup:

- portfolio_snapshot
- counterparty_snapshot
- installment_schedule
- default_recovery_history
- macroeconomic_scenarios
- scenario_config
- stage_rules
- ratings_mapping
- model_group_config
- cecl_run_manifest
- cecl_instrument_results
- cecl_feature_contributions
- cecl_attribution_results

The webapp can remap names later, but exact names enable automatic discovery.

## 2. Create a Standard webapp

In the Dataiku project:

1. New Webapp -> Standard webapp.
2. Paste `webapp/body.html` into the HTML tab.
3. Paste `webapp/style.css` into the CSS tab.
4. Paste `webapp/app.js` into the JavaScript tab.
5. Enable the Python backend and paste `webapp/backend.py` into the Python tab.
6. Restart the backend and open the webapp.

The app uses native browser JavaScript and SVG; no third-party front-end library is required.

Dataiku standard webapps can call Python Flask backend routes through `getWebAppBackendUrl(...)`, and the backend has access to project datasets and Python APIs:
https://doc.dataiku.com/dss/latest/webapps/introduction.html
https://developer.dataiku.com/latest/tutorials/webapps/standard/basics/index.html

## 3. Permissions

The webapp backend needs:

- read access to the mapped input datasets;
- read access to Saved Model metadata;
- ability to score selected Saved Models;
- write access to `cecl_run_manifest`, `cecl_instrument_results`, and optionally `cecl_feature_contributions` if reruns should persist.

## 4. Train Dataiku models

The webapp intentionally does not train models. Train/deploy them in the Flow and keep them as governed Saved Models.

Suggested models:

- `PD_MORTGAGE`
- `PD_RETAIL`
- `PD_COMMERCIAL`
- `LGD_SECURED`
- `LGD_UNSECURED`
- `LGD_COMMERCIAL`
- optional `CCF_CARD` / `EAD_REVOLVING`

Dataiku exposes Saved Models and versions through the project API, and `dataiku.Model.get_predictor(version_id=...)` can score compatible models directly:
https://developer.dataiku.com/latest/api-reference/python/projects.html
https://developer.dataiku.com/latest/api-reference/python/ml.html

## 5. First demo path

1. Open **Overview** and select `IFRS9_20260831_FINAL_V1`.
2. Open **Compare** and compare July official -> August official.
3. Click `Macroeconomic scenario paths` in the waterfall.
4. Click `Downside` to drill into unemployment, GDP, HPI, spreads, etc.
5. Open **Configure & Run**.
6. Change scenario weights or stage thresholds.
7. Run & save. The new result is `SANDBOX`.
8. Open **Versions** and inspect the new version.
9. Promote only after review. The prior official run becomes `SUPERSEDED`, not deleted.
10. Promote an older superseded version to demonstrate controlled rollback.

## 6. Model-group demo

In **Configure & Run**, each product receives:

- PD Saved Model + exact version
- LGD Saved Model + exact version
- EAD method + optional EAD Saved Model/version

This preserves reproducibility: a later retrain does not mutate the previously approved ECL run because the run manifest records the chosen model version.

## 7. Current demo scoring limitations

Direct predictor scoring is best suited to compatible in-memory Saved Models. Dataiku documentation notes limitations for direct Saved Model scoring, including partitioned models and containerized execution. For a production architecture, use standard scoring recipes or a deployed scoring service when those constraints matter:
https://developer.dataiku.com/latest/concepts-and-examples/ml.html
