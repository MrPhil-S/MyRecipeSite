# Future deployment workflow

Last checked: 2026-10-26. This is a planning reference, not authorization to
deploy the deferred custom cooked-date picker. The completed first Pi release
is documented in [the deployment handoff](DEPLOYMENT_HANDOFF_2026-10-24.md).

## Names and environments

| Name | Address | App location | Database | Purpose |
| --- | --- | --- | --- | --- |
| Local development | `http://127.0.0.1:8001/` | `C:\projects\MyRecipeSite\recipe_app_v2` in local Docker | `MyRecipes_DEV` | Build and test changes first |
| **Pi staging** | `http://192.168.1.13:8011/` | `/home/pi/fastapi-preview`; `recipe-fastapi-preview.service` | `MyRecipes_DEV` | Check the release on Pi/ARM before production |
| **Pi production** | `http://192.168.1.13:5000/` | `/home/pi/myrecipes-v2/current`; `recipe-fastapi-production.service` on localhost port 8012 behind Nginx | `MyRecipes` | Live app |

The name **Pi staging** replaces the informal “Pi test” or “Pi preview” in
conversation. The existing systemd service remains named
`recipe-fastapi-preview.service` unless a future deployment deliberately
renames it.

Local development and Pi staging use the **same** `MyRecipes_DEV` database at
`192.168.1.14:3307`. They are separate app installations, not separate data
environments. A local schema or data change to that database also affects Pi
staging. Pi staging currently serves port 8011 directly, while production uses
Nginx on port 5000, so staging alone does not test the production proxy.

Read-only health checks on 2026-10-26 showed both Pi services healthy.
Production pointed to `/home/pi/myrecipes-v2/releases/0220515` and had saves
enabled. The old `uwsgi.service` and original Flask tree were retained for
routing rollback after the first release; verify their status before relying
on them for any future release.

## Normal release path

1. **Create one reviewed release commit.** Start a feature branch from current
   `master`, make and test changes locally, and commit them. Build a release
   archive from a clean, recorded commit, record its SHA256 hash, and verify
   that it contains only the approved code and assets. A daily commit is not a
   deployment. Do not use `git pull` or reset either existing Pi app tree in
   place. Repository pushing is a separate decision; the first Pi deployment
   was made without a Git push.
2. **Promote the exact archive to Pi staging.** Put it in a new versioned
   directory, install pinned dependencies in its own virtual environment,
   switch `recipe-fastapi-preview.service` to that release, and verify
   `/health`, pages, media and the changed feature through port 8011. Use
   uniquely named test records and clean them up, because local development
   shares the staging database. A versioned staging layout would improve the
   current `/home/pi/fastapi-preview` installation.
3. **Plan database changes before production traffic.** Compare the actual
   staging and production schemas. Rehearse an approved migration against a
   suitable test copy, verify existing rows and old-code compatibility, and
   prepare exact success and rollback checks. Schema changes need their own
   checkpoint; do not infer them from a code diff alone.
4. **Back up production.** Use the current
   [`backup_pi.sh`](backup_pi.sh) to capture both databases, release files,
   media, v2 uploads, aliases and configuration. Copy the completed set off
   Pi into the protected C: archive and verify every SHA256 value. The
   off-Pi copy is currently manual, not scheduled.
5. **Stage production beside the running release.** Keep the current port
   8012 app serving users. Start the next version as a separate systemd
   candidate on another localhost port, for example 8013, using the **same
   release archive** tested on Pi staging. Link existing media, reuse the
   persistent `/var/lib/myrecipesite-v2/uploads`, and validate it against
   `MyRecipes` before changing Nginx. Start read-only if appropriate; if the
   candidate must restart to enable writes, do that while the old version is
   still serving users. This avoids the brief 502 seen when the first release
   restarted the public upstream.
6. **Switch and observe.** After an explicit production checkpoint, point
   Nginx port 5000 to the healthy candidate, run `nginx -t`, reload, and test
   the public URL, writes, images and PDFs. Keep the previous app process and
   release available. If the new app fails, restore the previous Nginx route
   and verify it. A code rollback does not automatically restore the database.

