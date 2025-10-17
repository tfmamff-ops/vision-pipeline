import os
import uuid
import cv2
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

# clipLimit: Umbral para limitar el contraste. Valores más altos dan más contraste.
# tileGridSize: Tamaño de la región para el análisis del histograma.
_DEF_CLIP_LIMIT = float(os.getenv("ADJ_CLAHE_CLIP", "2.0"))
_DEF_TILE_SIZE  = int(os.getenv("ADJ_CLAHE_TILE", "8"))

def _bytes_to_img(b: bytes) -> np.ndarray:
    """Decodifica un buffer de bytes a una imagen OpenCV."""
    arr = np.frombuffer(b, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _img_to_png_bytes(img: np.ndarray) -> bytes:
    """Codifica una imagen OpenCV a un buffer de bytes en formato PNG."""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
    return buf.tobytes()

def main(ref: dict) -> dict:
    """
    Mejora el contraste y brillo de una imagen usando CLAHE en el espacio LAB.
    Input:
      { "container": "...", "blobName": "..." }
    Output:
      { "container": "work", "blobName": "contrast/<uuid>.png" }
    """
    raw = download_bytes(ref["container"], ref["blobName"])
    bgr_img = _bytes_to_img(raw)
    if bgr_img is None:
        raise RuntimeError("Could not decode image from input blob")

    # 1. Convertir la imagen al espacio de color LAB
    # El canal 'L' representa la Luminosidad (brillo/contraste).
    # Los canales 'A' y 'B' representan el color.
    lab_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab_img)

    # 2. Crear y configurar el objeto CLAHE
    # Usamos los parámetros definidos para un control más fino.
    tile_size = (_DEF_TILE_SIZE, _DEF_TILE_SIZE)
    clahe = cv2.createCLAHE(clipLimit=_DEF_CLIP_LIMIT, tileGridSize=tile_size)

    # 3. Aplicar CLAHE SÓLO al canal de Luminosidad (L)
    # Esto mejora el contraste local sin distorsionar los colores.
    enhanced_l_channel = clahe.apply(l_channel)

    # 4. Unir el canal L mejorado con los canales de color originales
    merged_lab_img = cv2.merge([enhanced_l_channel, a_channel, b_channel])

    # 5. Convertir la imagen de vuelta al espacio BGR
    adjusted_img = cv2.cvtColor(merged_lab_img, cv2.COLOR_LAB2BGR)

    # 6. Guardar el resultado
    out_name = f"contrast/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, _img_to_png_bytes(adjusted_img), "image/png")

    return {"container": "work", "blobName": out_name}