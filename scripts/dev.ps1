$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')

if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
    Copy-Item (Join-Path $RepoRoot '.env.example') (Join-Path $RepoRoot '.env')
}

& 'D:\DevTools\DockerDesktop\resources\bin\docker.exe' compose -f (Join-Path $RepoRoot 'infra\compose.yaml') up --build
