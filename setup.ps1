$ErrorActionPreference = "Stop"

############################################
# CREATE VENV IF NOT EXISTS
############################################

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment with Python 3.12..."
    uv venv --python 3.12
} else {
    Write-Host ".venv already exists."
}
. .\.venv\Scripts\Activate.ps1

############################################
# OPTIONAL SSL FIX
############################################

$env:SSL_CERT_FILE = "$PWD\.venv\Lib\site-packages\certifi\cacert.pem"
$env:CURL_CA_BUNDLE = $env:SSL_CERT_FILE
$env:REQUESTS_CA_BUNDLE = $env:SSL_CERT_FILE

############################################
# INSTALL REQUIRED WHEELS
############################################

if (-not (Get-Module -ListAvailable -Name osgeo)) {
    Write-Host "Installing GDAL wheel..."
    uv pip install ./wheels/gdal-3.11.4-cp312-cp312-win_amd64.whl
}

if (-not (Get-Module -ListAvailable -Name pyproj)) {
    Write-Host "Installing pyproj wheel..."
    uv pip install ./wheels/pyproj-3.7.2-cp312-cp312-win_amd64.whl
}

############################################
# SET PROJ_LIB
############################################

$env:PROJ_LIB = "$PWD\.venv\Lib\site-packages\pyproj\proj_dir\share\proj"

############################################
# INSTALL PROJECT IF NOT INSTALLED
############################################

uv pip install .

Write-Host ""
Write-Host "======================================"
Write-Host "Setup complete."
Write-Host "======================================"