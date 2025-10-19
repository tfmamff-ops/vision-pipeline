import uuid
import logging
import numpy as np
import cv2
import zxingcpp

from shared_code.storage_util import download_bytes, upload_bytes

def _np_from_image_bytes(img_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # always BGR (3 channels)
    return img

def _extract_xy(p):
    """
    Returns (x, y) from:
      - objects with attributes .x / .y (e.g., zxingcpp.Point)
      - dicts with keys 'x'/'y'
      - tuples/lists (x, y)
    Raises ValueError if coordinates cannot be extracted.
    """
    if hasattr(p, "x") and hasattr(p, "y"):
        return float(p.x), float(p.y)
    if isinstance(p, dict) and "x" in p and "y" in p:
        return float(p["x"]), float(p["y"])
    if isinstance(p, (tuple, list)) and len(p) == 2:
        return float(p[0]), float(p[1])
    raise ValueError("corner without x/y")

def _bbox_from_corners(corners):
    """
    corners: iterable of 4 points (object with .x, .y, dict-like, or (x,y)).
    Returns bbox [x, y, w, h] as ints, ensuring top-left origin.
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
    Expected input: {"container": "...", "blobName": "..."} (output from to_grayscale)
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

        # 1) Download grayscale image (post to_grayscale)
        img_bytes = download_bytes(ref["container"], ref["blobName"])
        logging.info("[analyze_barcode] downloaded bytes=%d", len(img_bytes))

        img = _np_from_image_bytes(img_bytes)
        if img is None:
            logging.error("[analyze_barcode] imdecode returned None")
            return _no_barcode()
        logging.info("[analyze_barcode] img shape=%s dtype=%s", getattr(img, "shape", None), getattr(img, "dtype", None))

        # 2) Convert to grayscale for ZXing (usually better for 1D) + ensure contiguous uint8 array
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if gray.dtype != np.uint8:
            gray = gray.astype(np.uint8)
        if not gray.flags['C_CONTIGUOUS']:
            gray = np.ascontiguousarray(gray)
        logging.info("[analyze_barcode] gray shape=%s contiguous=%s", getattr(gray, "shape", None), gray.flags['C_CONTIGUOUS'])

        # 3) Read barcodes with ZXing
        results = zxingcpp.read_barcodes(gray)
        logging.info("[analyze_barcode] zxing results count=%d", len(results) if results is not None else -1)
        if not results:
            # No detection
            logging.info("[analyze_barcode] no barcode detected")
            return _no_barcode()

        # 4) Take the first one (simple case)
        r = results[0]
        decoded_value = r.text if getattr(r, "text", None) else None
        symbology = r.format.name if getattr(r, "format", None) else None

        # zxingcpp.Position is not iterable; extract corners explicitly
        pos = getattr(r, "position", None)
        corners = None
        if pos is not None:
            # Expected attributes: top_left, top_right, bottom_right, bottom_left
            corners = [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]
        logging.info("[analyze_barcode] decoded='%s' symbology=%s corners_ok=%s", decoded_value, symbology, corners is not None)

        # If no corners available, estimate using the full frame
        if corners:
            bbox = _bbox_from_corners(corners)
        else:
            h, w = gray.shape[:2]
            bbox = [0, 0, w, h]

        h, w = gray.shape[:2]
        x, y, bw, bh = _clamp_bbox_to_image(bbox, w, h)
        logging.info("[analyze_barcode] bbox=%s", (x, y, bw, bh))

        # 5) Create overlay (rectangle drawn)
        overlay = img.copy()
        cv2.rectangle(overlay, (x, y), (x + bw, y + bh), (0, 255, 0), thickness=2)

        # 6) Create ROI (crop)
        roi = img[y:y + bh, x:x + bw]

        # 7) Upload both blobs
        uid = str(uuid.uuid4())
        overlay_blob = f"barcode/overlay/{uid}.png"
        roi_blob = f"barcode/roi/{uid}.png"

        upload_bytes("output", overlay_blob, _png_bytes(overlay), "image/png")
        upload_bytes("output", roi_blob, _png_bytes(roi), "image/png")
        logging.info("[analyze_barcode] uploaded overlay=%s roi=%s", overlay_blob, roi_blob)

        # 8) Build output
        out = {
            "barcodeData": {
                "barcodeDetected": True,
                "barcodeLegible": bool(decoded_value),               # legible if text exists
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
