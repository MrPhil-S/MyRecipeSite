# Persistent media consolidation

This is the release plan for moving existing recipe images, source PDFs,
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

## Remaining cleanup

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
