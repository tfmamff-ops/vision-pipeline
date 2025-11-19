import uuid

import cv2
import numpy as np

from shared_code.storage_util import download_bytes, upload_bytes


def main(ref: dict) -> dict:
    """
    Efficiently converts an image to grayscale.
    """
    raw = download_bytes(ref["container"], ref["blobName"])

    # Decode the image directly to grayscale using the flag
    # cv2.IMREAD_GRAYSCALE. This is faster and uses less memory.
    gray = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)

    # If the image could not be decoded, gray will be None.
    if gray is None:
        raise RuntimeError("Could not decode image from input blob")

    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("Failed to encode PNG")

    out_name = f"bw/{uuid.uuid4()}.png"
    upload_bytes("work", out_name, buf.tobytes(), "image/png")

    return {"container": "work", "blobName": out_name}
