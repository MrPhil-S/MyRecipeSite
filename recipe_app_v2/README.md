# FastAPI migration preview

Phase 4 features 1–4 are implemented: recipe list, details, search, and create/edit.
Tag management and meal planning are next. Existing cuisine/collection assignment
is available in the recipe form; managing those tags is a separate feature.

The user authorized **dev-only saves** on October 11, 2026. FastAPI always reads
`[dev] db_uri` from `config.ini` and accepts only
`mysql+pymysql` at `192.168.1.14:3307/MyRecipes_DEV`, without URL query overrides.
Production deployment, routing and schema changes remain deferred.

[Current migration status](../migration_audit_2026-10-11.md) ·
[Phase 1 backup evidence](../phase1_backup_completed_2026-10-11.md)

## Run locally

Run from `C:\projects\MyRecipeSite`. Keep the environments separate:

```powershell
.\MyRecipesVenv\Scripts\python.exe -m venv recipe_app_v2\.venv
.\recipe_app_v2\.venv\Scripts\python.exe -m pip install -r recipe_app_v2\requirements.txt
```

Flask comparison preview on **8080**, unchanged source with writes blocked:

```powershell
.\MyRecipesVenv\Scripts\python.exe recipe_app_v2\run_flask_preview.py
```

FastAPI on **8001**, with authorized dev saves:

```powershell
$env:RECIPE_DEV_WRITES = "1"
.\recipe_app_v2\.venv\Scripts\python.exe -m uvicorn recipe_app_v2.main:app --host 127.0.0.1 --port 8001
```

Omit the variable, or set it to `0`, for form previews without saves. Browsing
always uses a separate server-enforced read-only connection; GETs do not record
visits or search history. Saves use a separate dev-only connection pool.

Alternatively, Docker Desktop must be running:

```powershell
New-Item -ItemType Directory -Force recipe_app_v2/uploads/images, recipe_app_v2/uploads/pdfs | Out-Null
docker compose -f compose.fastapi.yml up --build -d --wait
```

Compose enables dev saves and binds only `127.0.0.1:8001`. It runs the app as a
non-root user with a read-only root filesystem. Configuration and legacy assets
are mounted read-only. The separate `recipe_app_v2/uploads/` folder is writable,
excluded from Git/builds, and persists when the container is replaced. Include
this folder in future backups. Stop FastAPI with `docker compose -f compose.fastapi.yml down`.

Open [FastAPI](http://localhost:8001/) or [Create recipe](http://localhost:8001/recipes/new).
Each recipe detail page links to its edit form.

## Create/edit behavior

Forms support ingredient rows or bulk paste, group headings, ingredient notes,
instructions, source/user notes, times, servings, source/Whisk URLs, existing
cuisines and multiple collections. Start bulk ingredient/instruction headings
with `>`; bulk ingredient notes follow the first comma. Blank lines are skipped.
Individual rows preserve commas in names. Bulk input replaces the displayed rows.

Validation follows existing column limits and retains entered text on errors.
Create/Save validates entries and commits the recipe and its children
in one transaction, preserve hidden metadata/history, and reject stale edits.
Forms require a signed CSRF token and work with or without JavaScript.

Images accept JPEG/PNG up to 8 MB and 20 million pixels, re-encoded to a maximum
1000×1000 JPEG. PDFs accept up to 8 MB with header/end-marker checks. Uploads use
the separate dev folder; leaving them blank preserves existing files. Normal
save failures roll back database and staged files. Database/filesystem changes
are not crash-atomic; prior images and replaced dev PDFs are retained for recovery.

## Validation

```powershell
.\recipe_app_v2\.venv\Scripts\python.exe -m unittest discover -s recipe_app_v2/tests -v
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_dev
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_http
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_editor
```

`verify_editor` compares edit fields with local Flask. Add `--save` with
`RECIPE_DEV_WRITES=1` to create/edit/remove a new dev fixture and compare every
table's data before/after. It does not edit existing recipes. Unit tests use SQLite.

Validated October 11, 2026: 20 tests passed; all 453 edit forms matched Flask;
live dev create/edit and stale-edit rejection passed; the fixture was removed,
with all 12 tables' data unchanged. Browser checks covered HTMX row addition,
error rendering, create/edit, image/PDF uploads and JavaScript disabled.
List/detail parity also passed for 453 recipes, with 1,181 referenced assets loading.
Earlier list/detail/search verification remains in Git history and the existing
verification scripts. No production contact was needed for this feature.

Models retain the existing schema. Alembic revision `0001` is an offline baseline
for an empty database; online upgrade/stamp and destructive downgrade remain
blocked. No tables are created on application startup. Pi/ARM deployment and
full application rollback rehearsal remain untested.
