import uuid

import cv2
import numpy as np

from shared_code.storage_util import download_bytes, upload_bytes


def _var_laplacian(img_gray: np.ndarray) -> float:
    """Calculates the variance of the Laplacian to measure the blur level."""
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()


def main(ref: dict) -> dict:
    """
    Enhances the focus of an image using adaptive Unsharp Masking
    in the LAB color space.
    ref: {"container":"input", "blobName":"uploads/whatever.png"}
    output: {"container":"work", "blobName":"focus/<uuid>.png"}
    """
    # 1) Read source blob
    raw = download_bytes(ref["container"], ref["blobName"])
    npimg = np.frombuffer(raw, np.uint8)
    bgr = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # 2) Measure blur in the grayscale version to decide sharpening intensity
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur_metric = _var_laplacian(gray)

    # 3) Estimate sharpening intensity according to sharpness
    # A higher 'amount' value means more aggressive sharpening.
    if blur_metric < 20:
        amount = 1.8  # High blur -> strong sharpening
    elif blur_metric < 60:
        amount = 1.5
    elif blur_metric < 120:
        amount = 1.2
    else:
        amount = 0.8  # Sharp image -> gentle sharpening

    # 4) Convert to LAB color space to separate lightness (L) from color (A, B)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # 5) Apply Unsharp Mask ONLY to the lightness (L) channel
    # This enhances sharpness without altering colors.
    l_channel_f32 = l_channel.astype(np.float32)
    blurred_l = cv2.GaussianBlur(l_channel_f32, (0, 0), 2.5)
    sharpened_l = cv2.addWeighted(l_channel_f32, 1.0 + amount, blurred_l, -amount, 0)

    # Apply CLAHE to improve local contrast in the lightness channel
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    sharpened_l_u8 = np.clip(sharpened_l, 0, 255).astype(np.uint8)
    enhanced_l = clahe.apply(sharpened_l_u8)

    # 6) Recombine the channels and convert back to BGR
    merged_lab = cv2.merge([enhanced_l, a_channel, b_channel])
    out_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

    # 7) Save result to work/focus/<uuid>.png
    _, buffer = cv2.imencode(".png", out_bgr)
    out_name = f"focus/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buffer.tobytes(), content_type="image/png")

    return {"container": "work", "blobName": out_name}
