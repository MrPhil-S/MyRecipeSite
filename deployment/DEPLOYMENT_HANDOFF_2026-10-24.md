# My Recipes Pi deployment: complete handoff

This records what was done on 2026-10-24 and how to repeat it on a **fresh** Pi
with the same layout. The production site is already live. Do **not** run the
one-time cutover or write-enable scripts again on the current live site: their
preflight checks expect the old Nginx route and production writes disabled.

## Current map

| Item | Location / state |
| --- | --- |
| Windows repo | `C:\projects\MyRecipeSite` |
| Production URL | `http://192.168.1.13:5000/` |
| Production service | `recipe-fastapi-production.service`, localhost port 8012, active and enabled |
| Production database | `MyRecipes` at `192.168.1.14:3307` |
| Separate Pi test service | `recipe-fastapi-preview.service`, port 8011, `MyRecipes_DEV` |
| Legacy rollback service | `uwsgi.service`, still active |
| Release source | Git commit `0220515226a40dae8a497488be9437f51c97c87c` |
| Pi release | `/home/pi/myrecipes-v2/releases/0220515` |
| Active release symlink | `/home/pi/myrecipes-v2/current` |
| V2 environment | `/home/pi/myrecipes-v2/production.env`, mode 600, outside Git |
| V2 uploads and saved aliases | `/var/lib/myrecipesite-v2/uploads` |
| Production Nginx file | `/etc/nginx/sites-available/myrecipesite_app` |
| Saved legacy Nginx file | `/home/pi/myrecipes-v2/incoming/myrecipesite_app.legacy` |

Use PowerShell on Windows for commands marked **Windows**, and a Bash shell on
the Pi for commands marked **Pi**. Open the Pi shell with:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" pi@192.168.1.13
```

Commands below contain no password or secret value. Do not paste the contents
of `config.ini`, `production.env`, or the private SSH key into tickets or logs.

## Complete script and configuration inventory

All source files below are under
`C:\projects\MyRecipeSite\deployment\`; click each name for its **complete
script/configuration**, including checks and failure handling. The Pi copies
used during deployment are under `/home/pi/myrecipes-v2/incoming/` unless
another location is shown.

| File | What it does | Where it ran |
| --- | --- | --- |
| [`backup_pi.sh`](backup_pi.sh) | Dumps both databases and archives files with integrity checks | Pi `incoming/backup_pi.sh` |
| [`build_release.py`](build_release.py) | Builds tracked-source tarball and refuses deferred `recorded_dt` feature | Windows repo |
| [`recipe-fastapi-production.service`](recipe-fastapi-production.service) | Non-Docker Pi service on localhost 8012 | Pi `/etc/systemd/system/recipe-fastapi-production.service` |
| [`myrecipesite_app.v2`](myrecipesite_app.v2) | Public Nginx proxy on port 5000 | Pi `/etc/nginx/sites-available/myrecipesite_app` |
| [`smoke_candidate.py`](smoke_candidate.py) | Read-only route/media checks, with configurable expected write state | Pi `incoming/smoke_candidate.py` |
| [`cutover_readonly.sh`](cutover_readonly.sh) | First Nginx switch with automatic routing rollback | Pi `incoming/cutover_readonly.sh` |
| [`rollback_nginx.sh`](rollback_nginx.sh) | Restores legacy uWSGI routing | Pi `incoming/rollback_nginx.sh` |
| [`set_prod_write_flag.py`](set_prod_write_flag.py) | Atomically changes only `RECIPE_PROD_WRITES` | Pi `incoming/set_prod_write_flag.py` |
| [`enable_prod_writes.sh`](enable_prod_writes.sh) | Starts writable v2 before routing switch; rolls back if checks fail | Pi `incoming/enable_prod_writes.sh` |
| [`smoke_writes.py`](smoke_writes.py) | Creates, edits, acts on and cleans one owned production test recipe | Pi `incoming/smoke_writes.py` |

## 1. Inspect before changing anything

We found that production was healthy through Nginx on port 5000 and
`uwsgi.service`. An older `myrecipessite.service` was failed but unused. The
test FastAPI service on port 8011 was a separate non-Docker installation.

```bash
systemctl is-active nginx.service uwsgi.service recipe-fastapi-preview.service
sudo cat /etc/nginx/sites-available/myrecipesite_app
sudo nginx -t
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/
df -h /home/pi /var/lib
```

On this Pi, legacy Flask files were under `/var/www/MyRecipeSite` and
`/home/pi/git/MyRecipeSite`. We did not pull/reset either tree. The existing
assets were:

| Asset | Original path | Pre-deployment count |
| --- | --- | ---: |
| Recipe images | `/var/lib/myrecipesite/recipe_images` | 443 |
| Ingredient images | `/var/www/MyRecipeSite/myrecipes/static/ingredient_images` | 843 |
| PDFs | `/var/lib/myrecipesite/custom_prints` | 48 |

The original Nginx file's SHA256 was
`0088b9521c02513e6a71e490f9ed0260584b3aa683bc7304da4a524d8236d805`.
The original `config.ini` at `/var/www/MyRecipeSite/config.ini` already held
the `[prod]` and `[dev]` database URLs. Its values were not copied to Git.

## 2. Establish key-based SSH access

The dedicated private key is
`C:\Users\Phillycheese\.ssh\id_ed25519_myrecipes_pi`; its public half has
the same name with `.pub`. It was created with the following PowerShell
command. **If the key already exists, skip generation and never overwrite it.**

```powershell
ssh-keygen -q -t ed25519 -N '""' -C 'myrecipes-pi-deploy' -f "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi"
```

The user ran this PowerShell command once, entering the Pi account password at
the interactive SSH prompt. It appends only the public key on the Pi:

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi.pub" |
  ssh pi@192.168.1.13 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
```

