# Persistent media consolidation

## Release snapshots copied to the NAS (2026-11-08 Pacific time)

`deployment/backup_production_release.ps1` now requires three verified copies
for each release checkpoint: the original Pi snapshot, an off-Pi Windows copy,
and a NAS copy under `MyRecipeSite/release-backups/<ReleaseName>/<snapshot>`.
The Pi helper is installed at
`/home/pi/myrecipesite-deploy-backups/copy_release_snapshot_to_nas.py`.
It copies each release snapshot into a new NAS folder and verifies all files
against the Pi snapshot before reporting success. The nightly job does not
write to `release-backups`; use both `-Phase Before` and `-Phase After` during
each production deployment. Include `release-backups` when configuring the
Synology Hyper Backup off-site task. Full snapshots contain private settings.

## Backup folder names and archive (2026-11-08 Pacific time)

The active NAS folders are now `MyRecipeSite/media` and
`MyRecipeSite/databases`, each with `daily/` and `monthly/` snapshots. The
existing snapshots from the former `consolidated-media` and
`consolidated-databases` folders were moved into these active folders; the
nightly job continues in the same series. The older, pre-consolidation
`MyRecipeSite/daily` and `MyRecipeSite/monthly` folders were moved to
`MyRecipeSite/archive/pre-consolidation-2026-10-27/`. The archive is excluded
from automated backup retention. Historical paths in the dated sections below
describe where snapshots were originally created. The former and installed
backup scripts, one-time rename helper, and service files are saved at
`/home/pi/myrecipesite-deploy-backups/nas-folder-rename-20261108`.

## Nightly database backup added (2026-11-08 Pacific time)

On this date, `myrecipesite-assets-backup.timer` began backing up both
`MyRecipes` and `MyRecipes_DEV` near 03:15 Pi local time. The original NAS
destination was `MyRecipeSite/consolidated-databases`; it has since moved to
`MyRecipeSite/databases` as recorded above.
Database and production-media series each retain 30 daily and 12 monthly
snapshots. Both database dumps and their monthly copies were created and
verified on the NAS on 2026-11-08; the updated systemd service completed
successfully, and the timer remains active. The previous media-only snapshots
were left intact. The full Pi app/configuration snapshot script remains a
manual step before a production release or settings change; app release files
are not copied by the nightly job. The Windows
`deployment/backup_production_release.ps1` command now runs that step before
and after a release, copies each snapshot to the NAS and Windows, and verifies
all three copies. The old installed backup script and units are saved at
`/home/pi/myrecipesite-deploy-backups/nightly-pre-db-20261108`.

## Legacy folder retirement (2026-11-07 Pacific time)

Production database settings were copied to
`/home/pi/myrecipes-v2/database-config.ini` (mode 600, owned by `pi`).
`/home/pi/myrecipes-v2/production.env` now points `RECIPE_CONFIG` there.
Staging's private `config.ini` and `.env` are under
`/home/pi/fastapi-preview-data` (also mode 600). Staging now uses
`/home/pi/fastapi-preview-releases/current`, which points to
`media-4c74a2b`; its service has no dated override or old staging-root path.
The maintained full-backup script at
`/home/pi/myrecipesite-deploy-backups/backup_pi.sh` reads the new private
database config and includes staging's persistent data directory.

A fresh full snapshot of both databases, current code/settings, and all old
and new media passed archive and SHA256 checks on the Pi. Its off-Pi copy
passed matching hashes for all three artifacts. The protected locations are:

- Pi: `/home/pi/myrecipesite-deploy-backups/snapshot-20261108T063945Z`
- PC: `$env:USERPROFILE\MyRecipeSite_Local\archives\legacy-retirement_20261108\snapshot-20261108T063945Z`

Nine old paths were then **moved, not deleted**, into
`/home/pi/myrecipesite-retired/legacy-20261108` (private root-owned folder).
The archive's `PATHS.json` maps every original path to its new location.
It includes both old Flask checkouts, the old staging app tree, old media,
the `0220515` production and `media-430f3d2` staging releases, the old
incoming deployment folder, an older manual backup script, and the old
uWSGI configuration. The other old manual backup script is in the archived
incoming folder. The retired uWSGI service remains masked; the old Flask
service remains disabled.

Both active FastAPI services were restarted after the move. Their health,
library, plan, image-alias, recipe-photo, ingredient-image, and source-PDF
requests passed on ports 5000 and 8011. The nightly media backup timer
remains active. The maintained full-backup script's current paths and shell
syntax were checked. Its previous full execution was the verified snapshot
above.

To reverse only the folder move, use the saved mapping on the Pi and move
each archived path back to its original location after verifying it is free.
Do not overwrite a new path. The archived old releases require their media
trees restored before a rollback to the old media-reading code. Restoring
folders does not enable old services or change either database. The Pi copy
and off-Pi snapshot contain private credentials: keep them out of Git.

