# Local development tools

Run commands from the repository root with the native Python environment.

- `python -m tools.verify_dev` performs a read-only schema/card audit against `MyRecipes_DEV`. It refuses other databases or non-read-only sessions. It recognizes only the known local `recipe_cooked_date.recorded_dt` timestamp column/default; all other schema differences remain errors.
- `python -m tools.download_vendor` downloads pinned HTMX 2.0.4 and Alpine.js 3.14.9 assets and their licenses into `recipe_app_v2/static/vendor`. Run only when intentionally refreshing those vendor files; Phase 05 did not run it.

The operational `deployment/smoke_writes.py` uses `deployment/form_parser.py`. Both files must be copied together to the Pi incoming operations directory during a future separately authorized deployment. The release builder does not package `deployment/*.py`. The smoke script requires `--execute`, production environment settings, and writes to production; do not run it as a local validation command.
