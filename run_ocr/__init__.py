import os, uuid, requests
from shared_code.storage_util import download_bytes, upload_bytes

AZURE_OCR_ENDPOINT = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
AZURE_OCR_KEY = os.environ["AZURE_OCR_KEY"]

def main(ref: dict) -> dict:
    raw = download_bytes(ref["container"], ref["blobName"])

    # Copia final a output/final/<uuid>.png
    out_name = f"final/{uuid.uuid4()}.png"
    upload_bytes("output", out_name, raw, "image/png")

    # OCR
    url = f"{AZURE_OCR_ENDPOINT}/computervision/imageanalysis:analyze?api-version=2023-10-01&features=read"
    resp = requests.post(url, headers={
        "Ocp-Apim-Subscription-Key": AZURE_OCR_KEY,
        "Content-Type": "application/octet-stream"
    }, data=raw, timeout=30)

    try:
        data = resp.json()
    except Exception:
        data = {"error": {"code": str(resp.status_code), "message": resp.text}}

    return {
        "ocrResult": data,
        "outputBlob": {"container": "output", "blobName": out_name}
    }