Verify access without a password prompt:

```powershell
ssh -o BatchMode=yes -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" pi@192.168.1.13 'printf AUTH_OK'
```

## 3. Back up before deployment

The Pi initially lacked the MariaDB command-line client; it was installed via
APT (no Docker). A standard repeat command is:

```bash
sudo apt update
sudo apt install mariadb-client
```

The backup script reads database URLs from the existing Pi `config.ini`, checks
the targets, creates temporary MariaDB client option files in `/dev/shm`, dumps
both 12-table InnoDB databases, archives app trees, media and service files,
tests each archive, and writes SHA256 checksums. It creates an `INCOMPLETE`
marker until all checks pass. The **current** script is
[`backup_pi.sh`](backup_pi.sh). It includes the v2 paths, so it is for a Pi
where v2 has already been staged. The initial pre-v2 version is available in
Git commit `0220515`.

For an **initial backup before staging v2**, extract and transfer that older
script from the repo in Windows PowerShell:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
New-Item -ItemType Directory -Path 'tmp' -Force | Out-Null
python -c "import pathlib,subprocess; pathlib.Path('tmp/backup_pi_initial.sh').write_bytes(subprocess.check_output(['git','show','0220515:deployment/backup_pi.sh']))"
scp -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" 'tmp/backup_pi_initial.sh' pi@192.168.1.13:/home/pi/backup_pi_initial.sh
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" pi@192.168.1.13 'bash /home/pi/backup_pi_initial.sh'
```

The initial script prints `BACKUP_COMPLETE=/home/pi/myrecipesite-deploy-backups/pre-v2-<UTC timestamp>`.
Copy and verify that set off Pi before staging. Do not use the current script
until its required v2 paths exist.

For the current Pi, run:

```bash
bash /home/pi/myrecipes-v2/incoming/backup_pi.sh
```

It prints a new `BACKUP_COMPLETE=/home/pi/myrecipesite-deploy-backups/snapshot-<UTC timestamp>`
path. Do not proceed if it fails or leaves `INCOMPLETE`.

Three verified sets were made during this deployment:

| Stage | Pi directory | Protected Windows copy |
| --- | --- | --- |
| Initial baseline | `/home/pi/myrecipesite-deploy-backups/pre-v2-20261024T071021Z` | `C:\projects\MyRecipeSite_Archive_2026-10-23\Pi-pre-v2-20261024T071021Z` |
| Just before routing switch | `/home/pi/myrecipesite-deploy-backups/pre-v2-20261024T073741Z` | `C:\projects\MyRecipeSite_Archive_2026-10-23\Pi-pre-v2-20261024T073741Z` |
| Expanded v2 snapshot | `/home/pi/myrecipesite-deploy-backups/snapshot-20261024T074400Z` | `C:\projects\MyRecipeSite_Archive_2026-10-23\Pi-snapshot-20261024T074400Z` |

The expanded snapshot also contains the v2 release, `production.env`, alias
catalogue and new uploads. Each protected Windows folder grants access to the
Windows user, local Administrators and SYSTEM. To copy a **new** snapshot,
replace the timestamp in this PowerShell block with the value printed by the
script:

```powershell
$name = 'snapshot-YYYYMMDDTHHMMSSZ'
$root = 'C:\projects\MyRecipeSite_Archive_2026-10-23'
$dest = Join-Path $root ("Pi-" + $name)
if (Test-Path -LiteralPath $dest) { throw 'Backup destination already exists' }
New-Item -ItemType Directory -Path $dest | Out-Null
$identity = "$env:USERDOMAIN\$env:USERNAME"
icacls.exe $dest /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'NT AUTHORITY\SYSTEM:(OI)(CI)F' 'BUILTIN\Administrators:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw 'Backup ACL setup failed' }
scp -q -o BatchMode=yes -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" -r "pi@192.168.1.13:/home/pi/myrecipesite-deploy-backups/$name/." $dest
if ($LASTEXITCODE -ne 0) { throw 'Backup transfer failed' }
$manifest = Get-Content -LiteralPath (Join-Path $dest 'SHA256SUMS')
foreach ($line in $manifest) {
    if ($line -notmatch '^([0-9a-f]{64})  (MyRecipes\.sql\.gz|MyRecipes_DEV\.sql\.gz|pi-files\.tar\.gz)$') { throw 'Bad checksum line' }
    $actual = (Get-FileHash -LiteralPath (Join-Path $dest $Matches[2]) -Algorithm SHA256).Hash
    if ($actual -ine $Matches[1]) { throw "Checksum mismatch: $($Matches[2])" }
    "VERIFIED $($Matches[2])"
}
```

The archive contains recipe data and credentials. Keep it outside the repo.
Off-Pi copying is presently **manual**, not scheduled.

## 4. Review, test and package source on Windows

We changed the FastAPI app to select `MyRecipes` only when
`RECIPE_APP_ENV=production`, with `RECIPE_PROD_WRITES` off by default. A stable
`RECIPE_CSRF_SECRET_HEX` is mandatory in production. The `/health` endpoint
reports environment/database/write state. We removed dev-only save messages.
During testing we also found and fixed an unmatched Jinja `{% endif %}` in
`recipe_app_v2/templates/_recipe_detail.html` that broke recipe pages.

The local venv was broken and a Docker bind mount failed, so we ran the 76
SQLite unit tests in a **network-disabled throwaway Docker container** by
copying the source in. Docker was used only on the Windows development PC.
The Pi deployment is non-Docker. This is the reproducible PowerShell test:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
$testConfig = 'C:\projects\MyRecipeSite\tmp\preprod-test-config.ini'
[IO.File]::WriteAllText($testConfig, "[dev]`ndb_uri=mysql+pymysql://test:test@192.168.1.14:3307/MyRecipes_DEV`n", [Text.Encoding]::ASCII)
$container = $null
try {
    $container = (docker create --network none --entrypoint python myrecipesite-fastapi -m unittest discover -s recipe_app_v2/tests -q).Trim()
    docker cp 'C:\projects\MyRecipeSite\recipe_app_v2\.' "${container}:/app/recipe_app_v2"
    docker cp $testConfig "${container}:/app/config.ini"
    docker start -a $container
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
} finally {
    if ($container) { docker rm -f $container | Out-Null }
    Remove-Item -LiteralPath $testConfig -Force -ErrorAction SilentlyContinue
}
```

Result: **76 tests passed**. The fake URL was never contacted because the
container had no network. No local or Pi database data was changed by them.

The release was built from the reviewed worktree when HEAD was `0220515`:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
python deployment\build_release.py tmp\myrecipes-v2-release-20261024.tar.gz
Get-FileHash tmp\myrecipes-v2-release-20261024.tar.gz -Algorithm SHA256
```

