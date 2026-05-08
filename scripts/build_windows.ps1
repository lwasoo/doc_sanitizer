param(
    [string]$PythonExe = "python",
    [string]$AppName = "FileToolbox"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = $env:FILE_TOOLBOX_VERSION
if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = $env:MONTH_REPORT_CONVERTER_VERSION
}
if ([string]::IsNullOrWhiteSpace($Version)) {
  try {
    $Version = (& git describe --tags --abbrev=0 2>$null).Trim()
  } catch {
    $Version = ""
  }
}
if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = "0.0.0-dev"
}
$Version = $Version -replace '^[vV]', ''
$PackageName = "v$Version-$AppName"
Write-Host "[INFO] Stamping app version: $Version"
Set-Content -Path (Join-Path $Root "gui_app\version.txt") -Value $Version -Encoding UTF8

Write-Host "[INFO] Installing runtime/build dependencies..."
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $PythonExe -m pip cache purge *> $null
$ErrorActionPreference = $PreviousErrorActionPreference
& $PythonExe -m pip install --no-cache-dir --upgrade pip
& $PythonExe -m pip install --no-cache-dir -r requirements.txt -r requirements-build.txt

Write-Host "[INFO] Cleaning old build artifacts..."
if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }

$IconPng = Join-Path $Root "assets\icon.png"
$IconIco = Join-Path $Root "assets\icon.ico"
if (Test-Path $IconIco) {
  Write-Host "[INFO] Using Windows icon: assets\icon.ico"
} elseif (Test-Path $IconPng) {
  $IconIco = Join-Path $Root "build\icon.ico"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $IconIco) | Out-Null
  Write-Host "[INFO] assets\icon.ico not found; generating Windows icon from assets\icon.png..."
  @'
from pathlib import Path
from PIL import Image
root = Path.cwd()
icon_png = root / "assets" / "icon.png"
icon_ico = root / "build" / "icon.ico"
img = Image.open(icon_png).convert("RGBA")
sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(icon_ico, sizes=sizes)
print(icon_ico)
'@ | & $PythonExe -
} else {
  Write-Error "Missing assets\icon.ico and assets\icon.png; cannot build Windows app icon."
}

Write-Host "[INFO] Building Windows EXE with PyInstaller..."
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $PackageName `
  --icon $IconIco `
  --hidden-import rapidocr_onnxruntime `
  --collect-data customtkinter `
  --collect-all rapidocr_onnxruntime `
  --collect-all onnxruntime `
  --add-data "assets;assets" `
  --add-data "docx_to_ppt_converter.py;." `
  --add-data "office_conversion.py;." `
  --add-data "sanitize_docx.py;." `
  --add-data "doc_sanitizer;doc_sanitizer" `
  --add-data "gui_app;gui_app" `
  --add-data "report_converter;report_converter" `
  gui_converter.py

Write-Host "[INFO] Build completed: .\dist\$PackageName.exe"
