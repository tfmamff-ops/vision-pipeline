# Go to the project root (one level up from /scripts)
Set-Location (Join-Path $PSScriptRoot '..')

# Activate virtual environment
. .\.venv\Scripts\Activate.ps1

# Variables
$APP = "func-vision-pipeline-tfm"
$RG  = "rg-vision-pipeline-tfm"

# Login only if there is no active session
try {
    az account show | Out-Null
    Write-Host "==> Sesión de Azure ya activa." -ForegroundColor Green
} catch {
    Write-Host "==> No hay sesión de Azure, iniciando login..." -ForegroundColor Yellow
    az login | Out-Null
}

# Verify that the Function App exists
az functionapp show -g $RG -n $APP | Out-Null

# Update dependencies (installs only what's manually defined in requirements.txt)
pip install -r .\requirements.txt

# OPTIONAL: generate a lock file for inspection/reproducibility WITHOUT modifying requirements.txt
pip freeze > .\requirements.lock

# (Optional) update environment variables
# az functionapp config appsettings set `
#   --name $APP `
#   --resource-group $RG `
#   --settings `
#   AZURE_XX="https://x.com/" `
#   AZURE_YY="123.3"

# Publish (remote build; does not upload local.settings.json)
func azure functionapp publish $APP --build remote --python
