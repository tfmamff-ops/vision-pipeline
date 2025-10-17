import cv2
import uuid
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

def main(ref: dict) -> dict:
    """
    Convierte una imagen a escala de grises de forma eficiente.
    """
    raw = download_bytes(ref["container"], ref["blobName"])

    # Decodificamos la imagen directamente a escala de grises usando el flag
    # cv2.IMREAD_GRAYSCALE. Esto es más rápido y usa menos memoria.
    gray = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    
    # Si la imagen no se pudo decodificar, gray será None.
    if gray is None:
        raise RuntimeError("Could not decode image from input blob")

    # El resto del proceso es el mismo
    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
        
    out_name = f"bw/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buf.tobytes(), "image/png")
    
    return {"container": "work", "blobName": out_name}