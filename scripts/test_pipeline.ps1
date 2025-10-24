# ====== VARIABLES ======
$RG   = "rg-vision-pipeline-tfm"
$APP  = "func-vision-pipeline-tfm"
$FILE = "./samplePicture.png"  # <-- YOUR LOCAL IMAGE

# Unique blob name under input/uploads/
$ext        = [IO.Path]::GetExtension($FILE)
$guid       = [guid]::NewGuid().ToString()
$BLOB_NAME  = "uploads/$guid$ext"

# ====== 1) GET UPLOAD SAS TOKEN (get_sas) ======
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

# ====== 2) UPLOAD LOCAL FILE TO BLOB ======
# Note: In PowerShell, 'curl' is an alias for Invoke-WebRequest. We use Invoke-WebRequest explicitly.
Invoke-WebRequest -Method Put -Uri $sasUploadUrl -InFile $FILE -Headers @{ "x-ms-blob-type" = "BlockBlob" } | Out-Null

# ====== 3) START PIPELINE (http_start) WITH BLOB REFERENCE ======
$KEY_START = az functionapp function keys list -g $RG -n $APP --function-name http_start --query "default" -o tsv
$startReq = @{
container = "input"
blobName = $BLOB_NAME
expectedData = @{
order = "M-AR-23-00219"
batch = "L 97907"
expiry = "JUN/2026"
}
requestContent = @{
  user = @{
    id = "auth0|9a0812ffb13"
    name = "Bob Operator"
    email = "operator.qa@lab.com"
    role = "qa_operator"
  }
  client = @{
    appVersion = "web-1.0.0"
    ip = "127.0.0.1"
    userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
  }  
} 

$startResp = Invoke-RestMethod -Method POST `
  -Uri "https://$APP.azurewebsites.net/api/process" `
  -Headers @{ "x-functions-key" = $KEY_START; "Content-Type" = "application/json" } `
  -Body $startReq

$statusUrl = $startResp.statusQueryGetUri
if (-not $statusUrl) { throw "statusQueryGetUri was not obtained from the starter." }

# ====== 4) POLL UNTIL COMPLETION ======
Write-Host "Processing (polling Durable Functions) ..."
do {
  Start-Sleep -Seconds 2
  $statusResp = Invoke-RestMethod -Method GET -Uri $statusUrl
  $rt = $statusResp.runtimeStatus
  Write-Host "Status: $rt"
} while ($rt -notin @("Completed","Failed","Terminated"))

if ($rt -ne "Completed") {
  $statusResp | ConvertTo-Json -Depth 20 | Out-File .\durable_status_error.json -Encoding utf8
  throw "Pipeline did not complete. Check durable_status_error.json"
}

# ====== 5) EXTRACT RESULT (final blob) ======
$outBlob = $statusResp.output.processedImageBlob.blobName
if (-not $outBlob) { throw "processedImageBlob was not found in the output." }

# Save OCR to file (optional)
$statusResp | ConvertTo-Json -Depth 20 | Out-File .\resp.json -Encoding utf8
Write-Host "Response saved to resp.json"

# ====== 6) GENERATE READ SAS TOKEN FOR FINAL RESULT ======
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
Start-Process $readUrl   # Opens the final image in the browser

# Download the result to disk (optional)
Invoke-WebRequest -Uri $readUrl -OutFile ".\final_image.png"
