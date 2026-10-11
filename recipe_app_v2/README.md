# FastAPI migration: read-only preview

A parallel, read-only recipe list and detail view. Legacy Flask source and its existing local
edits are preserved. No production deployment, traffic routing, schema changes,
database writes, or search migration are included.

## Run locally in two PowerShell terminals

Run all commands from `C:\projects\MyRecipeSite`.

Create the **separate** FastAPI environment once (the existing Python 3.9 works):

```powershell
.\MyRecipesVenv\Scripts\python.exe -m venv recipe_app_v2\.venv
.\recipe_app_v2\.venv\Scripts\python.exe -m pip install -r recipe_app_v2\requirements.txt
```

Terminal 1: run the unchanged Flask app on **8080** through the safe local
validation launcher. It verifies the dev target before importing Flask, binds
only to loopback, disables the reloader, and makes its database connections
read-only for comparison. Edit and other write actions will fail in this mode.

```powershell
.\MyRecipesVenv\Scripts\python.exe recipe_app_v2\run_flask_preview.py
```

The existing `python run_dev.py` launcher remains unchanged for normal Flask
development; it binds to all network interfaces and permits writes. It was not
used for read-only milestone validation.

Terminal 2: FastAPI on **8001**:

```powershell
.\recipe_app_v2\.venv\Scripts\python.exe -m uvicorn recipe_app_v2.main:app --host 127.0.0.1 --port 8001
```

