import uuid
import logging
import numpy as np
import cv2
import zxingcpp

from shared_code.storage_util import download_bytes, upload_bytes

def _np_from_image_bytes(img_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # siempre BGR (3 canales)
    return img

def _extract_xy(p):
    """
    Devuelve (x, y) a partir de:
      - objetos con atributos .x / .y (p.ej. zxingcpp.Point)
      - dicts con keys 'x'/'y'
      - tuplas/listas (x, y)
    Lanza ValueError si no puede extraer coordenadas.
    """
    if hasattr(p, "x") and hasattr(p, "y"):
        return float(p.x), float(p.y)
    if isinstance(p, dict) and "x" in p and "y" in p:
        return float(p["x"]), float(p["y"])
    if isinstance(p, (tuple, list)) and len(p) == 2:
        return float(p[0]), float(p[1])
    raise ValueError("corner sin x/y")

def _bbox_from_corners(corners):
    """
    corners: iterable de 4 puntos (objeto con .x, .y, dict-like o (x,y)).
    Devuelve bbox [x, y, w, h] con ints, asegurando top-left origin.
    """
    xs, ys = [], []
    for p in corners:
        x, y = _extract_xy(p)
        xs.append(int(round(x)))
        ys.append(int(round(y)))
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    return [x1, y1, max(1, x2 - x1), max(1, y2 - y1)]

def _clamp_bbox_to_image(bbox, width, height):
    x, y, w, h = bbox
    x = max(0, min(int(x), width - 1))
    y = max(0, min(int(y), height - 1))
    w = max(1, min(int(w), width - x))
    h = max(1, min(int(h), height - y))
    return [x, y, w, h]

def _png_bytes(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
    return buf.tobytes()

def _no_barcode():
    return {
        "barcodeData": {
            "barcodeDetected": False,
            "barcodeLegible": False,
            "decodedValue": None,
            "barcodeSymbology": None,
            "barcodeBox": None,
        },
        "barcodeOverlayBlob": None,
        "barcodeRoiBlob": None,
    }

def main(ref: dict) -> dict:
    """
    Input esperado: {"container": "...", "blobName": "..."}  (salida de to_grayscale)
    Output:
      {
        "barcodeData": {
            "barcodeDetected": bool,
            "barcodeLegible": bool,
            "decodedValue": str | None,
            "barcodeSymbology": str | None,
            "barcodeBox": [x,y,w,h] | None,
        },  
        "barcodeOverlayBlob": {"container":"output","blobName":"barcode/overlay/<uuid>.png"} | None,
        "barcodeRoiBlob": {"container":"output","blobName":"barcode/roi/<uuid>.png"} | None,
      }
    """
    try:
        logging.info("[analyze_barcode] start ref=%s", ref)

        # 1) Descargar imagen bn (post to_grayscale)
        img_bytes = download_bytes(ref["container"], ref["blobName"])
        logging.info("[analyze_barcode] downloaded bytes=%d", len(img_bytes))

        img = _np_from_image_bytes(img_bytes)
        if img is None:
            logging.error("[analyze_barcode] imdecode devolvió None")
            return _no_barcode()
        logging.info("[analyze_barcode] img shape=%s dtype=%s", getattr(img, "shape", None), getattr(img, "dtype", None))

        # 2) Pasar a gray para ZXing (suele mejorar 1D) + asegurar uint8 contiguo
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if gray.dtype != np.uint8:
            gray = gray.astype(np.uint8)
        if not gray.flags['C_CONTIGUOUS']:
            gray = np.ascontiguousarray(gray)
        logging.info("[analyze_barcode] gray shape=%s contiguous=%s", getattr(gray, "shape", None), gray.flags['C_CONTIGUOUS'])

        # 3) Leer códigos con ZXing
        results = zxingcpp.read_barcodes(gray)
        logging.info("[analyze_barcode] zxing results count=%d", len(results) if results is not None else -1)
        if not results:
            # No hay detección
            logging.info("[analyze_barcode] no barcode detected")
            return _no_barcode()

        # 4) Tomar el primero (simple)
        r = results[0]
        decoded_value = r.text if getattr(r, "text", None) else None
        symbology = r.format.name if getattr(r, "format", None) else None

        # zxingcpp.Position no es iterable; extraer corners explícitos
        pos = getattr(r, "position", None)
        corners = None
        if pos is not None:
            # Los atributos esperados son top_left, top_right, bottom_right, bottom_left
            corners = [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]
        logging.info("[analyze_barcode] decoded='%s' symbology=%s corners_ok=%s", decoded_value, symbology, corners is not None)

        # Si por alguna razón no hay corners, estimar con todo el frame
        if corners:
            bbox = _bbox_from_corners(corners)
        else:
            h, w = gray.shape[:2]
            bbox = [0, 0, w, h]

        h, w = gray.shape[:2]
        x, y, bw, bh = _clamp_bbox_to_image(bbox, w, h)
        logging.info("[analyze_barcode] bbox=%s", (x, y, bw, bh))

        # 5) Crear overlay (rectángulo dibujado)
        overlay = img.copy()
        cv2.rectangle(overlay, (x, y), (x + bw, y + bh), (0, 255, 0), thickness=2)

        # 6) Crear ROI (recorte)
        roi = img[y:y + bh, x:x + bw]

        # 7) Subir ambos blobs
        uid = str(uuid.uuid4())
        overlay_blob = f"barcode/overlay/{uid}.png"
        roi_blob = f"barcode/roi/{uid}.png"

        upload_bytes("output", overlay_blob, _png_bytes(overlay), "image/png")
        upload_bytes("output", roi_blob, _png_bytes(roi), "image/png")
        logging.info("[analyze_barcode] uploaded overlay=%s roi=%s", overlay_blob, roi_blob)

        # 8) Armar salida
        out = {
            "barcodeData": {
                "barcodeDetected": True,
                "barcodeLegible": bool(decoded_value),               # legible si hay texto
                "decodedValue": decoded_value,
                "barcodeSymbology": symbology,
                "barcodeBox": [x, y, bw, bh],
            },
            "barcodeOverlayBlob": {"container": "output", "blobName": overlay_blob},
            "barcodeRoiBlob": {"container": "output", "blobName": roi_blob},
        }
        logging.info("[analyze_barcode] done ok")
        return out

    except Exception as e:
        logging.exception("[analyze_barcode] EXCEPTION: %s", e)
        return _no_barcode()
