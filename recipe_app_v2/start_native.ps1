[CmdletBinding()]
param(
    [string] $Python = (Join-Path $env:USERPROFILE 'MyRecipeSite_Local\.venv\Scripts\python.exe'),
    [switch] $ReadOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Native Python not found at $Python. Follow recipe_app_v2/README.md to create the environment."
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$configPath = Join-Path $projectRoot 'config.ini'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Missing local configuration: $configPath"
}

# Pin this launcher to the local dev configuration, independent of inherited overrides.
$settings = @{
    RECIPE_APP_ENV = 'dev'
    RECIPE_CONFIG = $configPath
    RECIPE_UPLOADS = (Join-Path $env:USERPROFILE 'MyRecipeSite_Local\media')
    RECIPE_DEV_WRITES = $(if ($ReadOnly) { '0' } else { '1' })
    RECIPE_DEV_DB_URI = $null
    RECIPE_PROD_DB_URI = $null
    RECIPE_PROD_WRITES = $null
}
$previous = @{}
$previousLocation = Get-Location
try {
    foreach ($name in $settings.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    Set-Location -LiteralPath $projectRoot
    Write-Host "Native dev app: http://127.0.0.1:8001/ (dev saves: $env:RECIPE_DEV_WRITES). Ctrl+C stops it."
    & $Python -m uvicorn recipe_app_v2.main:app --host 127.0.0.1 --port 8001
    if ($LASTEXITCODE -ne 0) { throw "Native server exited with code $LASTEXITCODE." }
}
finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
    Set-Location -LiteralPath $previousLocation.Path
}
