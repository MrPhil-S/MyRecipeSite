[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')]
    [string] $ReleaseName,
    [ValidateSet('Before', 'After')]
    [string] $Phase = 'Before',
    [switch] $CheckOnly
)

# Run Before after staging passes; run After once the new release is live.
# This script does not deploy code. Any failure leaves the backup incomplete.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$piHost = 'pi@192.168.1.13'
$key = Join-Path $env:USERPROFILE '.ssh\id_ed25519_myrecipes_pi'
$remoteScript = '/home/pi/myrecipesite-deploy-backups/backup_pi.sh'
$localScript = Join-Path $PSScriptRoot 'backup_pi.sh'
$remoteNasHelper = '/home/pi/myrecipesite-deploy-backups/copy_release_snapshot_to_nas.py'
$localNasHelper = Join-Path $PSScriptRoot 'copy_release_snapshot_to_nas.py'
$archiveRoot = Join-Path $env:USERPROFILE 'MyRecipeSite_Local\archives\release-backups'
$expectedFiles = @('MyRecipes.sql.gz', 'MyRecipes_DEV.sql.gz', 'pi-files.tar.gz')

if (-not (Test-Path -LiteralPath $key -PathType Leaf)) { throw "SSH key missing: $key" }
if (-not (Test-Path -LiteralPath $localScript -PathType Leaf)) { throw "Backup script missing: $localScript" }
if (-not (Test-Path -LiteralPath $localNasHelper -PathType Leaf)) { throw "NAS copy helper missing: $localNasHelper" }
foreach ($program in @('ssh', 'scp')) {
    if (-not (Get-Command $program -ErrorAction SilentlyContinue)) { throw "Missing program: $program" }
}

