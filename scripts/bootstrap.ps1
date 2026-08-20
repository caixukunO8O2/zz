$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')

$Python = 'D:\DevTools\Python312\python.exe'
if (-not (Test-Path $env:VIRTUAL_ENV)) {
    & $Python -m venv $env:VIRTUAL_ENV
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the project virtual environment.'
    }
}

$VenvPython = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
& $VenvPython -m pip install pip-tools
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install pip-tools.'
}

Push-Location (Join-Path $RepoRoot 'backend')
try {
    & $VenvPython -m piptools compile --generate-hashes --output-file requirements.txt requirements.in
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to compile runtime dependencies.'
    }

    & $VenvPython -m piptools compile --generate-hashes --allow-unsafe --output-file requirements-dev.txt requirements-dev.in
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to compile development dependencies.'
    }

    & $VenvPython -m pip install --require-hashes -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install runtime dependencies.'
    }

    & $VenvPython -m pip install --require-hashes -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install development dependencies.'
    }
}
finally {
    Pop-Location
}
