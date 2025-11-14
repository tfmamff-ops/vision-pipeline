import io
import logging

import requests

from .constants import CLOUDMERSIVE_URL


def convert_docx_to_pdf_cloudmersive(docx_bytes: io.BytesIO, api_key: str) -> bytes | None:
    """Send a DOCX to Cloudmersive and return the PDF bytes."""
    payload = docx_bytes.getvalue()
    logging.info("[generate_report] Cloudmersive upload DOCX size: %d bytes", len(payload))

    headers = {"Apikey": api_key}
    files = {
        "inputFile": (
            "input.docx",
            payload,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    try:
        response = requests.post(CLOUDMERSIVE_URL, headers=headers, files=files, timeout=60)
    except requests.RequestException as exc:
        logging.error("[generate_report] Cloudmersive network error: %s", exc)
        return None

    if response.status_code == 200:
        return response.content

    logging.error(
        "[generate_report] Cloudmersive error %s. Response: %s",
        response.status_code,
        response.text[:300],
    )
    return None
