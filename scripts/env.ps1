$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$env:VIRTUAL_ENV = Join-Path $RepoRoot '.runtime\venv'
$env:PIP_CACHE_DIR = Join-Path $RepoRoot '.cache\pip'
$env:npm_config_cache = Join-Path $RepoRoot '.cache\npm'
$env:TEMP = Join-Path $RepoRoot '.task-runtime\tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path $RepoRoot 'backend'

foreach ($directory in @($env:PIP_CACHE_DIR, $env:npm_config_cache, $env:TEMP)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}
