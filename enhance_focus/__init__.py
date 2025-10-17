import uuid
import cv2
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

def _var_laplacian(img_gray: np.ndarray) -> float:
    """Calcula la varianza del Laplaciano para medir el nivel de desenfoque."""
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()

def main(ref: dict) -> dict:
    """
    Mejora el enfoque de una imagen utilizando Unsharp Masking adaptativo
    en el espacio de color LAB.
    ref: {"container":"input", "blobName":"uploads/loque_sea.png"}
    salida: {"container":"work", "blobName":"focus/<uuid>.png"}
    """
    # 1) Leer blob fuente
    raw = download_bytes(ref["container"], ref["blobName"])
    npimg = np.frombuffer(raw, np.uint8)
    bgr = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # 2) Medir desenfoque en la versión gris para decidir la intensidad
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_metric = _var_laplacian(gray)

    # 3) Estimar la intensidad del enfoque según la nitidez
    # Un valor más alto de 'amount' significa un enfoque más agresivo.
    if blur_metric < 20:
        amount = 1.8  # Desenfoque alto -> enfoque fuerte
    elif blur_metric < 60:
        amount = 1.5
    elif blur_metric < 120:
        amount = 1.2
    else:
        amount = 0.8  # Imagen nítida -> enfoque suave

    # 4) Convertir a espacio LAB para separar luminosidad (L) de color (A, B)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # 5) Aplicar Unsharp Mask SÓLO al canal de luminosidad (L)
    # Esto mejora la nitidez sin alterar los colores.
    l_channel_f32 = l_channel.astype(np.float32)
    blurred_l = cv2.GaussianBlur(l_channel_f32, (0, 0), 2.5)
    sharpened_l = cv2.addWeighted(l_channel_f32, 1.0 + amount, blurred_l, -amount, 0)
    
    # Aplicar CLAHE para mejorar el contraste local en el canal de luminosidad
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    sharpened_l_u8 = np.clip(sharpened_l, 0, 255).astype(np.uint8)
    enhanced_l = clahe.apply(sharpened_l_u8)

    # 6) Recombinar los canales y convertir de vuelta a BGR
    merged_lab = cv2.merge([enhanced_l, a_channel, b_channel])
    out_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

    # 7) Guardar resultado en work/focus/<uuid>.png
    _, buffer = cv2.imencode(".png", out_bgr)
    out_name = f"focus/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buffer.tobytes(), content_type="image/png")

    return {"container": "work", "blobName": out_name}