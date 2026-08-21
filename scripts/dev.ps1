$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')

if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
    Copy-Item (Join-Path $RepoRoot '.env.example') (Join-Path $RepoRoot '.env')
}

$Docker = if ($env:XIANZHI_DOCKER_EXE) {
    $env:XIANZHI_DOCKER_EXE
}
else {
    'D:\DevTools\DockerDesktop\resources\bin\docker.exe'
}
$ComposeFile = Join-Path $RepoRoot 'infra\compose.yaml'
$EnvFile = Join-Path $RepoRoot '.env'
$ComposeArgs = @('compose', '--env-file', $EnvFile, '-f', $ComposeFile)

& $Docker @ComposeArgs build api
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to build the API image.'
}

& $Docker @ComposeArgs up -d mysql redis
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to start MySQL and Redis.'
}

& $Docker @ComposeArgs stop api
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to stop the API before migration.'
}

& $Docker @ComposeArgs run --rm api alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to apply database migrations.'
}

& $Docker @ComposeArgs up -d --wait --wait-timeout 120 api
if ($LASTEXITCODE -ne 0) {
    throw 'The API did not become healthy within 120 seconds.'
}

Write-Host 'API 文档：http://localhost:8000/docs'
