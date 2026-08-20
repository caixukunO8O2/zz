$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')

& (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe') -m pytest backend\tests -q
