# ============================================================
# build_release.ps1 — Automated build & package script
# ============================================================
# Usage: .\build_release.ps1
#
# This script:
#   1. Reads APP_VERSION from version.py
#   2. Cleans old build artifacts
#   3. Runs PyInstaller with Video_Cutter.spec
#   4. Verifies the built executable
#   5. Runs Inno Setup with the correct version
#   6. Computes SHA-256 and file size of the installer
#   7. Outputs metadata for upload
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Video Cutter — Build Release Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Read version from version.py ──
$versionFile = Join-Path $PSScriptRoot "version.py"
if (-not (Test-Path $versionFile)) {
    Write-Host "ERROR: version.py not found at $versionFile" -ForegroundColor Red
    exit 1
}

$versionContent = Get-Content $versionFile -Raw
if ($versionContent -match 'APP_VERSION\s*=\s*"([^"]+)"') {
    $appVersion = $Matches[1]
} else {
    Write-Host "ERROR: Could not parse APP_VERSION from version.py" -ForegroundColor Red
    exit 1
}

Write-Host "[1/7] Version: $appVersion" -ForegroundColor Green

# ── Step 2: Clean old build artifacts ──
Write-Host "[2/7] Cleaning build artifacts..." -ForegroundColor Yellow

$buildDir = Join-Path $PSScriptRoot "build"
$distDir = Join-Path $PSScriptRoot "dist"

if (Test-Path $buildDir) {
    Remove-Item -Path $buildDir -Recurse -Force
    Write-Host "  Removed build/" -ForegroundColor Gray
}
if (Test-Path $distDir) {
    Remove-Item -Path $distDir -Recurse -Force
    Write-Host "  Removed dist/" -ForegroundColor Gray
}

# ── Step 3: Run PyInstaller ──
Write-Host "[3/7] Building with PyInstaller..." -ForegroundColor Yellow

$specFile = Join-Path $PSScriptRoot "Video_Cutter.spec"
if (-not (Test-Path $specFile)) {
    Write-Host "ERROR: Video_Cutter.spec not found" -ForegroundColor Red
    exit 1
}

& pyinstaller $specFile --clean
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# ── Step 4: Verify built executable ──
Write-Host "[4/7] Verifying build output..." -ForegroundColor Yellow

$exePath = Join-Path $PSScriptRoot "dist\Video_Cutter\Video_Cutter.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "ERROR: Video_Cutter.exe not found at $exePath" -ForegroundColor Red
    exit 1
}

$exeSize = (Get-Item $exePath).Length
Write-Host "  Video_Cutter.exe: $([math]::Round($exeSize / 1MB, 2)) MB" -ForegroundColor Green

# ── Step 5: Run Inno Setup ──
Write-Host "[5/7] Building installer with Inno Setup..." -ForegroundColor Yellow

$isccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$issFile = Join-Path $PSScriptRoot "setup_script.iss"

if (-not (Test-Path $isccPath)) {
    Write-Host "WARNING: Inno Setup not found at $isccPath" -ForegroundColor Yellow
    Write-Host "  Skipping installer build. Install Inno Setup 6 to build installer." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Build completed (PyInstaller only)." -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $issFile)) {
    Write-Host "ERROR: setup_script.iss not found" -ForegroundColor Red
    exit 1
}

& $isccPath "/DMyAppVersion=$appVersion" $issFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Inno Setup build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# ── Step 6: Compute SHA-256 and file size ──
Write-Host "[6/7] Computing checksums..." -ForegroundColor Yellow

$installerDir = Join-Path $PSScriptRoot "installer_output"
$installerName = "Video_Cutter_Setup_v$appVersion.exe"
$installerPath = Join-Path $installerDir $installerName

if (-not (Test-Path $installerPath)) {
    Write-Host "ERROR: Installer not found at $installerPath" -ForegroundColor Red
    exit 1
}

$installerSize = (Get-Item $installerPath).Length
$sha256 = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()

Write-Host "  Installer: $installerName" -ForegroundColor Green
Write-Host "  Size:      $([math]::Round($installerSize / 1MB, 2)) MB ($installerSize bytes)" -ForegroundColor Green
Write-Host "  SHA-256:   $sha256" -ForegroundColor Green

# ── Step 7: Output metadata ──
Write-Host "[7/7] Generating release metadata..." -ForegroundColor Yellow

$metadata = @{
    app_id = "video_cutter"
    version = $appVersion
    installer_filename = $installerName
    installer_path = $installerPath
    file_size = $installerSize
    sha256 = $sha256
    built_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    package_type = "full"
}

$metadataPath = Join-Path $installerDir "release_metadata.json"
$metadata | ConvertTo-Json -Depth 3 | Out-File -FilePath $metadataPath -Encoding UTF8

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Installer: $installerPath" -ForegroundColor White
Write-Host "  Metadata:  $metadataPath" -ForegroundColor White
Write-Host "  SHA-256:   $sha256" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "  1. Upload installer to GitHub Release" -ForegroundColor Gray
Write-Host "  2. Update app_versions table on Supabase:" -ForegroundColor Gray
Write-Host "     - latest_version = '$appVersion'" -ForegroundColor Gray
Write-Host "     - download_url = <GitHub Release URL>" -ForegroundColor Gray
Write-Host "     - sha256 = '$sha256'" -ForegroundColor Gray
Write-Host "     - file_size = $installerSize" -ForegroundColor Gray
Write-Host ""
