import os
import uuid
import cv2
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

# Defaults internos (overridable por env vars)
# alpha = contraste (1.0 = sin cambio), beta = brillo (0 = sin cambio)
_DEF_ALPHA = float(os.getenv("ADJ_CB_ALPHA", "1.2"))
_DEF_BETA  = float(os.getenv("ADJ_CB_BETA", "10"))

def _bytes_to_img(b: bytes):
    arr = np.frombuffer(b, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _img_to_png_bytes(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
    return buf.tobytes()

def main(ref: dict) -> dict:
    """
    Input:
      { "container": "...", "blobName": "..." }
    Output:
      { "container": "work", "blobName": "contrast/<uuid>.png" }
    """
    raw = download_bytes(ref["container"], ref["blobName"])
    img = _bytes_to_img(raw)
    if img is None:
        raise RuntimeError("Could not decode image from input blob")

    # Lee parámetros internos (sin pasarlos desde el orquestador)
    alpha = max(0.5, min(float(_DEF_ALPHA), 3.0))  # clamp razonable
    beta  = max(-50.0, min(float(_DEF_BETA), 50.0))

    adjusted = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    out_name = f"contrast/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, _img_to_png_bytes(adjusted), "image/png")

    return {"container": "work", "blobName": out_name}
