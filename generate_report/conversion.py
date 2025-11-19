import io
import logging
import os

import requests

logger = logging.getLogger(__name__)


def convert_docx_to_pdf_cloudmersive(
    docx_bytes: io.BytesIO, api_key: str
) -> bytes | None:
    """Send a DOCX to Cloudmersive and return the PDF bytes."""
    payload = docx_bytes.getvalue()
    logger.info("Cloudmersive upload DOCX size: %d bytes", len(payload))

    headers = {"Apikey": api_key}
    files = {
        "inputFile": (
            "input.docx",
            payload,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    try:
        response = requests.post(
            str(os.getenv("CLOUDMERSIVE_URL")), headers=headers, files=files, timeout=60
        )
    except requests.RequestException as exc:
        logger.error("Cloudmersive network error: %s", exc)
        return None

    if response.status_code == 200:
        return response.content

    logger.error(
        "Cloudmersive error %s. Response: %s",
        response.status_code,
        response.text[:300],
    )
    return None
