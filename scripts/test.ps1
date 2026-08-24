$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')

$Python = if ($env:XIANZHI_PYTHON_EXE) {
    $env:XIANZHI_PYTHON_EXE
}
else {
    Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
}
$Tests = Join-Path $RepoRoot 'backend\tests'

Push-Location $RepoRoot
try {
    & $Python -m pytest $Tests -q
    if ($LASTEXITCODE -ne 0) {
        throw 'Backend tests failed.'
    }
}
finally {
    Pop-Location
}
