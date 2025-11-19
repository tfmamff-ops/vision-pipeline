import io
import logging
import os

import cv2
import numpy as np

from shared_code.storage_util import download_bytes

logger = logging.getLogger(__name__)


def resize_by_percentage(img: np.ndarray, percentage: int) -> np.ndarray | None:
    """Scale an image by a percentage and return the resized array."""
    if img is None:
        logger.error("input image is None")
        return None

    if percentage <= 0:
        logger.error("percentage must be > 0")
        return None

    scale = percentage / 100.0
    new_w = int(img.shape[1] * scale)
    new_h = int(img.shape[0] * scale)

    if new_w == 0 or new_h == 0:
        logger.error("resulting size is zero (%d×%d)", new_w, new_h)
        return None

    try:
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception as exc:
        logger.error("cv2.resize failed: %s", exc)
        return None

    return resized


def get_image(
    container: str,
    blob_name: str,
    resize_percentage: int,
    jpeg_quality: int,
) -> io.BytesIO | None:
    """Download, validate, resize, and encode a blob image into JPEG bytes."""
    try:
        img_bytes = download_bytes(container, blob_name)
    except Exception as exc:
        logger.error("error downloading image: %s", exc)
        return None

    if not img_bytes:
        logger.error("image blob is empty")
        return None

    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        logger.error("image is NOT a valid image (imdecode returned None)")
        return None

    logger.info(
        "image OK: shape=%s dtype=%s",
        img.shape,
        img.dtype,
    )

    resized = resize_by_percentage(img, resize_percentage)
    if resized is None:
        logger.error("resize_by_percentage returned None")
        return None

    jpeg_quality = max(1, min(100, int(jpeg_quality)))
    success, encoded_jpeg = cv2.imencode(
        ".jpg",
        resized,
        [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
    )
    if not success:
        logger.error("failed to encode resized image to JPEG")
        return None

    buf = io.BytesIO(encoded_jpeg.tobytes())
    buf.seek(0)
    return buf


def get_unavailable_image(
    resize_percentage: int = 50,
    jpeg_quality: int = 100,
) -> io.BytesIO | None:
    """Return the fallback 'unavailable' image stored in the report template container."""
    container = os.getenv("TEMPLATES_CONTAINER", "report-templates")
    blob_name = os.getenv("TEMPLATE_UNAVAILABLE_IMAGE", "unavailable_image.png")

    return get_image(container, blob_name, resize_percentage, jpeg_quality)
