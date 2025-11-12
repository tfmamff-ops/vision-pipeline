import json
import uuid
import logging
import azure.functions as func
import io
from shared_code.storage_util import download_bytes, upload_bytes

import re
from docx import Document
from docx.shared import Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph
from docx.table import Table
from PIL import Image as PilImage, ImageDraw, ImageFont
import os
import requests
import sys


TEMPLATES_CONTAINER = "report-templates"
TEMPLATE_ACCEPT = "accept.docx"
TEMPLATE_REJECT = "reject.docx"
CLOUDMERSIVE_API_KEY = "d2e4f77e-0140-4072-9390-1ffcfbe2b1e9"

# ----------------------------------------------------------------------
# CONVERSION FUNCTION
# ----------------------------------------------------------------------

def convert_docx_to_pdf_cloudmersive(docx_bytes: io.BytesIO, api_key: str) -> bytes | None:
    import requests, sys

    url = "https://api.cloudmersive.com/convert/docx/to/pdf"
    headers = {"Apikey": api_key}

    files = {
        "inputFile": (
            "input.docx",
            docx_bytes.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    try:
        r = requests.post(url, headers=headers, files=files, timeout=60)
        if r.status_code == 200:
            return r.content  # PDF bytes
        else:
            print(f"Error {r.status_code}. Response: {r.text[:300]}")
            return None
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return None
	

def main(req: func.HttpRequest) -> func.HttpResponse:
	"""
	Generates a report by fetching templates from Blob Storage and writing a PDF-named copy to output.
	"""
	logging.info("[generate_report] Starting. Input: %s", req)

	# Ensure both templates exist by attempting to download them
	try:
		accept_bytes = download_bytes(TEMPLATES_CONTAINER, TEMPLATE_ACCEPT)
		logging.info("[generate_report] Downloaded %s/%s (%d bytes)", TEMPLATES_CONTAINER, TEMPLATE_ACCEPT, len(accept_bytes))
	except Exception as e:
		logging.exception("[generate_report] Failed to download accept template: %s", e)
		return {"ok": False, "error": f"missing_template:{TEMPLATE_ACCEPT}"}

	try:
		reject_bytes = download_bytes(TEMPLATES_CONTAINER, TEMPLATE_REJECT)
		logging.info("[generate_report] Downloaded %s/%s (%d bytes)", TEMPLATES_CONTAINER, TEMPLATE_REJECT, len(reject_bytes))
	except Exception as e:
		# Not critical for current flow, but we log it.
		logging.warning("[generate_report] Could not download reject template: %s", e)


	docx_stream = io.BytesIO(accept_bytes)
	docx_stream.seek(0)
	pdf_bytes = convert_docx_to_pdf_cloudmersive(docx_stream, CLOUDMERSIVE_API_KEY)

	# Prepare output name and upload (renamed to .pdf as requested; no actual conversion performed)
	out_blob_name = f"final/report/{uuid.uuid4()}.pdf"
	try:
		upload_bytes("output", out_blob_name, pdf_bytes, content_type="application/pdf")
		logging.info("[generate_report] Uploaded report as %s/%s", "output", out_blob_name)
	except Exception as e:
		logging.exception("[generate_report] Failed to upload report: %s", e)
		return {"ok": False, "error": "upload_failed"}
	
	return func.HttpResponse(
        json.dumps({"hola": "hola"}),
        status_code=200,
        mimetype="application/json"
    )
