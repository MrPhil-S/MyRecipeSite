# FastAPI deployment reference

The recorded Pi layout (last read-only check 2026-10-26) has FastAPI production
behind Nginx on public port 5000 and a separate FastAPI staging service on
port 8011. Production uses `MyRecipes`; local development and staging share
`MyRecipes_DEV`. Both Pi applications run through systemd/Uvicorn, without
Docker. Treat these as dated observations and inspect the actual Pi state before
any separately authorized deployment.

The October 24, 2026 first-release evidence and one-time Flask transition
scripts are preserved under
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\phase06_20261103\deployment`.
The dated deployment investigations and six-phase local cleanup record are at
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\cleanup-guidance_20261104`.
These are historical records, not current upgrade or rollback procedures.
The former Flask source remains archived locally; its Pi service and media
retirement require separate work. This file is the maintained deployment guide.
In the paths below, `<WindowsUser>` means the Windows profile folder name.
PowerShell commands use `$env:USERPROFILE` so they work without editing it.

## Environments

| Environment | Address | App location | Database |
| --- | --- | --- | --- |
| Local development | `http://127.0.0.1:8001/` | `C:\projects\MyRecipeSite`; `recipe_app_v2/start_native.ps1` | `MyRecipes_DEV` |
| Pi staging | `http://192.168.1.13:8011/` | `/home/pi/fastapi-preview`; `recipe-fastapi-preview.service` | `MyRecipes_DEV` |
| Pi production | `http://192.168.1.13:5000/` | `/home/pi/myrecipes-v2/current`; `recipe-fastapi-production.service` behind Nginx | `MyRecipes` |

Local development and Pi staging share the same `MyRecipes_DEV` database at
`192.168.1.14:3307`; a local data or schema change affects staging too.
The recorded production `current` symlink pointed to
`/home/pi/myrecipes-v2/releases/0220515` on 2026-10-26. Staging serves port
8011 directly, so it does not test the production Nginx route. Refresh these
facts before a separately authorized deployment.

## Runtime archive

`build_release.py` has an explicit runtime list: application Python,
templates, static assets and licenses, alias seed, and pinned app requirements.
It excludes tests, tools, docs, migrations, local launchers, caches and uploads.
Migration files remain source history; packaging them would not authorize
schema execution. Persistent recipe images, ingredient images, source PDFs,
uploads and the editable alias catalogue belong under the environment's
`RECIPE_UPLOADS` root, outside the source archive. The Pi media copy and
cutover are tracked in [the consolidation runbook](MEDIA_CONSOLIDATION.md).

For a local, **non-deployable** review artifact:

```powershell
$stamp = Get-Date -Format yyyyMMdd-HHmmss
$localPython = Join-Path $env:USERPROFILE 'MyRecipeSite_Local\.venv\Scripts\python.exe'
& $localPython deployment\build_release.py preview "tmp\preview-$stamp.tar.gz"
```

Choose a new output path for each run. Inspect `RELEASE_MANIFEST.json`: it
records the base HEAD, dirty state, each member's hash and whether its preview
bytes came from tracked or untracked working tree source.
Preview artifacts must never be transferred to either Pi.

`release` mode requires a clean working tree and reads each runtime member
from the recorded commit. It fails if a required member, including the shared
icons template, is absent from that commit. It is available only after a
separately authorized review and commit. Both modes reject the deferred
`0002_cooked_recorded_dt.py` migration and custom cooked-date runtime content.
Do not change that guard or deploy the local feature without the user's
explicit instruction under root `AGENTS.md`. The local `recorded_dt` column
remains in `MyRecipes_DEV`.

## Operations and data

Keep `recipe-fastapi-production.service`, `myrecipesite_app.v2`,
`backup_pi.sh`, `smoke_candidate.py`, `smoke_writes.py`, and
`form_parser.py` as separately reviewed operations material. A future smoke
run needs `smoke_writes.py` and its adjacent `form_parser.py` together,
plus access to the installed app release and dependencies for direct-script
imports. The app archive intentionally excludes `deployment/*.py`.
The production write-flag helper remains for review with a future procedure;
none of these tools were run on Pi in Phase 06.

The Pi asset-backup timer was confirmed disabled on 2026-11-05. Its installed
script still covers only the three legacy directories. This branch updates
the source list to the single production media root, but that definition must
not be installed or enabled until media has been copied and a complete new
snapshot verified. Existing NAS snapshots lack v2 uploads and remain
untouched. The `backup_pi.sh` full-snapshot script includes the old media,
production uploads, code, configuration, and both databases; it still expects
old Pi paths. Refresh its source list before later releases. Copy a fresh
complete backup off Pi and verify its hashes before any production change.
Never replace editable aliases with packaged seed data.

## Next FastAPI release

1. Review and commit the intended source changes. Build `release` from a clean
   committed revision; record its commit, manifest, file hashes and archive hash.
   A daily commit is not a deployment, and a `preview` archive is never a
   production artifact. Do not update either running Pi app tree in place.
2. Stage that exact archive in a new Pi staging release directory with its own
   virtual environment. Test `/health`, pages, images, PDFs and the changed
   feature on port 8011. Use only owned test records, because staging shares
   `MyRecipes_DEV` with local development.
3. Compare the actual staging and production schemas. Rehearse any approved
   migration against a suitable test copy and prepare exact rollback checks.
   A code diff alone does not authorize DDL.
4. Take and verify a fresh production backup covering both databases, code,
   configuration, all three media trees, v2 uploads and editable aliases.
   Verify the off-Pi copy before the production checkpoint.
5. Start a separate production candidate beside the running FastAPI release,
   using the same archive tested on staging and the existing persistent media.
   Test it before changing the public Nginx route.
6. At the separately approved cutover, route port 5000 to the healthy candidate
   and test the public app. Keep the previous FastAPI process, release and Nginx
   configuration available for code rollback. A database restore is a separate
   data-loss decision. Write and review a version-specific promotion and
   rollback procedure before doing any of these Pi steps.

The original Flask cutover scripts in the archive do not apply to a
FastAPI-to-FastAPI release. Before media consolidation, the three legacy trees
are reached through release symlinks and new uploads through `RECIPE_UPLOADS`.
The consolidation branch changes readers and backups to one root per
environment; preserve the old trees for rollback until that release is
verified. Follow [the consolidation runbook](MEDIA_CONSOLIDATION.md).

## Deferred cooked-date picker

Root `AGENTS.md` excludes its UI, custom-date handling and `0002` migration
from Pi deployment until the user explicitly requests that feature. The local
`MyRecipes_DEV` database already has `recorded_dt`; do not remove it. The
production schema lacked that column at the dated 2026-10-24 inspection.
Recheck both schemas before planning the feature. The existing Alembic `0001`
is an offline baseline for an empty database; do not run `alembic upgrade head`
on production. The archived `FUTURE_DEPLOYMENTS.md` retains the detailed
historical feature example. No schema change is part of this cleanup.