$sshArgs = @('-i', $key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')
$remoteHashOutput = & ssh @sshArgs $piHost "tr -d '\r' < $remoteScript | sha256sum"
if ($LASTEXITCODE -ne 0 -or @($remoteHashOutput).Count -ne 1 -or
    -not ($remoteHashOutput -match '^([a-fA-F0-9]{64})  -$')) {
    throw 'Cannot verify the installed Pi backup script. No backup started.'
}
$remoteHash = $Matches[1].ToLowerInvariant()
$localText = [System.IO.File]::ReadAllText($localScript) -replace "`r`n", "`n"
$localBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($localText)
$sha256 = [Security.Cryptography.SHA256]::Create()
try { $localHash = [BitConverter]::ToString($sha256.ComputeHash($localBytes)).Replace('-', '').ToLowerInvariant() }
finally { $sha256.Dispose() }
if ($remoteHash -ne $localHash) {
    throw 'Pi backup script differs from deployment/backup_pi.sh. Review and install the intended version first.'
}
$nasHashOutput = & ssh @sshArgs $piHost "tr -d '\r' < $remoteNasHelper | sha256sum"
if ($LASTEXITCODE -ne 0 -or @($nasHashOutput).Count -ne 1 -or
    -not ($nasHashOutput -match '^([a-fA-F0-9]{64})  -$')) {
    throw 'Cannot verify the installed Pi NAS copy helper. No backup started.'
}
$installedNasHash = $Matches[1].ToLowerInvariant()
$nasText = [System.IO.File]::ReadAllText($localNasHelper) -replace "`r`n", "`n"
$nasBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($nasText)
$sha256 = [Security.Cryptography.SHA256]::Create()
try { $reviewedNasHash = [BitConverter]::ToString($sha256.ComputeHash($nasBytes)).Replace('-', '').ToLowerInvariant() }
finally { $sha256.Dispose() }
if ($installedNasHash -ne $reviewedNasHash) {
    throw 'Pi NAS copy helper differs from deployment/copy_release_snapshot_to_nas.py. Review and install the intended version first.'
}
if ($Phase -eq 'After') {
    $activeRelease = & ssh @sshArgs $piHost 'readlink -f /home/pi/myrecipes-v2/current'
    if ($LASTEXITCODE -ne 0 -or @($activeRelease).Count -ne 1 -or
        $activeRelease -ne "/home/pi/myrecipes-v2/releases/$ReleaseName") {
        throw "New release is not active on the Pi. Expected /home/pi/myrecipes-v2/releases/$ReleaseName; found $activeRelease"
    }
}
Write-Host "Verified Pi backup script for release $ReleaseName ($Phase)."
if ($CheckOnly) {
    Write-Host 'CHECK_OK: No snapshot was created.'
    return
}

Write-Host 'Creating a fresh Pi snapshot of both databases, app files, settings, and media...'
$backupOutput = @(& ssh @sshArgs $piHost "bash $remoteScript")
if ($LASTEXITCODE -ne 0) { throw 'Pi backup failed. Production deployment must stop.' }
$completeLines = @($backupOutput | Where-Object { $_ -match '^BACKUP_COMPLETE=/home/pi/myrecipesite-deploy-backups/snapshot-[0-9]{8}T[0-9]{6}Z$' })
if ($completeLines.Count -ne 1) { throw 'Pi did not report exactly one complete snapshot. Production deployment must stop.' }
$remoteDir = $completeLines[0].Substring('BACKUP_COMPLETE='.Length)
$snapshotName = $remoteDir.Substring($remoteDir.LastIndexOf('/') + 1)
$expectedNas = "//192.168.1.14/pi_myRecipes_backup/MyRecipeSite/release-backups/$ReleaseName/$snapshotName"
Write-Host 'Copying and verifying the Pi snapshot on the NAS...'
$nasOutput = @(& ssh @sshArgs $piHost "sudo -n python3 $remoteNasHelper $remoteDir $ReleaseName")
if ($LASTEXITCODE -ne 0 -or @($nasOutput | Where-Object { $_ -eq "NAS_BACKUP_READY=$expectedNas" }).Count -ne 1) {
    throw "NAS copy or verification failed. Pi snapshot remains at $remoteDir. Production deployment must stop."
}
$releaseDir = Join-Path $archiveRoot $ReleaseName
$localDir = Join-Path $releaseDir $snapshotName
if (Test-Path -LiteralPath $localDir) { throw "Refusing to overwrite existing backup: $localDir" }
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$marker = Join-Path $localDir 'INCOMPLETE'
Set-Content -LiteralPath $marker -Value 'Copy or verification did not finish.' -Encoding ASCII

$copyFiles = @('SHA256SUMS', 'MANIFEST.txt') + $expectedFiles
foreach ($name in $copyFiles) {
    & scp @sshArgs "${piHost}:$remoteDir/$name" $localDir
    if ($LASTEXITCODE -ne 0) { throw "Copy failed for $name. Production deployment must stop. Partial files remain in $localDir" }
}

$sumFile = Join-Path $localDir 'SHA256SUMS'
$lines = @(Get-Content -LiteralPath $sumFile)
if ($lines.Count -ne $expectedFiles.Count) { throw "Unexpected checksum list in $sumFile" }
$seen = @{}
foreach ($line in $lines) {
    if (-not ($line -match '^([a-fA-F0-9]{64})  (MyRecipes\.sql\.gz|MyRecipes_DEV\.sql\.gz|pi-files\.tar\.gz)$')) {
        throw "Invalid checksum entry in $sumFile"
    }
    $name = $Matches[2]
    if ($seen.ContainsKey($name)) { throw "Duplicate checksum entry for $name" }
    $seen[$name] = $true
    $actual = (Get-FileHash -LiteralPath (Join-Path $localDir $name) -Algorithm SHA256).Hash
    if ($actual -ine $Matches[1]) { throw "Checksum mismatch for $name. Production deployment must stop." }
}
foreach ($name in $expectedFiles) {
    if (-not $seen.ContainsKey($name)) { throw "Missing checksum for $name" }
}
$manifest = Get-Content -LiteralPath (Join-Path $localDir 'MANIFEST.txt') -Raw
foreach ($source in @(
    'archive_source=/home/pi/myrecipes-v2',
    'archive_source=/var/lib/myrecipesite-v2',
    'archive_source=/etc/systemd/system/recipe-fastapi-production.service'
)) {
    if (-not $manifest.Contains($source)) { throw "Release snapshot lacks $source" }
}

$record = @(
    "release_name=$ReleaseName"
    "phase=$Phase"
    "pi_snapshot=$remoteDir"
    "nas_snapshot=$expectedNas"
    "local_snapshot=$localDir"
    "verified_utc=$([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    'contents=MyRecipes, MyRecipes_DEV, Pi application and settings, production and staging media'
)
Set-Content -LiteralPath (Join-Path $localDir 'RELEASE_BACKUP.txt') -Value $record -Encoding UTF8
Remove-Item -LiteralPath $marker -Force
Write-Host "BACKUP_READY: $localDir"
