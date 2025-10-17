# update.ps1  (guardar en vision-pipeline\script\update.ps1)

# Ir a la raíz del proyecto (sube un nivel desde /script)
Set-Location (Join-Path $PSScriptRoot '..')

# Activar entorno virtual
. .\.venv\Scripts\Activate.ps1

# Variables
$APP = "func-vision-pipeline-agm"
$RG  = "rg-vision-pipeline"

# Login solo si no hay sesión activa
try {
    az account show | Out-Null
    Write-Host "==> Sesión de Azure ya activa." -ForegroundColor Green
} catch {
    Write-Host "==> No hay sesión de Azure, iniciando login..." -ForegroundColor Yellow
    az login | Out-Null
}

# Verificar que exista la Function App
az functionapp show -g $RG -n $APP | Out-Null

# Actualizar dependencias
pip install -r .\requirements.txt
pip freeze > .\requirements.txt

# (Opcional) actualizar variables de entorno
# az functionapp config appsettings set `
#   --name $APP `
#   --resource-group $RG `
#   --settings `
#   AZURE_XX="https://x.com/" `
#   AZURE_YY="123.3"

# Publicar (build remoto; no sube local.settings.json)
func azure functionapp publish $APP --build remote --python