The exact archive is
`C:\projects\MyRecipeSite\tmp\myrecipes-v2-release-20261024.tar.gz`, SHA256
`958fec9394d923781385688c03206235a61deccc2f2db4cb6bf98253b6e98c9f`.
It contained 123 tracked app files plus a manifest, no credentials or uploads,
and no `recorded_dt` migration. **Rebuilding from today's later HEAD will
produce a different hash.** The current HEAD `1a76500` includes subsequent
deployment documentation/scripts; the running app source is still `0220515`.

The user's saved local alias catalogue was selected over the packaged seed:
`C:\projects\MyRecipeSite\recipe_app_v2\uploads\ingredient-image-aliases.json`,
SHA256 `605db526e5aba8fc32357e1f5b08e8c6c47755057dafb34c69da6a5eaacdb144`.
It differs in the `gin`/`alcohol` mapping. Deploying it does not change
existing `recipe__ingredient.name_official` mappings automatically.

## 5. Stage separately on Pi

These are **historical one-time commands for a fresh Pi with the old layout**.
First, from Windows, transfer the archive, selected aliases and service file:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
$key = "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi"
ssh -i $key pi@192.168.1.13 'umask 077; mkdir -m 700 /home/pi/myrecipes-v2; mkdir -m 700 /home/pi/myrecipes-v2/incoming; mkdir -m 700 /home/pi/myrecipes-v2/releases; mkdir -m 700 /home/pi/myrecipes-v2/releases/0220515'
scp -i $key 'C:\projects\MyRecipeSite\tmp\myrecipes-v2-release-20261024.tar.gz' 'C:\projects\MyRecipeSite\recipe_app_v2\uploads\ingredient-image-aliases.json' 'C:\projects\MyRecipeSite\deployment\recipe-fastapi-production.service' pi@192.168.1.13:/home/pi/myrecipes-v2/incoming/
```

On the Pi, verify hashes, extract, link the original media without moving it,
and create the separate writable v2 uploads area:

```bash
set -e
base=/home/pi/myrecipes-v2
release=$base/releases/0220515
printf '%s  %s\n' 958fec9394d923781385688c03206235a61deccc2f2db4cb6bf98253b6e98c9f "$base/incoming/myrecipes-v2-release-20261024.tar.gz" | sha256sum -c
printf '%s  %s\n' 605db526e5aba8fc32357e1f5b08e8c6c47755057dafb34c69da6a5eaacdb144 "$base/incoming/ingredient-image-aliases.json" | sha256sum -c
tar -xzf "$base/incoming/myrecipes-v2-release-20261024.tar.gz" -C "$release"
grep -qx 'git_head=0220515226a40dae8a497488be9437f51c97c87c' "$release/RELEASE_MANIFEST.txt"
mkdir -p "$release/myrecipes/static"
ln -s /var/lib/myrecipesite/recipe_images "$release/myrecipes/static/recipe_images"
ln -s /var/www/MyRecipeSite/myrecipes/static/ingredient_images "$release/myrecipes/static/ingredient_images"
ln -s /var/lib/myrecipesite/custom_prints "$release/myrecipes/static/custom_prints"
sudo install -d -m 750 -o pi -g pi /var/lib/myrecipesite-v2
sudo install -d -m 700 -o pi -g pi /var/lib/myrecipesite-v2/uploads
install -m 600 "$base/incoming/ingredient-image-aliases.json" /var/lib/myrecipesite-v2/uploads/ingredient-image-aliases.json
ln -s "$release" "$base/current"
python3 -m venv "$release/.venv"
"$release/.venv/bin/python" -m pip install --disable-pip-version-check --no-input --no-cache-dir -r "$release/recipe_app_v2/requirements.txt"
"$release/.venv/bin/python" -m pip check
```

Pillow built a Pi wheel during dependency installation. `pip check` then found
no broken requirements. The legacy production media locations were only read
and linked; their files were not overwritten or moved.

The production environment file was generated on Pi from the existing
`/var/www/MyRecipeSite/config.ini`. This Python code writes a new 32-byte
random CSRF signing key without printing it:

```bash
python3 - <<'PY'
import configparser
import secrets
from pathlib import Path
from urllib.parse import urlsplit

