$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$configPath = Join-Path $projectRoot 'config.ini'
$composePath = Join-Path $projectRoot 'compose.fastapi.yml'
$uploadPath = Join-Path $PSScriptRoot 'uploads'
$volumeName = 'myrecipesite_recipe_uploads'
$inDevSection = $false
$databaseUri = $null

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Missing $configPath. Copy config.ini from your existing local setup."
}
foreach ($line in [System.IO.File]::ReadLines($configPath)) {
    if ($line -match '^\s*\[([^]]+)\]\s*$') {
        $inDevSection = $Matches[1].Trim() -ieq 'dev'
        continue
    }
    if ($inDevSection -and $line -match '^\s*db_uri\s*=\s*(.*?)\s*$') {
        $databaseUri = $Matches[1]
        break
    }
}
if ([string]::IsNullOrWhiteSpace($databaseUri)) {
    throw 'config.ini must contain [dev] db_uri.'
}

function Invoke-Docker([string[]] $Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

$oldDatabaseUri = [Environment]::GetEnvironmentVariable('RECIPE_DEV_DB_URI', 'Process')
$seedContainer = 'recipe-upload-seed-' + [Guid]::NewGuid().ToString('N')
$env:RECIPE_DEV_DB_URI = $databaseUri
try {
    Set-Location $projectRoot
    Invoke-Docker @('compose', '-f', $composePath, 'build', 'fastapi')
    Invoke-Docker @('volume', 'create', $volumeName)
    Invoke-Docker @('create', '--name', $seedContainer, '--user', '0', '--mount',
        "type=volume,source=$volumeName,target=/target", 'myrecipesite-fastapi:latest', 'sleep', '300')
    Invoke-Docker @('start', $seedContainer)

    & docker exec $seedContainer sh -c 'test -f /target/.recipe_uploads_seed_v1'
    $markerStatus = $LASTEXITCODE
    if ($markerStatus -eq 1) {
        & docker exec $seedContainer sh -c 'find /target -mindepth 1 -maxdepth 1 ! -name lost+found -print -quit | grep -q .'
        $contentStatus = $LASTEXITCODE
        if ($contentStatus -eq 0) {
            throw 'The Docker uploads volume already has data but no migration marker. It was left untouched.'
        }
        if ($contentStatus -ne 1) {
            throw 'Could not inspect the Docker uploads volume safely.'
        }

        & docker cp (Join-Path $uploadPath '.') "${seedContainer}:/target"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not copy existing uploads from $uploadPath."
        }
        Invoke-Docker @('exec', $seedContainer, 'sh', '-c',
            'chown -R 10001:10001 /target && touch /target/.recipe_uploads_seed_v1 && chown 10001:10001 /target/.recipe_uploads_seed_v1')
    }
    elseif ($markerStatus -ne 0) {
        throw 'Could not inspect the Docker uploads migration marker.'
    }
    Invoke-Docker @('rm', '-f', $seedContainer)
    $seedContainer = $null
    Invoke-Docker @('compose', '-f', $composePath, 'up', '-d', '--force-recreate', 'fastapi')
}
finally {
    if ($seedContainer) {
        & docker rm -f $seedContainer *> $null
    }
    if ($null -eq $oldDatabaseUri) {
        Remove-Item Env:RECIPE_DEV_DB_URI -ErrorAction SilentlyContinue
    }
    else {
        $env:RECIPE_DEV_DB_URI = $oldDatabaseUri
    }
}
