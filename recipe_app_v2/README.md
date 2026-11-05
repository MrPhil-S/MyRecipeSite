# FastAPI recipe app

Phase 4 features 1–6 are implemented: recipe list, details, search, create/edit,
tag management and meal planning. The user chose production's plan list grouped
by date added; calendar scheduling is outside this agreed scope. Use **Manage tags** in the header to
create/edit/delete collections, cuisines and synonyms. Deleting a collection or
cuisine confirms the assignment count, removes that tag's assignments and keeps
the recipes. The existing schema is retained.
Connected synonym links form a group: any name finds ingredients using all other
names in that group. Add multiple other names on separate lines in the synonym
form. Deleting a connecting link can split the group; no schema change is needed.

The native development database URL comes directly from `[dev] db_uri` in
the private root `config.ini`. Development mode accepts only `MyRecipes_DEV` at
`192.168.1.14:3307`. For Pi deployment, `RECIPE_APP_ENV=production` selects
`[prod] db_uri` (or `RECIPE_PROD_DB_URI`) and accepts only `MyRecipes` at the
same server. Production saves require the separate `RECIPE_PROD_WRITES=1` flag.
See [the Pi release runbook](../deployment/README.md) before enabling them.

## Run locally

Run natively from `C:\projects\MyRecipeSite` using a separate Python 3.12
virtual environment. The verified environment on this workstation is
`C:\Users\<WindowsUser>\MyRecipeSite_Local\.venv` (Python 3.12.10).
Replace `<WindowsUser>` with the Windows profile folder name in descriptive
paths; the PowerShell commands below use `$env:USERPROFILE` automatically.
The interpreter came from the signed [official Python 3.12.10 installer](https://www.python.org/downloads/release/python-31210/), installed under
`C:\Users\<WindowsUser>\MyRecipeSite_Local\Python312`; it does not replace the old environments.
To recreate it in a **new, empty** location using the installed interpreter:

```powershell
$localRoot = Join-Path $env:USERPROFILE 'MyRecipeSite_Local'
& "$localRoot\Python312\python.exe" -m venv "$localRoot\.venv"
& "$localRoot\.venv\Scripts\python.exe" -m pip install -r recipe_app_v2\requirements.txt
& "$localRoot\.venv\Scripts\python.exe" -m pip check
```

Start the native app in a PowerShell window; **Ctrl+C** stops it:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\recipe_app_v2\start_native.ps1
```

The launcher always uses the repository working directory, loopback
`127.0.0.1:8001`, `[dev] db_uri` from the root private `config.ini`, and
`$env:USERPROFILE\MyRecipeSite_Local\media` for all persistent media. Its
`images/`, `pdfs/`, and `ingredient_images/` directories hold both existing and
new files; the editable alias catalogue sits at the media root. It overrides inherited database,
environment and upload settings for this process and restores them when it
exits. Dev saves and visit tracking are enabled by default. Add `-ReadOnly`
to disable saves and visits, or `-Python C:\path\to\venv\Scripts\python.exe`
to select another native environment. The app validates that the target is
`192.168.1.14:3307/MyRecipes_DEV`; this database is shared with Pi staging.
Use `?log_visit=false` on recipe details during verification to preserve
existing visit history. GETs never save search history. Search history is saved
only on Enter, Search or selection of a previous query; typing, sorting and
pagination do not save. Suggestions show distinct recent queries. Queries over
the existing 100-character history limit are not truncated or saved; live search
still accepts 200 characters.

The local recipe Docker fallback was retired in cleanup Phase 02 after explicit
resource approval. Routine startup uses the native launcher above. The former
container, image and upload volume are unavailable for immediate rollback.
The four Docker setup files and both upload trees were preserved outside the
checkout with SHA256 manifests. The archived cleanup record at
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\cleanup-guidance_20261104`
contains exact recovery paths; see the [deployment guide](../deployment/README.md)
for the current workflow.

For native recovery, stop local writes, back up the current media tree, verify
the selected backup manifest and restore into a new empty location for comparison.
Reconcile newer files and alias changes before restoring the configured Windows
media path; preserve `images/8a665686f0440c45.jpg` and subsequent writes.
Keep private `config.ini`, the native environment and alias seed.
Recreate a broken environment using the Python setup above, then launch and check
`/health` and media. A Docker recovery requires restoring the archived setup files,
rebuilding an image, creating a new volume and seeding it from the reconciled current
Windows media root. A code/runtime rollback does not restore the shared development
database; never replace it with an older dump as part of runtime recovery.

Open [FastAPI](http://localhost:8001/) or [Create recipe](http://localhost:8001/recipes/new).
Each recipe detail page links to its edit form.

Use **Meal plan** in the header, or Add/Remove from plan on recipe cards and
details. Plan changes update with HTMX and also work without JavaScript.
**Mark cooked** is on recipe details and plan cards. Details show the recorded
cooked/view counts. The home page adds a collection carousel and Recently cooked /
Recently visited sorts, preserving search and collection context through actions.
Collection thumbnails use the most frequently cooked recipe; ties and collections
with no cooked history use the newest recipe. Empty collections show a placeholder.
Favorites stays immediately after All recipes, whose thumbnail uses the most
frequently cooked recipe across the library. Each sort offers both directions.
Recipe cards use a compact + Plan / Planned button over the thumbnail.
Deleting a recipe requires confirmation, rejects changed recipes/history and
removes all child records in one transaction; image/PDF files remain for recovery.

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

**Image aliases** in the header manages a separate ingredient-image catalogue;
search synonyms are unchanged. Test ingredient wording there before adding/editing
aliases. Matching normalizes case, accents, punctuation and controlled plurals,
uses whole phrases, prioritizes the primary ingredient over alternatives and
leaves tied matches unresolved. It preserves fresh/dried and other conflicting
variants. New or renamed ingredient rows use the catalogue; unchanged rows retain
their existing mappings until explicitly reviewed. On **Image aliases**, use
**Review recipes** for one image name or **Review affected recipes** for all
proposals. Saving aliases opens that review automatically. The page finds affected
ingredients across recipes and shows current/proposed images; check only the rows
you want and **Apply selected image mappings**. Up to 50 selections commit together,
updating only `recipe__ingredient.name_official`. Stale rows or catalogue changes
reject the entire selection. Recipe wording, notes and other metadata stay intact.
Unresolved matches never clear existing mappings. Recipe editors have no rematch
controls. No blanket remapping has been applied.
Missing ingredient images always use `default_ingredient.jpg`.
Image-alias and tag table headers sort both ways across all pages; filters retain
the chosen order. The Image column sorts by image availability.

The packaged `image_alias_seed.json` seeds image names and reviewed initial aliases.
Edits persist separately in `uploads/ingredient-image-aliases.json`, using a lock,
stale-version checks and atomic file replacement. Include it in uploads backups.
No MariaDB schema changes are required for this release.

Images accept JPEG/PNG up to 8 MB and 20 million pixels, re-encoded to a maximum
1000×1000 JPEG. PDFs accept up to 8 MB with header/end-marker checks. Uploads use
the separate dev folder; leaving them blank preserves existing files. Normal
save failures roll back database and staged files. Database/filesystem changes
are not crash-atomic; prior images and replaced dev PDFs are retained for recovery.

## Validation

```powershell
& "$env:USERPROFILE\MyRecipeSite_Local\.venv\Scripts\python.exe" -m unittest discover -s recipe_app_v2/tests -v
& "$env:USERPROFILE\MyRecipeSite_Local\.venv\Scripts\python.exe" -m tools.verify_dev
```

The maintained unit tests use isolated SQLite fixtures. Cleanup Phase 01 on
October 28, 2026 passed all 76 tests, native home/detail and HTMX responses,
media hashes, alias catalogue, and one owned create/edit/upload/delete fixture
with persistence across restart. All 12 dev-table data hashes and upload hashes
matched after fixture cleanup. The external cleanup archive named above holds
the Phase 01 record, including exact commands and backup locations.

`tools.verify_dev` is read-only, targets `MyRecipes_DEV`, and recognizes the
documented local `recipe_cooked_date.recorded_dt` timestamp/default. It reports
other schema differences for review. Historical Flask parity and Selenium
verifier scripts have been archived; use the isolated maintained unit suite and
the supported native app checks described in cleanup status. The operational
production smoke helper is `deployment/smoke_writes.py`, which requires its
adjacent `deployment/form_parser.py`; it is not a local validation command.

Validated October 12, 2026: 50 tests passed. Central affected-recipe review,
selected-column-only updates, stale-selection rollback and the JavaScript-disabled
browser flow passed using owned dev fixtures. All 12 tables matched after cleanup.
Separate image-alias CRUD, stale saves,
recipe matching and fallback checks passed using owned dev fixtures; all 12 tables
matched their original data after cleanup. Against the saved production audit,
269 of 429 default rows receive proposed matches and 160 remain unresolved; these
proposals have not been applied to either database.
Earlier collection carousel browser checks
passed with HTMX, browser Back, JavaScript disabled and mobile scrolling; thumbnail
choices matched the dev data and all 12 tables stayed unchanged.
Activity/plan/deletion checks used
owned dev fixtures, including HTMX and JavaScript-disabled browser checks;
all 12 tables matched their original data after cleanup. Current list/detail
parity passed for 454 recipes and 1,182 assets; 17 search queries matched the
reference behavior. The plan matched existing active recipes and local Flask.
Earlier validation: all 453 edit forms matched Flask;
live dev create/edit and stale-edit rejection passed; the fixture was removed,
with all 12 tables' data unchanged. Browser checks covered HTMX row addition,
error rendering, create/edit, image/PDF uploads and JavaScript disabled.
List/detail parity also passed for 453 recipes, with 1,181 referenced assets loading.
Tag lists matched Flask; tag CRUD, assignments, synonym search and browser checks
passed. All 12 dev tables matched their pre-test data after fixture cleanup.
Earlier list/detail/search verification remains in Git history and the existing
verification scripts. No production contact was needed for this feature.

Models retain the existing production schema. Alembic revision `0001` is an
offline baseline for an empty database; online upgrade/stamp and destructive
downgrade remain blocked. No tables are created on application startup. The
non-Docker Pi/ARM release went live on October 24, 2026. At the dated
inspection, the original uWSGI service remained installed; its current state
has not been checked. A future v2 release needs a v2-to-v2 rollback plan.
The dated release evidence is preserved in the private Phase 06 archive named
in the [deployment guide](../deployment/README.md).

## Library / Oxblood UI (October 20, 2026)

The database-backed homepage `/` uses Library / Oxblood, and `/recipes/{id}`
uses the Split recipe layout. Meal planning, recipe creation/editing, collection,
cuisine and synonym management, ingredient image aliases/rematches, deletion
confirmations and not-found pages use the same Oxblood navigation, local DM Sans
type and shared controls. The selected Library and recipe layouts remain the
production UI; the design studies have been retired. The selected recipe layouts
omit legacy `app.css`; working forms retain the existing
editor styling and override its colors and controls with the current design.

Recipe links use normal page navigation. HTMX handles list filtering, sorting,
pagination and recipe actions. Library fragments also update sidebar navigation
and counts; recipe actions replace only the detail component. Alpine manages
dropdowns and ingredient/method checkmarks, whose sections survive action updates.
Personal notes come from `Recipe.note_from_user` and appear once below the title
and collections. Ingredient image surfaces are white.

Review corrected legacy style collisions, recipe action swaps, stale sidebar
links/counts, missing mobile cuisine filters, grouped instruction numbering,
and inconsistent badge and empty-state layouts. Verification used isolated
SQLite tests in a network-disabled container and read-only Chrome checks at
desktop, 390px and 320px widths. Browser review files are archived at
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\phase03_20261103_231500\recipe_app_v2\.browser-tools\live-ui-review`.

This UI change introduces no database migration. Planning uses the existing
add/remove queue: `Recipe_Plan_Date.added_dt` is an addition timestamp, not a
scheduled cooking date. User accounts and scheduled-day planning remain separate
implementation work.


## Ingredient image review follow-up (October 14, 2026)

All 518 reviewed ingredient rows now have explicit image choices in
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\phase03_20261103_231500\recipe_app_v2\image-review-analysis-2026-10-14\standardized\ingredient-image-review-decisions-standardized.csv`.
The original export remains unchanged. `Use selected image` denotes a later explicit
user choice; CSV consumers must use `selected_image` for this decision.
No reviewed assignments have been applied to either database.

Matching now uses preparation notes as well as ingredient wording, recognizes
reviewed aliases, and retains shared nouns in supported alternatives such as
"corn or flour tortillas". Notes contribute preparation descriptors without
borrowing ingredients from substitutions or serving suggestions. Incomplete
ingredient rows split before the food name can use the note to recover it.
Unresolved ties still use the default image. The new `turnip` image is registered.

Image-alias previews accept a separate preparation note. Rematch previews display
notes and use the same matching logic when applying selections. Recipe saves use
notes for new/renamed ingredient rows. Existing image mappings remain preserved
on unchanged names, including note-only edits; use explicit rematch review to
change those mappings. Row/catalogue freshness checks still protect saves.

Reviewed aliases are merged into both the packaged seed and the local persisted
catalogue without replacing existing aliases. Include the persisted catalogue
and the new turnip image in any later deployment; production was not changed.
File backups and the change manifest are under
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\phase03_20261103_231500\recipe_app_v2\image-review-analysis-2026-10-14\matcher-code-backup\`.

Validation: 62 isolated unit tests passed before installation. The complete
review comparison improved from 195/518 to 492/518 exact selected-image matches.
This is agreement on the reviewed dataset, not general accuracy. The remaining
26 differences retain the user's CSV choices and are reported separately;
several prefer a generic image or a later ingredient alternative. See
`C:\Users\<WindowsUser>\MyRecipeSite_Local\archives\phase03_20261103_231500\recipe_app_v2\image-review-analysis-2026-10-14\standardized\implementation-results.md`
for installed-code validation and the before/after comparison.
