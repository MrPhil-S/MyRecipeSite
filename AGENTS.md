# Repository guidance

## Deferred deployment feature

- The custom cooked-date picker on recipe detail pages is deferred from Pi deployment.
- Until the user explicitly says to deploy this feature, exclude its date-picker UI, custom-date request handling, and `recorded_dt` schema migration (`recipe_app_v2/migrations/versions/0002_cooked_recorded_dt.py`) from Pi deployments.
- The feature may remain enabled in the local app. Preserve the user's other requested changes when preparing a deployment that excludes this feature.
- The `recorded_dt` column has already been added to the local `MyRecipes_DEV` database and its existing rows were initialized. Do not remove it as part of deployment staging.
- Production must remain untouched unless the user explicitly requests a production deployment.
