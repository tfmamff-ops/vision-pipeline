import os
import uuid

import cv2
import numpy as np

from shared_code.storage_util import download_bytes, upload_bytes

# clipLimit: Threshold to limit contrast. Higher values give more contrast.
# tileGridSize: Size of the region for histogram analysis.
_DEF_CLIP_LIMIT = float(os.getenv("ADJ_CLAHE_CLIP", "2.0"))
_DEF_TILE_SIZE = int(os.getenv("ADJ_CLAHE_TILE", "8"))


def _bytes_to_img(b: bytes) -> np.ndarray:
    """Decodes a byte buffer to an OpenCV image."""
    arr = np.frombuffer(b, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _img_to_png_bytes(img: np.ndarray) -> bytes:
    """Encodes an OpenCV image to a PNG byte buffer."""
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
    return buf.tobytes()


def main(ref: dict) -> dict:
    """
    Enhances image contrast and brightness using CLAHE in LAB color space.
    Input:
        { "container": "...", "blobName": "..." }
    Output:
        { "container": "work", "blobName": "contrast/<uuid>.png" }
    """
    raw = download_bytes(ref["container"], ref["blobName"])
    bgr_img = _bytes_to_img(raw)
    if bgr_img is None:
        raise RuntimeError("Could not decode image from input blob")

    # 1. Convert the image to LAB color space
    # The 'L' channel represents lightness (brightness/contrast).
    # The 'A' and 'B' channels represent color.
    lab_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab_img)

    # 2. Create and configure the CLAHE object
    # Use defined parameters for finer control.
    tile_size = (_DEF_TILE_SIZE, _DEF_TILE_SIZE)
    clahe = cv2.createCLAHE(clipLimit=_DEF_CLIP_LIMIT, tileGridSize=tile_size)

    # 3. Apply CLAHE ONLY to the lightness (L) channel
    # This improves local contrast without distorting colors.
    enhanced_l_channel = clahe.apply(l_channel)

    # 4. Merge the enhanced L channel with the original color channels
    merged_lab_img = cv2.merge([enhanced_l_channel, a_channel, b_channel])

    # 5. Convert the image back to BGR color space
    adjusted_img = cv2.cvtColor(merged_lab_img, cv2.COLOR_LAB2BGR)

    # 6. Save the result
    out_name = f"contrast/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, _img_to_png_bytes(adjusted_img), "image/png")

    return {"container": "work", "blobName": out_name}
