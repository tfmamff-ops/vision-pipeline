import os, json
import azure.functions as func
from datetime import datetime, timedelta, timezone
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

# This Azure Function (get_sas) is designed to generate URLs with SAS (Shared Access Signature) to access blobs in Azure Storage.

ACCOUNT_URL = os.environ["BLOB_ACCOUNT_URL"]   # e.g., https://stvision109330379.blob.core.windows.net
ACCOUNT_KEY = os.environ["BLOB_ACCOUNT_KEY"]

def _account_name_from_url(url: str) -> str:
    # https://<account>.blob.core.windows.net -> <account>
    return url.split("//")[1].split(".")[0]

ACCOUNT_NAME = _account_name_from_url(ACCOUNT_URL)

def _make_upload_sas(container: str, blob_name: str, minutes: int, content_type: str | None) -> str:
    sas = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=container,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        content_type=content_type or "application/octet-stream",
    )
    return f"{ACCOUNT_URL}/{container}/{blob_name}?{sas}"

def _make_read_sas(container: str, blob_name: str, minutes: int) -> str:
    sas = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=container,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    )
    return f"{ACCOUNT_URL}/{container}/{blob_name}?{sas}"

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except Exception:
        return func.HttpResponse("Invalid JSON body", status_code=400)

    container   = data.get("container")   # "input" | "output"
    blob_name   = data.get("blobName")    # e.g., "uploads/uuid.png"
    mode        = (data.get("mode") or "upload").lower()  # "upload" | "read"
    minutes     = int(data.get("minutes") or 10)
    content_type= data.get("contentType")  # optional for upload

    # Minimal policy: only upload to input; only read from output.
    if mode == "upload" and container != "input":
        return func.HttpResponse("Uploads must target the 'input' container.", status_code=400)
    if mode == "read" and container not in ("output",):
        return func.HttpResponse("Reads are allowed only from the 'output' container.", status_code=400)
    if not blob_name:
        return func.HttpResponse("Missing 'blobName'.", status_code=400)

    if mode == "upload":
        url = _make_upload_sas(container, blob_name, minutes, content_type)
    elif mode == "read":
        url = _make_read_sas(container, blob_name, minutes)
    else:
        return func.HttpResponse("mode must be 'upload' or 'read'", status_code=400)

    return func.HttpResponse(
        json.dumps({"sasUrl": url}),
        status_code=200,
        mimetype="application/json"
    )