## Earlier consolidation record

The following sections describe the completed migration and its original
rollback design. Their old paths are historical; the retired archive above
records where those folders are stored now.

This was the release plan for moving existing recipe images, source PDFs,
ingredient images, new uploads, and editable aliases under one persistent root
per environment. It does not authorize the deferred cooked-date picker or a
database migration. Keep the public URLs `/recipe-images/`, `/source-pdfs/`,
and `/ingredient-images/` unchanged.

Consolidation was deployed on 2026-11-05 Pacific time (2026-11-06 UTC).
Local, Pi staging, and Pi production now read and write media under their
respective persistent roots. No database migration was run.

- Runtime commit: `4c74a2b9fbd666b473358028fdaf577f2dddf611`.
- Production: `/home/pi/myrecipes-v2/current` points to
  `/home/pi/myrecipes-v2/releases/media-4c74a2b`.
- Staging: `/home/pi/fastapi-preview-releases/media-4c74a2b`.
  Its existing override filename remains
  `/etc/systemd/system/recipe-fastapi-preview.service.d/10-media-430f3d2.conf`;
  its contents now select `media-4c74a2b`. Inspect the contents, not the filename.
- The same 72-file archive was installed in both Pi environments. SHA256:
  `22362b287dfd8ed7ab808f6379232bbb53431d7fc89730e32325288ecd3dba07`.
- Production has 445 photos (443 copied plus 2 existing), 48 PDFs and 844
  ingredient images. Every copied source matched its destination SHA256.
  The production editable alias file was preserved byte for byte.
- Both Pi environments passed create, image/PDF upload, edit, plan, cooked,
  favorite and delete checks. Owned fixtures 3724 (staging) and 3662
  (production), including their uploads, were removed.
- 89 isolated unit tests passed. Production candidate/public read checks,
  browser image checks and existing PDF hash checks passed. No production
  recipe refers to a missing image file. This is not a check of every image's
  visual quality; legacy empty/unreferenced files were copied unchanged.
- Local was restarted on port 8001. The one image referenced by DEV but
  missing locally was copied from staging and hash-verified; existing local
  files and aliases were not overwritten. Local and staging share DEV data
  but not media: a future upload in one still needs copying to the other
  if both must display it. Automatic media synchronization is not introduced.
- Nginx and public ports were unchanged. Old media trees and previous
  releases remain available for rollback; they are no longer active media
  sources for the consolidated app. Do not delete them during the rollback window.

## Verified recovery copy

Pi snapshot: `/home/pi/myrecipesite-deploy-backups/snapshot-20261106T063334Z`.
Off-Pi snapshot:
`$env:USERPROFILE\MyRecipeSite_Local\archives\media-consolidation_20261106T063334Z\snapshot-20261106T063334Z`.
Both database dumps and `pi-files.tar.gz` passed SHA256 verification on the
PC. Archive checks confirmed coverage of both upload roots, old media,
releases, environment files and staging overrides. Dumps passed gzip and
table-count checks; a full database restore rehearsal was not performed.
These backups contain secrets and must remain outside Git.

Saved pre-cutover service files, previous release target and the one-time
promotion script are in
`/home/pi/myrecipesite-deploy-backups/media-cutover-4c74a2b`.
The production service was updated to remove legacy-media `ReadOnlyPaths`.
Its writable path remains `/var/lib/myrecipesite-v2/uploads`.

## Scheduled production media backup

`/usr/local/sbin/myrecipesite-assets-backup.py` now backs up the whole
production root. A verified 1,339-file daily snapshot and monthly copy were
created on the NAS under
`//192.168.1.14/pi_myRecipes_backup/MyRecipeSite/consolidated-media`:
`daily/2026-11-05` and `monthly/2026-11`. Sample photo, PDF, ingredient image
and aliases were restored to a separate test folder and matched the manifest
hashes. Existing snapshots in the old NAS layout were left untouched.

`myrecipesite-assets-backup.timer` is enabled for 03:15 Pi local time with up
to five minutes of randomized delay. It retains 30 daily and 12 monthly
snapshots. This job protects production media only, not either database or
staging media; full deployment snapshots cover both databases and Pi media
roots. The temporary read-only candidate service on port 8014 was stopped.

Follow-up verification on 2026-11-07 confirmed both Pi apps healthy on the
same release and the unattended 03:16 backup completed successfully with
1,339 files. The timer remains enabled.

## Retirement audit before the folder move

### Retirement audit on 2026-11-07: NOT cleared for removal

Both current release manifests matched the deployed commit. An isolated
production candidate passed health, library, plan, tag, alias, recipe-photo,
ingredient-image and existing PDF-download checks with all three legacy media
directories and both old versioned releases inaccessible. This verifies the
tested FastAPI readers, not all remaining services on the Pi.

Remaining retirement dependencies:

