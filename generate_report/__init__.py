import json
import logging
import os
import uuid

import azure.functions as func
import bleach

from shared_code.storage_util import download_bytes, upload_bytes

from .conversion import convert_docx_to_pdf_cloudmersive
from .docx_report import generate_verification_report_bytes
from .replacements import get_report_replacements_and_image_paths
from .report_log import insert_report_log

logger = logging.getLogger(__name__)

REPORT_CONTAINER = "output"
MIME_JSON = "application/json"


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered entrypoint that generates a PDF report from DOCX templates
    stored in Blob Storage and returns the Blob reference of the final PDF.
    Accepts JSON with instanceId, userComment, and accepted flag:
    {
        "instanceId": "some-orchestration-instance-id",
        "userComment": "The data looks good.",
        "accepted": true
    }
    """
    try:
        payload = req.get_json()

        # Log the full received JSON body for auditing/troubleshooting purposes
        logger.info("JSON received (raw): %s", req.get_body().decode("utf-8"))
        logger.info(
            "Parsed JSON (payload): %s",
            json.dumps(payload, indent=2, ensure_ascii=False),
        )

        instance_id = payload.get("instanceId")
        # Sanitize the user comment using bleach
        safe_user_comment = bleach.clean(payload.get("userComment"))
        accepted = payload.get("accepted")
    except Exception:
        logger.exception("Error processing JSON - returning 400")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_json",
                        "message": "Invalid JSON in request body",
                    },
                }
            ),
            status_code=400,
            mimetype=MIME_JSON,
        )

    try:
        template_bytes = download_bytes(
            str(os.getenv("TEMPLATES_CONTAINER")),
            str(os.getenv("TEMPLATE_ACCEPT"))
            if accepted
            else str(os.getenv("TEMPLATE_REJECT")),
        )
    except Exception as exc:
        logger.exception("Failed to download template: %s", exc)
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

    # Generate unique output blob names
    out_blob_name = f"final/report/{uuid.uuid4()}"
    out_blob_name_pdf = out_blob_name + ".pdf"
    out_blob_name_docx = out_blob_name + ".docx"

    # Build the data used to fill the DOCX template
    replacements, image_paths = get_report_replacements_and_image_paths(
        instance_id, safe_user_comment, REPORT_CONTAINER, out_blob_name_pdf
    )

    if not replacements or not image_paths:
        logger.error("No replacements found for instance_id %s", instance_id)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "no_data",
                        "message": "No data found for the given instance ID",
                    },
                }
            ),
            status_code=404,
            mimetype=MIME_JSON,
        )

    # Generate the DOCX report
    docx_stream = generate_verification_report_bytes(
        template_bytes, replacements, image_paths
    )

    if docx_stream is None:
        logger.error("DOCX generation failed")
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

    # Convert DOCX to PDF using Cloudmersive API
    pdf_bytes = convert_docx_to_pdf_cloudmersive(
        docx_stream, str(os.getenv("CLOUDMERSIVE_API_KEY"))
    )

    if not pdf_bytes:
        logger.error("DOCX to PDF conversion failed")
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

    try:
        upload_bytes(
            "output", out_blob_name_pdf, pdf_bytes, content_type="application/pdf"
        )
        logger.info("Uploaded report as %s/%s", "output", out_blob_name_pdf)

        upload_bytes(
            "output",
            out_blob_name_docx,
            docx_stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        logger.info("Uploaded report as %s/%s", "output", out_blob_name_docx)

        # Insert a log entry for the generated report
        insert_report_log(
            instance_id,
            safe_user_comment,
            accepted,
            REPORT_CONTAINER,
            out_blob_name_pdf,
            out_blob_name_docx,
        )

    except Exception as exc:
        logger.exception("Failed to upload report: %s", exc)
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "upload_failed",
                        "message": "Could not upload report to Blob Storage",
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
                    "container": REPORT_CONTAINER,
                    "blobNamePDF": out_blob_name_pdf,
                    "blobNameDOCX": out_blob_name_docx,
                }
            }
        ),
        status_code=200,
        mimetype=MIME_JSON,
    )
