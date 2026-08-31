# Deployment and Version Control

Use **two independent version-control layers**.

## A. ECL calculation version

Every rerun receives a unique `run_id` and immutable run manifest. A run captures:

- as-of date
- exact portfolio/counterparty snapshot
- scenario vintage and weights
- reasonable-and-supportable horizon
- reversion method
- stage-rule version
- model group and exact Saved Model versions
- management overlay
- solution bundle version
- user / timestamp
- resulting exposure and ECL

Lifecycle:

`SANDBOX -> REVIEW -> PRODUCTION -> SUPERSEDED`

The demo webapp implements the important behavior: **promotion never deletes the previous run**. Promoting an older version is a rollback of the official truth.

## B. Dataiku application / bundle version

This controls the code and Flow logic independently of the accounting run.

Recommended lifecycle:

1. Develop in the Design node.
2. Create a project bundle such as `ECL_APP_1.4.0`.
3. Include required Saved Models / additional content as appropriate.
4. Submit the bundle/model artifacts through the institution's Dataiku Govern approval process.
5. Publish through Project Deployer to the Automation node.
6. Activate the approved bundle.
7. If an application defect occurs, reactivate the prior stable bundle.

Dataiku bundle documentation:
https://doc.dataiku.com/dss/latest/deployment/creating-bundles.html

Deployment governance/policies:
https://doc.dataiku.com/dss/latest/governance/deployment-policies.html

## Why the two layers must stay separate

A finance assumption error should not require an application rollback. Conversely, an application-code defect should not rewrite an already signed-off accounting result.

Example:

- `ECL_APP_1.4.0` can produce both `JULY_FINAL_V1` and `AUG_FINAL_V1`.
- `AUG_FINAL_V2` can supersede `AUG_FINAL_V1` without changing the app bundle.
- If `ECL_APP_1.5.0` has a defect, production can revert to `ECL_APP_1.4.0` while all historical run versions remain preserved.
