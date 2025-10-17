import uuid
import cv2
import numpy as np
from shared_code.storage_util import download_bytes, upload_bytes

def _var_laplacian(img_gray: np.ndarray) -> float:
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()

def _gaussian_psf(shape, sigma: float) -> np.ndarray:
    h, w = shape
    y, x = np.indices((h, w))
    cy, cx = h // 2, w // 2
    psf = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * sigma ** 2))
    psf /= psf.sum()
    return psf

def _wiener_deconv(img: np.ndarray, psf: np.ndarray, k: float = 0.01) -> np.ndarray:
    # img, psf en float32 [0..1]
    eps = 1e-7
    G = np.fft.fft2(img)
    H = np.fft.fft2(np.fft.ifftshift(psf), s=img.shape)
    h_conj = np.conj(H)
    denom = (np.abs(H) ** 2) + k
    f_hat = (h_conj / (denom + eps)) * G
    rec = np.fft.ifft2(f_hat).real
    rec = np.clip(rec, 0.0, 1.0).astype(np.float32)
    return rec

def main(ref: dict) -> dict:
    """
    ref: {"container":"input", "blobName":"uploads/loque_sea.png"}
    salida: {"container":"work", "blobName":"focus/<uuid>.png"}
    """
    # 1) Leer blob fuente
    raw = download_bytes(ref["container"], ref["blobName"])
    npimg = np.frombuffer(raw, np.uint8)
    bgr = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # 2) A gris + medir blur
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_metric = _var_laplacian(gray)

    # 3) Estimar sigma/k del PSF según nitidez
    if blur_metric < 20:
        sigma, k = 3.0, 0.02
    elif blur_metric < 60:
        sigma, k = 2.2, 0.015
    elif blur_metric < 120:
        sigma, k = 1.6, 0.01
    else:
        sigma, k = 1.2, 0.008

    # 4) Deconvolución Wiener en FFT
    img_f32 = gray.astype(np.float32) / 255.0
    psf = _gaussian_psf(img_f32.shape, sigma)
    rec = _wiener_deconv(img_f32, psf, k=k)

    # 5) Unsharp mask suave
    blurred = cv2.GaussianBlur(rec, (0, 0), 1.0)
    sharpen = cv2.addWeighted(rec, 1.6, blurred, -0.6, 0)

    # 6) CLAHE para contraste local
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    out_u8 = (np.clip(sharpen, 0, 1) * 255).astype(np.uint8)
    out_u8 = clahe.apply(out_u8)

    # 7) Guardar resultado en work/focus/<uuid>.png
    ok, buffer = cv2.imencode(".png", out_u8)
    out_name = f"focus/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buffer.tobytes(), content_type="image/png")

    return {"container": "work", "blobName": out_name}
