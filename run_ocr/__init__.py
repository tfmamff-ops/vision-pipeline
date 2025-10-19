import os, uuid, requests, logging
import numpy as np
import cv2
from shared_code.storage_util import download_bytes, upload_bytes

AZURE_OCR_ENDPOINT = os.environ["AZURE_OCR_ENDPOINT"].rstrip("/")
AZURE_OCR_KEY = os.environ["AZURE_OCR_KEY"]

def _bbox_from_polygon(poly):
    """Convert a bounding polygon to an axis-aligned bounding box (x1, y1, x2, y2)."""
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

def _clamp_bbox(bbox, img_width, img_height):
    """Clamp bounding box coordinates to image bounds."""
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(x1, img_width - 1))
    y1 = max(0, min(y1, img_height - 1))
    x2 = max(0, min(x2, img_width - 1))
    y2 = max(0, min(y2, img_height - 1))
    return (x1, y1, x2, y2)

def _is_valid_line(ln):
    """Check if a line dict has a valid bounding polygon."""
    if not isinstance(ln, dict):
        return False
    poly = ln.get("boundingPolygon")
    return isinstance(poly, list) and len(poly) >= 4

def _extract_ocr_lines(ocr_data):
    """Extract lines from OCR result data."""
    if not isinstance(ocr_data, dict):
        return []
    
    read_result = ocr_data.get("readResult", {})
    if not isinstance(read_result, dict):
        return []
    
    blocks = read_result.get("blocks", [])
    if not isinstance(blocks, list):
        return []
    
    lines = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        for ln in blk.get("lines", []):
            if _is_valid_line(ln):
                lines.append(ln.get("boundingPolygon"))
    
    return lines

def _draw_ocr_overlay(img_bytes, ocr_data):
    """Create an overlay image with blue rectangles around OCR lines. Returns (overlay_bytes, drawn_count) or (None, 0)."""
    try:
        # Decode image
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("OpenCV imdecode returned None")

        overlay = img.copy()
        h, w = overlay.shape[:2]

        # Extract and draw lines
        lines = _extract_ocr_lines(ocr_data)
        drawn = 0
        
        for poly in lines:
            bbox = _bbox_from_polygon(poly)
            if bbox:
                x1, y1, x2, y2 = _clamp_bbox(bbox, w, h)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), thickness=2)  # Blue in BGR
                drawn += 1

        if drawn == 0:
            return None, 0

        # Encode overlay
        ok, buf = cv2.imencode(".png", overlay)
        if not ok:
            raise RuntimeError("Failed to encode overlay PNG")
        
        return buf.tobytes(), drawn

    except Exception as e:
        logging.exception("[run_ocr] Failed to build OCR overlay: %s", e)
        return None, 0

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

    # Build overlay with OCR line rectangles
    overlay_blob = None
    overlay_bytes, drawn_count = _draw_ocr_overlay(raw, data)
    
    if overlay_bytes and drawn_count > 0:
        overlay_name = f"final/overlay/{uuid.uuid4()}.png"
        upload_bytes("output", overlay_name, overlay_bytes, "image/png")
        overlay_blob = {"container": "output", "blobName": overlay_name}
        logging.info("[run_ocr] Uploaded OCR overlay with %d rectangles: %s", drawn_count, overlay_name)
    else:
        logging.info("[run_ocr] No OCR lines to draw; overlay not created")

    return {
        "ocrResult": data,
        "outputBlob": {"container": "output", "blobName": out_name},
        "overlayBlob": overlay_blob
    }