config = configparser.ConfigParser(interpolation=None)
assert config.read('/var/www/MyRecipeSite/config.ini')
url = urlsplit(config['prod']['db_uri'])
assert (url.scheme, url.hostname, url.port, url.path) == ('mysql+pymysql', '192.168.1.14', 3307, '/MyRecipes')
path = Path('/home/pi/myrecipes-v2/production.env')
assert not path.exists()
with path.open('x', encoding='ascii') as file:
    file.write('RECIPE_APP_ENV=production\n')
    file.write('RECIPE_CONFIG=/var/www/MyRecipeSite/config.ini\n')
    file.write('RECIPE_PROD_WRITES=0\n')
    file.write('RECIPE_UPLOADS=/var/lib/myrecipesite-v2/uploads\n')
    file.write('RECIPE_CSRF_SECRET_HEX=' + secrets.token_hex(32) + '\n')
path.chmod(0o600)
print('READ_ONLY_ENV_READY')
PY
```

Install/start the candidate service without changing public routing:

```bash
sudo install -m 644 /home/pi/myrecipes-v2/incoming/recipe-fastapi-production.service /etc/systemd/system/recipe-fastapi-production.service
sudo systemctl daemon-reload
sudo systemctl start recipe-fastapi-production.service
systemctl is-active recipe-fastapi-production.service
curl -fsS http://127.0.0.1:8012/health
```

The candidate initially reported `database=MyRecipes`,
`read_only=true`, `saves_enabled=false`. Smoke testing is implemented in
[`smoke_candidate.py`](smoke_candidate.py):

```powershell
scp -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" 'C:\projects\MyRecipeSite\deployment\smoke_candidate.py' pi@192.168.1.13:/home/pi/myrecipes-v2/incoming/
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" pi@192.168.1.13 'python3 /home/pi/myrecipes-v2/incoming/smoke_candidate.py'
```

It checked the homepage, plan, collections, cuisines, synonyms, image aliases,
create form, recipe 3550, recipe and ingredient images, title image and
favicon. All returned HTTP 200. The port 8011 test app was left in place.

## 6. Route public traffic with writes off

The exact Nginx replacement is
[`myrecipesite_app.v2`](myrecipesite_app.v2), SHA256
`1822fec13ed4c38e0fc5b1c4cc5df3e6a9ff9d95e2e37d1c36bb43a343cf2c8f`.
It proxies public port 5000 to localhost 8012, preserves the original Host
header including its port, and allows uploads up to 20 MB.

Transfer the Nginx file, [`cutover_readonly.sh`](cutover_readonly.sh), and
[`rollback_nginx.sh`](rollback_nginx.sh) to
`/home/pi/myrecipes-v2/incoming/`:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
$key = "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi"
scp -i $key deployment\myrecipesite_app.v2 deployment\cutover_readonly.sh deployment\rollback_nginx.sh pi@192.168.1.13:/home/pi/myrecipes-v2/incoming/
```

