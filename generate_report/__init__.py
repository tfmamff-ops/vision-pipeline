import json
import uuid
import logging
import azure.functions as func
import io
from shared_code.storage_util import download_bytes, upload_bytes
import requests
import logging


import re
from docx import Document
from docx.shared import Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph
from docx.table import Table
from PIL import Image as PilImage, ImageDraw, ImageFont
import os
import io
import requests
import sys

TEMPLATES_CONTAINER = "report-templates"
TEMPLATE_ACCEPT = "accept.docx"
TEMPLATE_REJECT = "reject.docx"
CLOUDMERSIVE_URL = "https://api.cloudmersive.com/convert/docx/to/pdf"
CLOUDMERSIVE_API_KEY = "d2e4f77e-0140-4072-9390-1ffcfbe2b1e9"
MIME_JSON = "application/json"

# ----------------------------------------------------------------------
# REPORT CONTENT PREPARATION
# ----------------------------------------------------------------------
def getReportReplacementsAndImagePaths(instanceId, userComment, accepted):
    """
    Prepares the replacements dictionary and image paths for the report generation.
    """
    replacements = {
        "{{instance_id}}": "INS-20251010-001",
        "{{created_date}}": "2025/10/10",
        "{{created_time}}": "13:00:45",
        "{{requested_by_user_id}}": "user123",
        "{{requested_by_user_name}}": "Álvaro Morales",
        "{{requested_by_user_email}}": "alvaro.m@company.com",
        "{{requested_by_user_role}}": "Operator",
        "{{client_app_version}}": "1.5.2",
        "{{expected_prod_code}}": "PROD-ABC-456",
        "{{expected_prod_desc}}": "Paracetamol 500mg - Tablets",
        "{{expected_lot}}": "LOT-2025-09-001",
        "{{validation_lot_ok}}": "✔",
        "{{expected_exp_date}}": "2027/12/31",
        "{{validation_exp_date_ok}}": "✔",
        "{{expected_pack_date}}": "2025/09/20",
        "{{validation_pack_date_ok}}": "✘",
        "{{validation_barcode_detected_ok}}": "✘",
        "{{validation_barcode_legible_ok}}": "✔",
        "{{barcode_payload_decoded_value}}": "GS1-98765432101234",
        "{{barcode_payload_barcode_symbology}}": "DataMatrix",
        "{{input_container}}": "cont-in-2025",
        "{{input_blob_name}}": "input_001.jpg",
        "{{processed_image_container}}": "cont-proc-2025",
        "{{processed_image_blob_name}}": "processed_001.jpg",
        "{{ocr_overlay_container}}": "cont-ocr-2025",
        "{{ocr_overlay_blob_name}}": "ocr_overlay_001.png",
        "{{barcode_overlay_container}}": "cont-bar-2025",
        "{{barcode_overlay_blob_name}}": "barcode_overlay_001.png",
        "{{barcode_roi_container}}": "cont-roi-2025",
        "{{barcode_roi_blob_name}}": "barcode_roi_001.png",
        "{{VALOR_AND}}": "✔",
        "{{validation_barcode_ok}}": "✔",
        "{{validation_summary}}": "✘",
        "{{user_comment}}": "Product successfully verified. Dates are visible and legible.",
        "{{report_container}}": "cont-report-2025",
        "{{report_blob_name}}": "report_001.docx",
    }

    image_paths = {
        "input_image": "input_image.png",
        "processed_image": "processed_image.png",
        "ocr_overlay_image": "ocr_overlay_image.png",
        "barcode_overlay_image": "barcode_overlay_image.png",
        "barcode_roi_image": None,
    }

    return replacements, image_paths

# ----------------------------------------------------------------------
# CONVERSION FUNCTION
# ----------------------------------------------------------------------

