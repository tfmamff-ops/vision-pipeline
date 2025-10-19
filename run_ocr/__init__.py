import os, uuid, requests, logging
import numpy as np
import cv2
from shared_code.storage_util import download_bytes, upload_bytes

AZURE_OCR_ENDPOINT = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
AZURE_OCR_KEY = os.environ["AZURE_OCR_KEY"]

def main(ref: dict) -> dict:
    raw = download_bytes(ref["container"], ref["blobName"])

    # Final copy to output/final/<uuid>.png
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

    # Build an overlay image marking all OCR line bounding polygons (blue rectangles)
    overlay_blob = None
    try:
        # Decode original image from raw bytes
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("OpenCV imdecode returned None")

        overlay = img.copy()

        # Extract lines from OCR result
        read_result = (data or {}).get("readResult", {}) if isinstance(data, dict) else {}
        blocks = read_result.get("blocks", []) if isinstance(read_result, dict) else []

        def _bbox_from_polygon(poly):
            xs, ys = [], []
            for p in poly:
                try:
                    xs.append(int(round(p.get("x"))))
                    ys.append(int(round(p.get("y"))))
                except Exception:
                    pass
            if not xs or not ys:
                return None
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            return (x1, y1, x2, y2)

        drawn = 0
        for blk in blocks:
            for ln in blk.get("lines", []) if isinstance(blk, dict) else []:
                poly = ln.get("boundingPolygon") if isinstance(ln, dict) else None
                if isinstance(poly, list) and len(poly) >= 4:
                    bbox = _bbox_from_polygon(poly)
                    if bbox:
                        x1, y1, x2, y2 = bbox
                        # Clamp to image bounds
                        h, w = overlay.shape[:2]
                        x1 = max(0, min(x1, w - 1))
                        y1 = max(0, min(y1, h - 1))
                        x2 = max(0, min(x2, w - 1))
                        y2 = max(0, min(y2, h - 1))
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), thickness=2)  # Blue in BGR
                        drawn += 1

        # Only upload overlay if we drew anything
        if drawn > 0:
            ok, buf = cv2.imencode(".png", overlay)
            if not ok:
                raise RuntimeError("Failed to encode overlay PNG")
            overlay_bytes = buf.tobytes()
            overlay_name = f"final/overlay/{uuid.uuid4()}.png"
            upload_bytes("output", overlay_name, overlay_bytes, "image/png")
            overlay_blob = {"container": "output", "blobName": overlay_name}
            logging.info("[run_ocr] Uploaded OCR overlay with %d rectangles: %s", drawn, overlay_name)
        else:
            logging.info("[run_ocr] No OCR lines to draw; overlay not created")

    except Exception as e:
        logging.exception("[run_ocr] Failed to build/upload OCR overlay: %s", e)

    return {
        "ocrResult": data,
        "outputBlob": {"container": "output", "blobName": out_name},
        "overlayBlob": overlay_blob
    }