On Pi, save the old Nginx file before the switch:

```bash
sudo install -m 600 -o pi -g pi /etc/nginx/sites-available/myrecipesite_app /home/pi/myrecipes-v2/incoming/myrecipesite_app.legacy
sha256sum /home/pi/myrecipes-v2/incoming/myrecipesite_app.legacy
bash -n /home/pi/myrecipes-v2/incoming/cutover_readonly.sh /home/pi/myrecipes-v2/incoming/rollback_nginx.sh
```

The first cutover had explicit user approval. It used a fresh backed-up set
`pre-v2-20261024T073741Z`, copied and hash-verified on C:, before running:

```bash
bash /home/pi/myrecipes-v2/incoming/cutover_readonly.sh
```

That script enabled the new systemd unit at boot, installed the tested Nginx
file, ran `nginx -t`, reloaded Nginx, and tested the public routes. It would
restore the saved legacy Nginx file on failure. Public `/health` and homepage
passed from the Windows PC with production writes still off.

## 7. Add v2 to the ongoing backup scope

The initial script did not cover the newly created v2 uploads path. We updated
[`backup_pi.sh`](backup_pi.sh) to archive `/home/pi/myrecipes-v2`,
`/var/lib/myrecipesite-v2`, and the new systemd unit as well. Its expanded
snapshot `snapshot-20261024T074400Z` completed on Pi and was copied to the
protected C: archive. The archive membership and all copied SHA256 values
were checked before enabling any production saves.

```powershell
Set-Location 'C:\projects\MyRecipeSite'
scp -i "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi" deployment\backup_pi.sh pi@192.168.1.13:/home/pi/myrecipes-v2/incoming/backup_pi.sh
```

Then run the Pi backup and Windows copy/checksum block from step 3.

## 8. Enable saves and test one owned fixture