- Production still requires `/var/www/MyRecipeSite/config.ini`; staging
  requires `/home/pi/fastapi-preview/.env` and its `config.ini`. Do not remove
  these parent directories wholesale.
- Older backup scripts at `/home/pi/backup_pi.sh` and
  `/home/pi/myrecipes-v2/incoming/backup_pi.sh` still require old parent trees.
  The current nightly backup uses only the consolidated production root;
  older manual scripts must be retired or clearly superseded.
- The one-time `consolidate_media.py` script and documented old-release
  rollback intentionally need legacy media. Update/archive these procedures
  when retiring their sources.

The full-library `/recipe-book.pdf` test caused severe Pi memory pressure;
both public health checks and new SSH connections subsequently timed out.
The user power cycled the Pi. On reboot, both public health checks, sample
recipe photo, ingredient image and source PDF reads passed again. Production
and staging services are active, available memory recovered, and both
temporary test units disappeared. The previous isolated candidate verified
normal readers but **did not verify full-book PDF generation**. Do not repeat
that test without a strict memory limit and a small data fixture.

The reboot confirmed that six legacy uWSGI workers started automatically and
the failed old `myrecipessite.service` was still enabled. Both startup paths
were subsequently disabled: `myrecipessite.service` is disabled and inactive;
the only uWSGI app link was moved from `/etc/uwsgi/apps-enabled` to
`/home/pi/myrecipesite-deploy-backups/legacy-services-disabled-20261107/`,
and `uwsgi.service` is masked and inactive. Its six workers exited. The saved
service unit and uWSGI configuration are in that same backup folder. To undo
this change, restore the archived app link to `/etc/uwsgi/apps-enabled`,
unmask and start `uwsgi.service`, and enable the old Flask service only if it
is actually needed. Do not restore old app services merely to roll back the
current FastAPI release.

After disabling the legacy startup paths, both FastAPI services passed
health, library, recipe-photo, ingredient-image, and source-PDF checks.
The nightly consolidated media backup remains enabled; its last recorded run
on 2026-11-07 completed successfully. The active FastAPI apps do not require
the old versioned release folders for the tested requests. **Retirement of
old parent trees remains blocked by the configuration and old script
references above.** Keep the old media and release copies until their
rollback purpose and remaining references are reviewed. No old media or
releases were deleted during this work.

No media cutover remains for local, staging or production. After a suitable
recovery window, review retirement of the old media trees and releases as a
separate cleanup. First confirm no active service, backup job or operational
script needs them. Standardizing staging's dated override filename and release
pointer can also be a separate change; it is not required for media isolation.

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
4. Start a separate read-only production candidate using the same archive,
   production `RECIPE_UPLOADS`, and `MyRecipes`. Verify it first. Atomically
   switch `/home/pi/myrecipes-v2/current`, restart
   `recipe-fastapi-production.service`, and test the public app on port 5000.
   Nginx continues proxying to port 8012; no routing edit is needed.
5. Replace the installed asset-backup definition with the reviewed single
   production media-root source. Make a complete verified new NAS snapshot
   before enabling the timer. The old incomplete snapshots remain untouched.
6. After the new release and backups are verified, archive the three old Pi
   media directories off Pi and remove the release symlinks. Check that no
   active service or backup job references the old paths. Keep the verified
   archive for the rollback window; remove old copies only by a separately
   reviewed cleanup step.

## Rollback

Before retiring the old directories, restore the saved production
service/release. The previous code still reads its legacy
paths. Keep the new media root and its new uploads intact; a code rollback
does not restore database or media state. If old directories have already
been retired, restore their verified archive before starting the old release.
Do not restore an older database dump merely to roll back application code.

The release has no DDL. Root `AGENTS.md` continues to exclude the cooked-date
picker and its `recorded_dt` migration from Pi deployment.

For this specific release, run these commands **on the Pi** if code rollback
is necessary. Verify the recorded paths first. They preserve all uploads and
database changes. No Nginx rollback is needed.

```bash
set -e
ops=/home/pi/myrecipesite-deploy-backups/media-cutover-4c74a2b
old=$(cat "$ops/production-current.before")
test "$old" = /home/pi/myrecipes-v2/releases/0220515
test -x "$old/.venv/bin/uvicorn"
test ! -e /home/pi/myrecipes-v2/current.rollback
ln -s "$old" /home/pi/myrecipes-v2/current.rollback
mv -Tf /home/pi/myrecipes-v2/current.rollback /home/pi/myrecipes-v2/current
sudo install -m 644 "$ops/production.service.before" /etc/systemd/system/recipe-fastapi-production.service
sudo systemctl daemon-reload
sudo systemctl restart recipe-fastapi-production.service
curl --retry 10 --retry-connrefused --retry-delay 1 -fsS http://192.168.1.13:5000/health
```

The consolidated backup continues protecting the writable root after code
rollback. Keep the pre-consolidation full snapshot for the legacy media trees.
Do not restore the old incomplete asset-backup script.
