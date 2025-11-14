import json
import logging
import uuid

import azure.functions as func

from shared_code.storage_util import download_bytes, upload_bytes

from .constants import (
    CLOUDMERSIVE_API_KEY,
    MIME_JSON,
    TEMPLATE_ACCEPT,
    TEMPLATE_REJECT,
    TEMPLATES_CONTAINER,
)
from .conversion import convert_docx_to_pdf_cloudmersive
from .docx_report import generate_verification_report_bytes
from .replacements import get_report_replacements_and_image_paths


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered entrypoint that generates a PDF report from DOCX templates
    stored in Blob Storage and returns the Blob reference of the final PDF.
    """
    try:
        payload = req.get_json()

        # Log the full received JSON body for auditing/troubleshooting purposes
        logging.info("[generate_report] JSON received (raw): %s", req.get_body().decode("utf-8"))
        logging.info(
            "[generate_report] Parsed JSON (payload): %s",
            json.dumps(payload, indent=2, ensure_ascii=False),
        )

        instance_id = payload.get("instanceId")
        user_comment = payload.get("userComment")
        accepted = payload.get("accepted")
    except Exception:
        logging.exception("[generate_report] Error processing JSON - returning 400")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {"code": "invalid_json", "message": "Invalid JSON in request body"},
                }
            ),
            status_code=400,
            mimetype=MIME_JSON,
        )

    try:
        template_bytes = download_bytes(
            TEMPLATES_CONTAINER,
            TEMPLATE_ACCEPT if accepted else TEMPLATE_REJECT,
        )
    except Exception as exc:
        logging.exception("[generate_report] Failed to download template: %s", exc)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "missing_template",
                        "message": "Template could not be downloaded",
                    },
                }
            ),
            status_code=404,
            mimetype=MIME_JSON,
        )

    # Build the data used to fill the DOCX template
    replacements, image_paths = get_report_replacements_and_image_paths(instance_id, user_comment)
    docx_stream = generate_verification_report_bytes(template_bytes, replacements, image_paths)

    if docx_stream is None:
        logging.error("[generate_report] DOCX generation failed")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "docx_generation_failed",
                        "message": "Could not generate DOCX report",
                    },
                }
            ),
            status_code=500,
            mimetype=MIME_JSON,
        )

    pdf_bytes = convert_docx_to_pdf_cloudmersive(docx_stream, CLOUDMERSIVE_API_KEY)

    if not pdf_bytes:
        logging.error("[generate_report] DOCX to PDF conversion failed")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "conversion_failed",
                        "message": "Could not convert DOCX to PDF",
                    },
                }
            ),
            status_code=502,
            mimetype=MIME_JSON,
        )

    out_blob_name = f"final/report/{uuid.uuid4()}.pdf"

    try:
        upload_bytes("output", out_blob_name, pdf_bytes, content_type="application/pdf")
        logging.info("[generate_report] Uploaded report as %s/%s", "output", out_blob_name)
    except Exception as exc:
        logging.exception("[generate_report] Failed to upload report: %s", exc)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "upload_failed",
                        "message": "Could not upload PDF to Blob Storage",
                    },
                }
            ),
            status_code=500,
            mimetype=MIME_JSON,
        )

    return func.HttpResponse(
        json.dumps(
            {
                "reportBlob": {
                    "container": "output",
                    "blobName": out_blob_name,
                }
            }
        ),
        status_code=200,
        mimetype=MIME_JSON,
    )