The original one-time cutover scripts under `deployment/` assumed legacy
Flask was the previous public route. They should **not** be rerun to perform a
future FastAPI-to-FastAPI upgrade. Write and review a new cutover/rollback
procedure for each release. Never remove or overwrite the existing production
media folders during promotion.

## Example: custom cooked-date picker

The picker exists in local Git branch `feature/custom-cooked-date-picker`,
commit `e4a0f6f`. That branch starts from older commit `aef54ee`; current
`master` has since gained production configuration, deployment tooling and
the recipe-detail template fix. Merge/cherry-pick the feature into a **new
branch from current master** and resolve its overlapping code rather than
deploying the old branch as a release.

The feature changes the recipe-detail UI, cooked action handling, the model,
and migration `recipe_app_v2/migrations/versions/0002_cooked_recorded_dt.py`.
It adds `recipe_cooked_date.recorded_dt`, which records the time of the click
separately from the date the user says the recipe was cooked. Existing rows
would be initialized from `recipe_cooked_dt`. Undo eligibility then uses the
recorded time. The feature commit added JavaScript to
`recipe_app_v2/static/recipe-controls.js`; review that against the project’s
HTMX/Alpine.js requirements and add tests for ordinary and custom dates,
future-date rejection, existing rows, and undo behavior. The feature commit
itself did not add tests.

As verified read-only on 2026-10-24:

- Shared `MyRecipes_DEV` already had `recorded_dt`: 61 cooked rows, zero null
  recorded dates. One row’s recorded date differed from its cooked date.
- Production `MyRecipes` had **no** `recorded_dt` column.
- Neither Pi app installation had the picker code at that inspection.

Recheck those facts before deployment. Because local development and Pi
staging share `MyRecipes_DEV`, the staging database does **not** need another
`ADD COLUMN` if it still has the column. It does need the new app release and
real Pi/ARM feature testing. The local Docker image observed on 2026-10-24
was stale and its recipe-detail page returned 500 from a since-fixed template
error; rebuild from the integrated branch before judging local behavior.

Production needs a separate, reviewed migration after a fresh off-Pi backup.
The proposed `0002` migration adds `recorded_dt` with a current-timestamp
default and backfills existing rows from `recipe_cooked_dt`. Verify production
row counts, null counts, defaults and old-code compatibility after applying
it. This is additive, so the old app should tolerate the extra column, but
confirm that on the actual release before changing traffic. Once custom
history exists, a code rollback should leave `recorded_dt` in place.

**Do not run `alembic upgrade head` on the existing production database as
currently configured.** `recipe_app_v2/migrations/env.py` explicitly blocks
online Alembic operations, and revision `0001` is an offline baseline for
creating an empty schema, not an upgrade to run against existing tables.
Prepare a one-time reviewed migration procedure or deliberately redesign the
migration setup, test it, and get a separate production schema checkpoint.

`AGENTS.md` currently defers this picker and its schema change from Pi
deployments until the user explicitly requests deployment. The release builder
[`build_release.py`](build_release.py) also refuses any `recorded_dt` content.
Change that gate deliberately only when the feature is approved. An example
question about the process does not authorize deploying the feature.

## Checks and rollback for this example

Before production cutover, verify on Pi staging: picker visible, normal
“Mark cooked” still works, a chosen past date is saved, future dates are
rejected, undo uses the **recorded** time, and plan/detail/history displays
remain correct. Verify both ordinary browser submission and HTMX updates.
Check that the release contains the approved migration and that production
schema has been migrated before starting code that queries `recorded_dt`.

After switching public traffic, test the same flows with a uniquely named
owned fixture, then clean it up. Keep the previous production service and
Nginx configuration. If the feature fails, route users back to the previous
code and retain the new column and any real user data. Database restore is a
separate incident decision: restoring an older dump could discard recipes
saved since that dump.
