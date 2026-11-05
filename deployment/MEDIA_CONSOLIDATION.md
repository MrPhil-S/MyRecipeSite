# Persistent media consolidation

This is the release plan for moving existing recipe images, source PDFs,
ingredient images, new uploads, and editable aliases under one persistent root
per environment. It does not authorize the deferred cooked-date picker or a
database migration. Keep the public URLs `/recipe-images/`, `/source-pdfs/`,
and `/ingredient-images/` unchanged.

As of 2026-11-05, the local media copy was SHA256-verified and the native
candidate passed its read checks. The Pi staging copy was also SHA256-verified;
the running staging service still uses its old code. Production media and
production routing have not been changed. A fresh full Pi snapshot was
verified on Pi and copied to
`$env:USERPROFILE\MyRecipeSite_Local\archives\media-consolidation_20261105T074558Z`;
all three off-Pi artifact hashes matched. The separate staging uploads copy
was also verified. The Pi source snapshot is
`/home/pi/myrecipesite-deploy-backups/snapshot-20261105T074558Z`.

## Destination layout

| Environment | Persistent root (`RECIPE_UPLOADS`) |
| --- | --- |
| Local development | `$env:USERPROFILE\MyRecipeSite_Local\media` |
| Pi staging | `/home/pi/fastapi-preview-data/uploads` |
| Pi production | `/var/lib/myrecipesite-v2/uploads` |

Each root contains `images/` for old and new recipe photos, `pdfs/` for old
and new source PDFs, `ingredient_images/` for the ingredient catalogue, and
`ingredient-image-aliases.json` when aliases have been edited. Staging and
production keep separate writable roots so staging saves cannot alter live
production media. Runtime releases contain code and static UI assets only.

## Observed Pi state before migration (2026-11-05)

- Production: 443 legacy recipe images, 48 custom-print PDFs, 844 ingredient
  images, and 2 new upload images. The aliases file is in the production root.
- Staging: the same legacy directories are linked into its app tree, with 1
  new image in its separate upload root.
- There were no filename collisions when comparing either environment's
  `images/` and `pdfs/` directories against the legacy files.
- Production and staging were active. The asset-backup timer was disabled;
  its installed source list covered only the three legacy trees and omitted
  v2 uploads. A complete new backup is required before moving media.
- The production release resolved to `/home/pi/myrecipes-v2/releases/0220515`.
  Refresh all observations before executing the cutover.

## Promotion sequence

1. Verify a fresh full Pi snapshot of both databases, app code, configuration,
   services, all three legacy media trees, and both v2 upload roots. Copy it
   off Pi and verify archive hashes. Preserve the original source folders.
2. Record file counts and SHA256 manifests. Use
   `deployment/consolidate_media.py staging --apply` and, after the production
   checkpoint, `deployment/consolidate_media.py production --apply` on the Pi.
   The script's default mode is read-only. Copy the three legacy trees into
   `images/`, `pdfs/`, and `ingredient_images/` under each environment root.
   Never overwrite an existing file. Compare every source and destination
   hash and reconcile changes made during the copy before switching readers.
3. Build a committed runtime release from this branch. Confirm its manifest
   excludes the deferred cooked-date picker. Test the new code against the
   complete staging media root and `MyRecipes_DEV` on port 8011, including
   existing and new images, PDFs, aliases, recipe book, and upload writes.
4. Start a separate production candidate using the same runtime archive,
   the existing production `RECIPE_UPLOADS` setting, and `MyRecipes`.
   Verify it before changing Nginx. At the production checkpoint, route port
   5000 to the candidate and test reads and writes with an owned fixture.
5. Replace the installed asset-backup definition with the reviewed single
   production media-root source. Make a complete verified new NAS snapshot
   before enabling the timer. The old incomplete snapshots remain untouched.
6. After the new release and backups are verified, archive the three old Pi
   media directories off Pi and remove the release symlinks. Check that no
   active service or backup job references the old paths. Keep the verified
   archive for the rollback window; remove old copies only by a separately
   reviewed cleanup step.

## Rollback

Before retiring the old directories, restore the saved Nginx route and
previous production service/release. The previous code still reads its legacy
paths. Keep the new media root and its new uploads intact; a code rollback
does not restore database or media state. If old directories have already
been retired, restore their verified archive before starting the old release.
Do not restore an older database dump merely to roll back application code.

The release has no DDL. Root `AGENTS.md` continues to exclude the cooked-date
picker and its `recorded_dt` migration from Pi deployment.