Open [Flask](http://localhost:8080/) and [FastAPI](http://localhost:8001/).
Stop either local process with Ctrl+C. Stopping FastAPI has no effect on Flask.
Do not install the new requirements into `MyRecipesVenv`.

## Configuration and read-only behavior

The new app reads `config.ini` from the repository root, or the file path in
`RECIPE_CONFIG`. It reads **only `[dev] db_uri`**, regardless of hostname. The
driver and target must be `mysql+pymysql`, `192.168.1.14:3307`, `MyRecipes_DEV`.
Other targets are rejected before connecting. Credentials are not committed,
printed, or embedded in the container image.
URL query overrides are also rejected, so driver options cannot silently change
the validated database target.

Every new database connection sets `SET SESSION TRANSACTION READ ONLY`.
Application SQL is restricted to read queries, ORM flushes are blocked, and
request sessions roll back on completion. No tables are created on startup.
GET requests neither save search history nor record recipe visits. Forms and
actions that change meal plans or cooking history are deferred to later milestones.

Recipe cards count ingredients excluding group headers and count cooked-date
rows, following Flask's logic. The default sort is creation date descending,
with recipe ID as a stable tie breaker. A to Z and 24-card pagination use GET
requests, server-rendered HTML, and HTMX partial updates. Alpine handles the
preview information toggle. Browser history restoration returns a full page.
Page navigation works without JavaScript. The explicit legacy recipe image,
ingredient image, and source PDF directories are mounted read-only as static
content; the app does not reuse legacy templates or write routes.

HTMX 2.0.4 and Alpine 3.14.9 are vendored with their licenses in `static/vendor`.
Normal browsing requires no CDN connection. `download_vendor.py` is the optional
maintenance utility for fetching those pinned upstream versions.

## Schema and Alembic

`models.py` mirrors all 11 legacy model tables, including actual Flask names such
as `recipe__ingredient`, `recipe__plan__date`, and `ingredient__synonym`. Existing
fields, nullable columns, foreign keys, and uniqueness are retained.

`migrations/baseline_schema.py` is a frozen snapshot for revision `0001`, separate
from the live models. The revision describes creating the existing schema in an
empty database, and can be rendered for **offline review only**:

```powershell
.\recipe_app_v2\.venv\Scripts\python.exe -m alembic -c recipe_app_v2\alembic.ini upgrade head --sql
```

This prints SQL and does not connect to a database. **Do not apply that SQL to
the existing dev database.** All online Alembic commands, including `stamp`, are
disabled in this milestone; even stamping would write migration history. Before
any future migration milestone, verify backups and restore capability, recheck
schema parity, and use the configured `recipe_v2_alembic_version` migration
history table to avoid the legacy Flask `alembic_version` table. No backup,
restore, tag of production, or
production access was performed in this milestone.

## Docker Compose

Docker Desktop with Linux containers and the Compose plugin must be installed.
The same service supports a 64-bit ARM Raspberry Pi via the multi-architecture
Python image, but deployment to the Pi is deferred.

```powershell
docker compose -f compose.fastapi.yml config
docker compose -f compose.fastapi.yml up --build -d
docker compose -f compose.fastapi.yml ps
docker compose -f compose.fastapi.yml down
```

Stop the locally running Uvicorn process first if it already occupies 8001.
Compose starts **only the app**, binds host port 8001 to loopback, and uses the
external dev database. `config.ini`, recipe images, ingredient images, and source
PDFs are mounted read-only; none are sent in the Docker build context. The container runs as a non-root
user with a read-only filesystem and a health check at `/health`.
Existing Flask, Nginx, uWSGI, and Raspberry Pi configuration remain untouched.

## Validation

```powershell
.\recipe_app_v2\.venv\Scripts\python.exe -m unittest discover -s recipe_app_v2\tests -v
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_dev
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_http
.\recipe_app_v2\.venv\Scripts\python.exe -m recipe_app_v2.verify_details
```

Unit tests use an in-memory SQLite database. The other checks read only the dev
database; HTTP parity requires both localhost apps running.

Validated October 11, 2026:

- Eight automated tests pass: target rejection, percent-encoded credentials,
  write guards, pagination and sorting, group-header exclusion, cooking counts,
  partials and history restoration, escaping, empty lists, missing write routes,
  and the online Alembic guard tested without a database connection.
- Dev database reports session read-only enabled; all 11 mapped tables match
  column names, types, nullability, primary keys, foreign keys, and uniqueness.
- Flask on 8080 and FastAPI on 8001 both return HTTP 200.
- All **453 recipes** across **19 pages** match Flask's recipe set, with correct
  ingredient and cooked counts and no duplicate or missing recipe IDs.
- HTMX partials, CSS, both local JavaScript files, health endpoint, and a sample
  legacy image return successfully. POST to the list returns 405.
- Alembic baseline SQL renders offline; online migrations are explicitly blocked.
- Docker Desktop 4.94.0 is installed for the current user (Docker CLI 29.8.2,
  Compose 5.5.1). `docker compose -f compose.fastapi.yml config --quiet` passes.
  After the Windows restart, the Linux engine runs successfully.
- `docker compose -f compose.fastapi.yml up --build -d --wait` builds the image
  and starts `myrecipesite-fastapi-1` with **healthy** status, bound only to
  `127.0.0.1:8001`. The container runs as `recipes`, with its root filesystem,
  config mount, and recipe-image mount verified read-only.
- The container connects to `MyRecipes_DEV` with session read-only enabled;
  schema verification passes for all 11 tables, and `pip check` passes.
- HTTP parity against the actual container passes for all 453 recipe cards
  across 19 pages alongside unchanged Flask on 8080. Health, static assets,
  sample images, HTMX partials, and rejection of POST requests pass.
- No browser visual/interaction check or Raspberry Pi deployment was performed.

For subsequent starts, open Docker Desktop and wait for its engine to become
ready. From the repository root, run:

```powershell
docker compose -f compose.fastapi.yml up --build -d --wait
docker compose -f compose.fastapi.yml ps
```

The first milestone is complete, including container build/startup and HTTP
verification. Both previews are available on their original ports. Review the
preview before proceeding to another feature; production cutover and all
database writes remain deferred.

## Second milestone: recipe details

Recipe cards open `/recipes/{recipe_id}`. Details include ordered ingredients
and ingredient notes, instruction groups with the legacy numbering behavior,
source notes, user notes, cuisine, collections, all recorded times, servings,
recipe/ingredient images, external source links, and available source PDFs.
Existing cooking/view counts and meal-plan status are displayed without changing
them. The back link preserves the list page and sort order. Unknown recipes show
an HTML 404 page. Source links accept only HTTP/HTTPS URLs, and stored text is
escaped. No recipe fields or mapped instruction objects are modified.

The detail ingredient count excludes group headers, consistent with the new
list; Flask's detail heading included group headers in its count. Total time is
also displayed when recorded, even if individual time fields are empty. These
are presentation changes; database values are unchanged.

Validated October 11, 2026:

- All ten unit tests pass, including grouped instruction numbering, stable
  sequence ordering, single/empty instructions, notes, escaping, missing recipes,
  preserved list navigation, and blocked POST requests.
- The rebuilt Docker container is healthy on loopback port 8001, alongside
  unchanged Flask on 8080. Additional asset mounts remain read-only.
- All **453 detail pages** match the legacy queries and safely rendered Flask
  templates for ingredient/instruction/source-note ordering and content, cuisine,
  collections, time fields, notes, cooking counts, and existing visit counts.
- All **1,181 distinct referenced image/PDF assets** return HTTP 200.
- Visit-history row count remains unchanged after the full comparison. The
  existing recipe-list parity check still passes for all 453 cards.

`verify_details.py` runs `legacy_detail_snapshot.py` with the legacy interpreter
and compares its captured output with FastAPI HTTP responses. The snapshot uses
dev-only, read-only connections and renders `recipe.html` directly. It **never
calls Flask's detail route**, which would commit a visit record. Nullable image
names are normalized only in temporary display objects for rendering; mapped
objects and database values are untouched. It does not print recipe content or
credentials to the terminal.

The second milestone is complete. Review the detail page before moving to the
next prescribed feature: search. Manual browser visual testing remains pending.
