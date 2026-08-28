$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 docker"
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
$envFile = Join-Path $Root ".env"
$example = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $example)) {
    Copy-Item $example $envFile
    Write-Host "已复制 .env.example -> .env"
}

docker compose up -d --build

$bind = "127.0.0.1"
$port = "8765"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*ARW_BIND=(.+)$') { $bind = $Matches[1].Trim() }
        if ($_ -match '^\s*ARW_PORT=(.+)$') { $port = $Matches[1].Trim() }
    }
}

Write-Host ""
Write-Host "容器已启动。"
Write-Host "  网页:  http://${bind}:${port}"
Write-Host "  日志:  docker logs -f apple-refurb-watch"
Write-Host "  停止:  $PSScriptRoot\docker-down.ps1"
Write-Host "  数据:  $(Join-Path $Root 'data')"
