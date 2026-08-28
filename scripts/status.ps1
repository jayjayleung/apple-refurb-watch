$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
Set-Location $Root
& (Get-ArwBin) status @args
