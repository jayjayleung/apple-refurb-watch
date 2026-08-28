$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
Set-Location $Root

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Error "需要 Python 3.11+"
}

& $python.Source -m venv .venv
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e ".[dev]"

Write-Host ""
Write-Host "安装完成。"
Write-Host "  启动:  $PSScriptRoot\serve.ps1"
Write-Host "  后台:  $PSScriptRoot\serve.ps1 --detach"
Write-Host "  停止:  $PSScriptRoot\stop.ps1"
