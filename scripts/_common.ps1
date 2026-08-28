$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ArwBin = Join-Path $Root ".venv\Scripts\apple-refurb-watch.exe"

function Get-ArwBin {
    if (-not (Test-Path $ArwBin)) {
        Write-Error "尚未安装虚拟环境。请先运行: $PSScriptRoot\setup.ps1"
    }
    return $ArwBin
}
