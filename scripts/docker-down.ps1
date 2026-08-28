$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 docker"
}

docker compose down
Write-Host "容器已停止。数据仍保留在 $(Join-Path $Root 'data')"