This was a **second explicit user checkpoint**. The current write-enable
procedure is [`enable_prod_writes.sh`](enable_prod_writes.sh), with
[`set_prod_write_flag.py`](set_prod_write_flag.py) and
[`smoke_writes.py`](smoke_writes.py). Transfer those scripts and the current
`smoke_candidate.py` to `/home/pi/myrecipes-v2/incoming/`, check Bash/Python
syntax, then run on a fresh deployment still served by legacy Nginx:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
$key = "$env:USERPROFILE\.ssh\id_ed25519_myrecipes_pi"
scp -i $key deployment\enable_prod_writes.sh deployment\set_prod_write_flag.py deployment\smoke_writes.py deployment\smoke_candidate.py deployment\rollback_nginx.sh pi@192.168.1.13:/home/pi/myrecipes-v2/incoming/
```

```bash
bash -n /home/pi/myrecipes-v2/incoming/enable_prod_writes.sh
python3 -m py_compile /home/pi/myrecipes-v2/incoming/set_prod_write_flag.py /home/pi/myrecipes-v2/incoming/smoke_writes.py
bash /home/pi/myrecipes-v2/incoming/enable_prod_writes.sh
```

An **earlier version** restarted v2 while public Nginx was already pointed at
it. One health request saw a transient 502; no fixture had been created. The
script disabled v2 writes and restored legacy routing. Pi Nginx logs showed
`Connection refused` during restart. After correction, the script restarted
v2 and waited for healthy port 8012 **while legacy still served the public
site**, then switched Nginx and ran public checks.

The successful owned fixture was recipe ID **3661**. It was created with a
recipe image and PDF, both were retrieved, then the recipe was edited,
planned, marked cooked, favorited and deleted. The script cleaned its new
upload files. `/recipes/3661?log_visit=false` returned 404 afterward. The
script automatically attempts to restore legacy routing and turn v2 writes
off if the write checks fail. It does not restore the database automatically.

## 9. Verify the live result

On Windows:

```powershell
Invoke-RestMethod 'http://192.168.1.13:5000/health'
$siteHome = Invoke-WebRequest 'http://192.168.1.13:5000/' -UseBasicParsing
$siteHome.StatusCode
```

On Pi:

```bash
systemctl is-active nginx.service uwsgi.service recipe-fastapi-preview.service recipe-fastapi-production.service
systemctl is-enabled recipe-fastapi-production.service
readlink -f /home/pi/myrecipes-v2/current
sha256sum /etc/nginx/sites-available/myrecipesite_app
curl -fsS http://192.168.1.13:5000/health
curl -fsS http://192.168.1.13:8011/health
```

The last check showed production `MyRecipes` with
`saves_enabled=true`, the test app on `MyRecipes_DEV`, all four services
active, and candidate Nginx hash `1822fec1...`. The three original media
counts remained 443/843/48, with no files left from the owned fixture in
the new upload image/PDF folders.

No Alembic migration or other DDL was run on Pi. The deferred custom cooked
date picker and `recorded_dt` migration were excluded. The local
`MyRecipes_DEV.recorded_dt` column was not removed. No Git push occurred.
Deployment commits were `0220515`, `54420fb`, `db404ce`, and `1a76500`;
this handoff was documented in a subsequent local commit. The repository
worktree was clean afterward. To inspect the local
record from Windows:

```powershell
Set-Location 'C:\projects\MyRecipeSite'
git status --short
git log -5 --oneline
git ls-files | Select-String '(?i)(secret|\.env|config\.ini|\.pem|\.key)'
```

The file-name check found no tracked credential/configuration files. It was
not a comprehensive content secret scan. The database configuration,
production signing secret, SSH private key and backups stayed outside Git.

## Rollback and day-two operation

To route the public site back to the unchanged legacy uWSGI app, from a Pi
shell run:

```bash
bash /home/pi/myrecipes-v2/incoming/rollback_nginx.sh
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.1.13:5000/
systemctl is-active uwsgi.service
```

The rollback script verifies the saved legacy file's hash, installs it at
`/etc/nginx/sites-available/myrecipesite_app`, runs `nginx -t`, reloads
Nginx and retries the public homepage. It changes **routing only**. It does
not alter production media or automatically restore old database contents.
Database restore has not been rehearsed and must be planned separately using
the verified snapshot appropriate for the incident; an automatic restore
could discard recipes created since the snapshot.

For a new backup, run the current `backup_pi.sh`, copy its new set off Pi,
and verify all SHA256 values as in step 3. This off-Pi transfer is not
automated yet. The Windows archive folders have restricted NTFS access but
are **not encrypted**. Keep the protected archives and the Pi private SSH key
outside Git. Monitor the first real production saves and set up a regular
off-Pi backup schedule.
