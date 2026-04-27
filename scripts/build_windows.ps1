param(
    [string]$PythonExe = "python",
    [string]$AppName = "MonthReportConverter"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[INFO] Installing runtime/build dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r requirements.txt -r requirements-build.txt

Write-Host "[INFO] Cleaning old build artifacts..."
if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }

Write-Host "[INFO] Building Windows EXE with PyInstaller..."
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $AppName `
  --hidden-import rapidocr_onnxruntime `
  --collect-all rapidocr_onnxruntime `
  --collect-all onnxruntime `
  --add-data "docx_to_ppt_converter.py;." `
  --add-data "report_converter;report_converter" `
  gui_converter.py

Write-Host "[INFO] Build completed: .\dist\$AppName.exe"
