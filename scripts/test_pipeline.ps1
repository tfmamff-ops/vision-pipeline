# ====== VARIABLES ======
$RG   = "rg-vision-pipeline"
$APP  = "func-vision-pipeline-agm"
$FILE = "C:\Alvaro\OneDrive - UNIR\TFM\brainStorming\codigosBarras\IMG_8938.png"  # <-- YOUR LOCAL IMAGE

# Unique blob name under input/uploads/
$ext        = [IO.Path]::GetExtension($FILE)
$guid       = [guid]::NewGuid().ToString()
$BLOB_NAME  = "uploads/$guid$ext"

# ====== 1) OBTENER SAS DE UPLOAD (get_sas) ======
$KEY_SAS = az functionapp function keys list -g $RG -n $APP --function-name get_sas --query "default" -o tsv
$uploadReq = @{
  container   = "input"
  blobName    = $BLOB_NAME
  mode        = "upload"
  minutes     = 15
  contentType = "image/png"
} | ConvertTo-Json

$uploadResp = Invoke-RestMethod -Method POST `
  -Uri "https://$APP.azurewebsites.net/api/sas" `
  -Headers @{ "x-functions-key" = $KEY_SAS; "Content-Type" = "application/json" } `
  -Body $uploadReq

$sasUploadUrl = $uploadResp.sasUrl
if (-not $sasUploadUrl) { throw "Upload SAS was not obtained." }

# ====== 2) SUBIR ARCHIVO LOCAL AL BLOB ======
# Note: In PowerShell, 'curl' is an alias for Invoke-WebRequest. We use Invoke-WebRequest explicitly.
Invoke-WebRequest -Method Put -Uri $sasUploadUrl -InFile $FILE -Headers @{ "x-ms-blob-type" = "BlockBlob" } | Out-Null

# ====== 3) INICIAR EL PIPELINE (http_start) CON LA REFERENCIA AL BLOB ======
$KEY_START = az functionapp function keys list -g $RG -n $APP --function-name http_start --query "default" -o tsv
$startReq = @{
  container = "input"
  blobName  = $BLOB_NAME
} | ConvertTo-Json

$startResp = Invoke-RestMethod -Method POST `
  -Uri "https://$APP.azurewebsites.net/api/process" `
  -Headers @{ "x-functions-key" = $KEY_START; "Content-Type" = "application/json" } `
  -Body $startReq

$statusUrl = $startResp.statusQueryGetUri
if (-not $statusUrl) { throw "statusQueryGetUri was not obtained from the starter." }

# ====== 4) POLL HASTA COMPLETAR ======
Write-Host "Processing (polling Durable Functions) ..."
do {
  Start-Sleep -Seconds 2
  $statusResp = Invoke-RestMethod -Method GET -Uri $statusUrl
  $rt = $statusResp.runtimeStatus
  Write-Host "Estado: $rt"
} while ($rt -notin @("Completed","Failed","Terminated"))

if ($rt -ne "Completed") {
  $statusResp | ConvertTo-Json -Depth 20 | Out-File .\durable_status_error.json -Encoding utf8
  throw "Pipeline did not complete. Check durable_status_error.json"
}

# ====== 5) EXTRAER RESULTADO (blob final + OCR) ======
$outBlob = $statusResp.output.processedImageBlob.blobName
if (-not $outBlob) { throw "processedImageBlob was not found in the output." }

# Save OCR to file (optional)
$statusResp.output.ocrResult | ConvertTo-Json -Depth 20 | Out-File .\ocrResult.json -Encoding utf8
Write-Host "OCR saved to ocrResult.json"

# ====== 6) GENERAR SAS DE LECTURA PARA VER EL RESULTADO FINAL ======
$readReq = @{
  container = "output"
  blobName  = $outBlob
  mode      = "read"
  minutes   = 15
} | ConvertTo-Json

$readResp = Invoke-RestMethod -Method POST `
  -Uri "https://$APP.azurewebsites.net/api/sas" `
  -Headers @{ "x-functions-key" = $KEY_SAS; "Content-Type" = "application/json" } `
  -Body $readReq

$readUrl = $readResp.sasUrl
if (-not $readUrl) { throw "Read SAS for the result was not obtained." }

Write-Host "Final result (open in browser): $readUrl"
Start-Process $readUrl   # opens the final image in the browser

# (Optional) Download the result to disk:
# Invoke-WebRequest -Uri $readUrl -OutFile ".\resultado_final.png"
