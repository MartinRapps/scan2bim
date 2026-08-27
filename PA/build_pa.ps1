#Requires -Version 5.0
# PA Build-Skript für Windows PowerShell
# Alternative zu build_pa.sh (Bash) – ruft latexmk direkt auf.
# Voraussetzung: TeX Live oder MiKTeX mit latexmk im PATH

$ErrorActionPreference = "Stop"

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PA_DIR = $PSScriptRoot
Set-Location $PA_DIR

if (-not (Get-Command latexmk -ErrorAction SilentlyContinue)) {
    Write-Error "latexmk nicht gefunden. Bitte TeX Live (https://tug.org/texlive/) oder MiKTeX installieren und PATH setzen. Test: latexmk --version"
    exit 1
}

New-Item -ItemType Directory -Force -Path "build" | Out-Null

Write-Host "Baue PA/build/pa.pdf ..."

latexmk -pdf -jobname=pa -interaction=nonstopmode -halt-on-error -outdir=build main.tex

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build fehlgeschlagen (Exit $LASTEXITCODE). Siehe build/pa.log"
    exit $LASTEXITCODE
}

Write-Host "PDF erzeugt: $PA_DIR\build\pa.pdf"
