import json
import uuid
import logging
import azure.functions as func
import io
from shared_code.storage_util import download_bytes, upload_bytes
import requests
import logging
import numpy as np
import cv2

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
TEMPLATE_UNAVAILABLE_IMAGE = "unavailable_image.png"
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
        "input_image": {
            "container": "input",
            "blobName": "uploads/0a0643fc-fd95-480f-94cc-459f21d03aeb.jpg",
        },
        "processed_image": {
            "container": "output",
            "blobName": "final/ocr/processed/03de1e46-ede1-4354-a890-69b550c08c33.png",
        },
        "ocr_overlay_image": {
            "container": "output",
            "blobName": "final/ocr/overlay/04f75521-4400-4d79-8e30-ded2952200a9.png",
        },
        "barcode_overlay_image": {
            "container": "output",
            "blobName": "final/barcode/overlay/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
        },
        "barcode_roi_image": {
            "container": "output",
            "blobName": "final/barcode/roi/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
        },
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
        buf = io.BytesIO(template)
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
        # Ensures iteration through all paragraphs if it's a table
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
            # Combine all runs’ text to find placeholders
            full_text = "".join([run.text for run in paragraph.runs])
            image_inserted = False

            # 1. Image replacement (placeholders {{..._image}})
            # Loops to handle one image replacement per paragraph/cell,
            # and removes previous runs.
            for img_placeholder, img_path in image_paths.items():
                token = f"{{{{{img_placeholder}}}}}"
                if token in full_text:
                    # Remove existing content before inserting image
                    for run in reversed(paragraph.runs):
                        paragraph._element.remove(run._element)

                    final_img_source = None
                    new_width_emu = target_width_emu
                    new_height_emu = target_width_emu * (300 / 400)  # Default ratio for placeholder

                    if img_path and os.path.exists(img_path):
                        final_img_source = img_path
                        try:
                            img = PilImage.open(final_img_source)
                            original_width, original_height = img.size
                            aspect_ratio = original_height / original_width
                            new_height_emu = new_width_emu * aspect_ratio
                        except Exception as e:
                            print(f"Warning: Unable to open real image '{img_path}'. Using 'Not Available' placeholder. Error: {e}")
                            final_img_source = get_unavailable_image()
                    else:
                        print(f"Generating 'Not Available' placeholder for '{img_placeholder}' in memory.")
                        final_img_source = get_unavailable_image()

                    if final_img_source:
                        run = paragraph.add_run()
                        run.add_picture(final_img_source, width=new_width_emu, height=new_height_emu)
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        image_inserted = True
                    break

            # 2. Text replacement (remaining placeholders {{...}})
            if not image_inserted:
                # Recalculate text after possible run removals
                full_text = "".join([run.text for run in paragraph.runs])
                new_text = full_text

                for placeholder, value in replacements.items():
                    new_text = new_text.replace(placeholder, str(value))

                if new_text != full_text:
                    # If text has changed, replace paragraph content
                    for run in reversed(paragraph.runs):
                        paragraph._element.remove(run._element)
                    add_colored_text(paragraph, new_text)

    # Iterate through all paragraphs and tables in the document
    for paragraph in document.paragraphs:
        replace_in_element(paragraph)

    for table in document.tables:
        replace_in_element(table)  # Process each table

    # Save the document to an in-memory byte buffer
    docx_stream = io.BytesIO()
    document.save(docx_stream)
    docx_stream.seek(0)

    print("\nDOCX report successfully generated in memory.")
    return docx_stream

# ----------------------------------------------------------------------
# IMAGE SUPPORT CODE
# ----------------------------------------------------------------------

def resize_by_percentage(img: np.ndarray, percentage: int) -> np.ndarray | None:
    """
    Scales an OpenCV image (ndarray) by a percentage.
    Returns a resized ndarray or None if it fails.
    """

    if img is None:
        logging.error("[resize_by_percentage] input image is None")
        return None

    if percentage <= 0:
        logging.error("[resize_by_percentage] percentage must be > 0")
        return None

    scale = percentage / 100.0
    new_w = int(img.shape[1] * scale)
    new_h = int(img.shape[0] * scale)

    if new_w == 0 or new_h == 0:
        logging.error("[resize_by_percentage] resulting size is zero (%d×%d)", new_w, new_h)
        return None

    try:
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logging.error("[resize_by_percentage] cv2.resize failed: %s", e)
        return None

    return resized

def get_image(container: str, blob_name: str, resize_percentage: int = 50) -> io.BytesIO | None:
    """
    Downloads an image, validates that it is an image,
    uses resize_by_percentage(), and returns a PNG BytesIO.
    """

    # Download image from Blob
    try:
        img_bytes = download_bytes(container, blob_name)
    except Exception as e:
        logging.error("[generate_report] error downloading image: %s", e)
        return None

    if not img_bytes:
        logging.error("[generate_report] image blob is empty")
        return None

    # Decode to ndarray
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        logging.error("[generate_report] image is NOT a valid image (imdecode returned None)")
        return None

    logging.info(
        "[generate_report] image OK: shape=%s dtype=%s",
        img.shape,
        img.dtype,
    )

    # Resize using the generic function
    resized = resize_by_percentage(img, resize_percentage)
    if resized is None:
        logging.error("[generate_report] resize_by_percentage returned None")
        return None

    # Convert to PNG in BytesIO
    success, encoded_png = cv2.imencode(".png", resized)
    if not success:
        logging.error("[generate_report] failed to encode resized image to PNG")
        return None

    buf = io.BytesIO(encoded_png.tobytes())
    buf.seek(0)
    return buf

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