def convert_docx_to_pdf_cloudmersive(docx_bytes: io.BytesIO, api_key: str) -> bytes | None:
    headers = {"Apikey": api_key}

    files = {
        "inputFile": (
            "input.docx",
            docx_bytes.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    try:
        r = requests.post(CLOUDMERSIVE_URL, headers=headers, files=files, timeout=60)
        if r.status_code == 200:
            return r.content  # PDF bytes
        else:
            logging.error(f"Error {r.status_code}. Response: {r.text[:300]}")
            return None
    except requests.RequestException as e:
        logging.error(f"Network error: {e}")
        return None

# ----------------------------------------------------------------------
# DOCX REPORT GENERATION CODE
# ----------------------------------------------------------------------

def generate_verification_report_bytes(template: bytes, replacements: dict, image_paths: dict) -> io.BytesIO:
    """Generates a DOCX report from a template and returns it as an io.BytesIO object."""
    try:
        # Asegurarse de que template sea bytes o BytesIO
        if isinstance(template, bytes):
            buf = io.BytesIO(template)
        elif isinstance(template, io.BytesIO):
            buf = template
            buf.seek(0)
        else:
            logging.error("[generate_report] Unexpected template type: %s", type(template))
            return None

        document = Document(buf)
    except Exception:
        logging.exception("[generate_report] Error loading DOCX template")
        return None

    target_width_cm = 4.0
    target_width_emu = Cm(target_width_cm)

    def add_colored_text(paragraph, text: str):
        """Writes text with color for ✔ (green) and ✘ (red)."""
        for ch in text:
            run = paragraph.add_run(ch)
            if ch == "✔":
                run.font.color.rgb = RGBColor(0, 150, 0)   # green
            elif ch == "✘":
                run.font.color.rgb = RGBColor(200, 0, 0)   # red

    def replace_in_element(element):
        """Replaces text and image placeholders in a paragraph or table cell."""
        from docx.text.paragraph import Paragraph
        from docx.table import Table

        if isinstance(element, Paragraph):
            paragraphs = [element]
        elif isinstance(element, Table):
            paragraphs = []
            for row in element.rows:
                for cell in row.cells:
                    paragraphs.extend(cell.paragraphs)
        else:
            return

        for paragraph in paragraphs:
            # De momento no metemos imágenes, solo texto
            image_inserted = False  # <- IMPORTANTE: que arranque en False

            # 2. Text replacement (remaining placeholders {{...}})
            if not image_inserted:
                full_text = "".join([run.text for run in paragraph.runs])
                new_text = full_text

                for placeholder, value in replacements.items():
                    new_text = new_text.replace(placeholder, str(value))

                if new_text != full_text:
                    # Limpiar runs y escribir con colores
                    for run in reversed(paragraph.runs):
                        paragraph._element.remove(run._element)
                    add_colored_text(paragraph, new_text)

    # Iterar por todo el documento
    for paragraph in document.paragraphs:
        replace_in_element(paragraph)

    for table in document.tables:
        replace_in_element(table)

    docx_stream = io.BytesIO()
    document.save(docx_stream)
    docx_stream.seek(0)

    logging.info("[generate_report] DOCX report successfully generated in memory.")
    return docx_stream

# ----------------------------------------------------------------------
# IMAGE SUPPORT CODE
# ----------------------------------------------------------------------

def get_unavailable_image(width_px: int = 400, height_px: int = 300) -> io.BytesIO:
    """Creates a PNG image with the text 'IMAGE NOT AVAILABLE'."""
    width_px = 400
    height_px = 300
    img = PilImage.new('RGB', (width_px, height_px), color='#E0E0E0')
    draw = ImageDraw.Draw(img)
    font_size = 400
    try:
        # Ensure the script can locate 'arial.ttf'
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    text = "IMAGE NOT AVAILABLE"
    left, top, right, bottom = draw.textbbox((0, 0), text, font)
    textwidth = right - left
    textheight = bottom - top
    x = (width_px - textwidth) / 2
    y = (height_px - textheight) / 2
    draw.text((x, y), text, fill=(50, 50, 50), font=font)
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

def main(req: func.HttpRequest) -> func.HttpResponse:
	"""
	HTTP-triggered function that generates a PDF report from templates stored in Blob Storage.

	It fetches "accept.docx" and "reject.docx" from the container "report-templates". 
	Expected JSON body fields include:
	{
		"instanceId": "<durable instance id>",
		"userComment": "<optional free-text comment>",
		"accepted": "<true|false>"
	}

	The response returns the blob reference of the generated PDF:
	{
		"reportBlob": {
			"container": "output",
			"blobName": "final/report/<uuid>.pdf"
		}
	}
	"""
	
	try:
		payload = req.get_json()
        
        # Log the full received JSON
		logging.info("[generate_report] JSON received (raw): %s", req.get_body().decode('utf-8'))
		logging.info("[generate_report] Parsed JSON (payload): %s", json.dumps(payload, indent=2, ensure_ascii=False))
		instanceId = payload.get("instanceId")
		userComment = payload.get("userComment")
		accepted = payload.get("accepted")
	except Exception as e:
		logging.exception("[generate_report] Error processing JSON - returning 400")
		return func.HttpResponse(
			json.dumps({
				"ok": False,
				"error": {"code": "invalid_json", "message": "Invalid JSON in request body"}
			}),
			status_code=400,
			mimetype=MIME_JSON
		)


	try:
		template_bytes = download_bytes(TEMPLATES_CONTAINER, TEMPLATE_ACCEPT if accepted else TEMPLATE_REJECT)
	except Exception as e:
		logging.exception("[generate_report] Failed to download template: %s", e)
		return func.HttpResponse(
			json.dumps({
				"ok": False,
				"error": {"code": "missing_template", "message": "Template could not be downloaded"}
			}),
			status_code=404,
			mimetype=MIME_JSON
		)

    # Prepare replacements and image paths
	replacements, image_paths = getReportReplacementsAndImagePaths(instanceId, userComment, accepted)
	docx_stream = generate_verification_report_bytes(template_bytes, replacements, image_paths)
	
	if docx_stream is None:
		logging.error("[generate_report] DOCX generation failed")
		return func.HttpResponse(
			json.dumps({
				"ok": False,
				"error": {"code": "docx_generation_failed", "message": "Could not generate DOCX report"}
			}),
			status_code=500,
			mimetype=MIME_JSON
		)

	pdf_bytes = convert_docx_to_pdf_cloudmersive(docx_stream, CLOUDMERSIVE_API_KEY)

	if not pdf_bytes:
		logging.error("[generate_report] DOCX to PDF conversion failed")
		return func.HttpResponse(
			json.dumps({
				"ok": False,
				"error": {"code": "conversion_failed", "message": "Could not convert DOCX to PDF"}
			}),
			status_code=502,
			mimetype=MIME_JSON
		)

	# Prepare output name and upload
	out_blob_name = f"final/report/{uuid.uuid4()}.pdf"
	try:
		upload_bytes("output", out_blob_name, pdf_bytes, content_type="application/pdf")
		logging.info("[generate_report] Uploaded report as %s/%s", "output", out_blob_name)
	except Exception as e:
		logging.exception("[generate_report] Failed to upload report: %s", e)
		return func.HttpResponse(
			json.dumps({
				"ok": False,
				"error": {"code": "upload_failed", "message": "Could not upload PDF to Blob Storage"}
			}),
			status_code=500,
			mimetype=MIME_JSON
		)
	
	return func.HttpResponse(
		json.dumps({
			"reportBlob": {"container": "output", "blobName": out_blob_name}
		}),
		status_code=200,
		mimetype=MIME_JSON
	)
