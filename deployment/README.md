# Pi release runbook

The production Pi is `192.168.1.13`; its live Flask application is served by
Nginx on port 5000 through `uwsgi.service`. The FastAPI test application is a
separate, non-Docker systemd service on port 8011 and uses `MyRecipes_DEV`.
Neither existing application tree should be updated in place. Do not use
`git pull`, `git reset`, or a Docker deployment on the Pi.

## Release contents and exclusions

Build a release from the reviewed `recipe_app_v2` source, pinned requirements,
and its tracked static files. Record the Git commit and the hash of the release
archive. Verify the actual archive contains no cooked-date picker, custom-date
request handler, or `recorded_dt` migration. The local development database's
existing `recorded_dt` column is outside this release and must be left alone.
Do not run Alembic or any DDL against the Pi databases for this release.

The Git tree does not contain all production images. In the separate release
root, create `myrecipes/static/` with symlinks to the existing Pi asset paths:

| Release path | Existing target |
| --- | --- |
| `recipe_images` | `/var/lib/myrecipesite/recipe_images` |
| `ingredient_images` | `/var/www/MyRecipeSite/myrecipes/static/ingredient_images` |
| `custom_prints` | `/var/lib/myrecipesite/custom_prints` |

Keep their existing files, paths, ownership, and permissions unchanged. Put new
FastAPI uploads and the writable image-alias catalogue in a separate persistent
directory, selected through `RECIPE_UPLOADS`. The packaged
`image_alias_seed.json` is included with source, but local persisted alias edits
need an explicit comparison before migration. Existing ingredient image mappings
in `recipe__ingredient.name_official` stay in the database; deploying an alias
catalogue does not automatically rematch rows.

## Backup and restore

The initial Pi backup set is
`/home/pi/myrecipesite-deploy-backups/pre-v2-20261024T071021Z`.
`backup_pi.sh` also captures `MyRecipes_DEV`, both application trees, live media,
and the production Nginx/uWSGI and test service configuration. It validates both
database dumps and the archive, then writes `SHA256SUMS`. Copy this set to the
separate C: archive and verify hashes there before changing the production site.
The archive contains credentials and recipe data; restrict access to the owner.

Before cutover, make a fresh backup after any intervening recipe edits. Record
the existing Nginx configuration and uWSGI status. The candidate systemd unit
`recipe-fastapi-production.service` starts a separate non-Docker app on
`127.0.0.1:8012`, with production writes disabled at first. Stage and validate
that instance, then switch only the production Nginx upstream at the agreed
checkpoint. Keep uWSGI and its application tree ready for immediate routing
rollback. The existing port 8011 test app stays separate.

Rollback for an app or layout failure: restore the original Nginx site file,
run `nginx -t`, reload Nginx, and verify a production page and uWSGI health.
For this staging run, the original site file is also copied to
`/home/pi/myrecipes-v2/incoming/myrecipesite_app.legacy`; the tested candidate
is `/home/pi/myrecipes-v2/incoming/myrecipesite_app.v2`. The replacement sends
the public port 5000 to the local port 8012 and preserves the Host header and
its port. If Nginx validation fails, restore the legacy file before any reload.
If post-switch smoke checks fail, restore it and reload immediately.
Database restore is only for verified data corruption, after stopping both
writers, taking a new incident snapshot, and confirming the restore point with
the user. An automatic database restore could discard recipes edited after the
backup. Restore media only if it was independently damaged; cutover must not
modify it.

## Environment gates

`RECIPE_APP_ENV=dev` is the default. Production mode requires
`RECIPE_APP_ENV=production`, a valid `[prod] db_uri` from `RECIPE_CONFIG` or
`RECIPE_PROD_DB_URI`, and a stable `RECIPE_CSRF_SECRET_HEX` of at least 32 bytes.
`RECIPE_PROD_WRITES` defaults to off. Development and production database
settings cannot be mixed. Use a separate Pi systemd environment file with mode
600 outside Git. Never print the URI or secret in a deployment log.

The `/health` endpoint reports the selected environment, database, and write
state. Validate it before opening traffic and again after cutover. Test list,
detail, search, plan, tags, ingredient images, and PDFs. Only after those checks
and a second explicit checkpoint should production writes be enabled and a
create/edit/action flow be tested with a recoverable fixture.

[Staging evidence for the current release](release_20261024.md).
