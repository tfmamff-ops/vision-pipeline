import os
import logging

import psycopg  # psycopg v3
from psycopg.rows import dict_row


POSTGRES_URL = os.environ["POSTGRES_URL"]
MISSING_VALUE = "--"

def _bool_to_mark(value) -> str:
    """Return '✔' for True, '✘' for False, '' for None."""
    if value is True:
        return "✔"
    return "✘"


def get_report_replacements_and_image_paths(instance_id: str, user_comment: str, out_container: str, out_blob_name_pdf: str) -> tuple[dict, dict]:
    """
    Build the dictionaries 'replacements' and 'image_paths' using the row stored
    in vision.vision_pipeline_log for the given instance_id.

    If no row is found, returns ({}, {}).
    """

    try:
        # psycopg v3 connection
        with psycopg.connect(POSTGRES_URL) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT
                        instance_id,
                        created_at,
                        requested_by_user_id,
                        requested_by_user_name,
                        requested_by_user_email,
                        requested_by_user_role,
                        client_app_version,
                        expected_prod_code,
                        expected_prod_desc,
                        expected_lot,
                        expected_exp_date,
                        expected_pack_date,
                        validation_lot_ok,
                        validation_exp_date_ok,
                        validation_pack_date_ok,
                        validation_barcode_detected_ok,
                        validation_barcode_legible_ok,
                        validation_barcode_ok,
                        validation_summary,
                        input_container,
                        input_blob_name,
                        processed_image_container,
                        processed_image_blob_name,
                        ocr_overlay_container,
                        ocr_overlay_blob_name,
                        barcode_overlay_container,
                        barcode_overlay_blob_name,
                        barcode_roi_container,
                        barcode_roi_blob_name,
                        barcode_payload
                    FROM vision.vision_pipeline_log
                    WHERE instance_id = %s
                    """,
                    (instance_id,),
                )

                row = cur.fetchone()

        # No record found
        if row is None:
            logging.error(
                "[get_report_replacements_and_image_paths] instance_id %s not found in vision_pipeline_log",
                instance_id,
            )
            return {}, {}

        # Format timestamps
        created_at = row["created_at"]
        if created_at is not None and getattr(created_at, "tzinfo", None) is not None:
            created_at_local = created_at.astimezone()
        else:
            created_at_local = created_at

        created_date_str = (
            created_at_local.strftime("%Y/%m/%d") if created_at_local else ""
        )
        created_time_str = (
            created_at_local.strftime("%H:%M:%S") if created_at_local else ""
        )

        # Extract barcode payload fields safely (supports nested barcodeData)
        barcode_payload = row.get("barcode_payload") or {}
        decoded_value = MISSING_VALUE
        barcode_symbology = MISSING_VALUE

        if isinstance(barcode_payload, dict):
            barcode_data = barcode_payload.get("barcodeData")
            source = barcode_data if isinstance(barcode_data, dict) else barcode_payload

            decoded_value = source.get("decodedValue") or MISSING_VALUE
            barcode_symbology = source.get("barcodeSymbology") or MISSING_VALUE

        # Build replacements dictionary
        replacements = {
            "{{instance_id}}": row["instance_id"],
            "{{created_date}}": created_date_str,
            "{{created_time}}": created_time_str,
            "{{requested_by_user_id}}": row.get("requested_by_user_id") or "",
            "{{requested_by_user_name}}": row.get("requested_by_user_name") or "",
            "{{requested_by_user_email}}": row.get("requested_by_user_email") or "",
            "{{requested_by_user_role}}": row.get("requested_by_user_role") or "",
            "{{client_app_version}}": row.get("client_app_version") or "",
            "{{expected_prod_code}}": row.get("expected_prod_code") or "",
            "{{expected_prod_desc}}": row.get("expected_prod_desc") or "",
            "{{expected_lot}}": row.get("expected_lot") or "",
            "{{validation_lot_ok}}": _bool_to_mark(row.get("validation_lot_ok")),
            "{{expected_exp_date}}": row.get("expected_exp_date") or "",
            "{{validation_exp_date_ok}}": _bool_to_mark(
                row.get("validation_exp_date_ok")
            ),
            "{{expected_pack_date}}": row.get("expected_pack_date") or "",
            "{{validation_pack_date_ok}}": _bool_to_mark(
                row.get("validation_pack_date_ok")
            ),
            "{{validation_barcode_detected_ok}}": _bool_to_mark(
                row.get("validation_barcode_detected_ok")
            ),
            "{{validation_barcode_legible_ok}}": _bool_to_mark(
                row.get("validation_barcode_legible_ok")
            ),
            "{{barcode_payload_decoded_value}}": decoded_value,
            "{{barcode_payload_barcode_symbology}}": barcode_symbology,
            "{{input_container}}": row.get("input_container") or "",
            "{{input_blob_name}}": row.get("input_blob_name") or "",
            "{{processed_image_container}}": row.get("processed_image_container") or "",
            "{{processed_image_blob_name}}": row.get("processed_image_blob_name") or "",
            "{{ocr_overlay_container}}": row.get("ocr_overlay_container") or "",
            "{{ocr_overlay_blob_name}}": row.get("ocr_overlay_blob_name") or "",
            "{{barcode_overlay_container}}": row.get("barcode_overlay_container") or MISSING_VALUE,
            "{{barcode_overlay_blob_name}}": row.get("barcode_overlay_blob_name") or MISSING_VALUE,
            "{{barcode_roi_container}}": row.get("barcode_roi_container") or MISSING_VALUE,
            "{{barcode_roi_blob_name}}": row.get("barcode_roi_blob_name") or MISSING_VALUE,
            "{{validation_ocr_ok}}": _bool_to_mark(row.get("validation_lot_ok") and row.get("validation_exp_date_ok") and row.get("validation_pack_date_ok")),
            "{{validation_barcode_ok}}": _bool_to_mark(
                row.get("validation_barcode_ok")
            ),
            "{{validation_summary}}": _bool_to_mark(row.get("validation_summary")),
            # As requested: hardcoded placeholders
            "{{user_comment}}": user_comment,
            "{{report_container}}": out_container,
            "{{report_blob_name}}": out_blob_name_pdf,
        }

        # Hardcoded image parameters
        resize_percentage = 40
        jpeg_quality = 70
        width_cm_large = 10.0
        width_cm_small = 7.0

        # Build image_paths
        image_paths = {
            "input_image": {
                "container": row.get("input_container") or "",
                "blobName": row.get("input_blob_name") or "",
                "resizePercentage": resize_percentage,
                "jpegQuality": jpeg_quality,
                "widthCm": width_cm_large,
            },
            "processed_image": {
                "container": row.get("processed_image_container") or "",
                "blobName": row.get("processed_image_blob_name") or "",
                "resizePercentage": resize_percentage,
                "jpegQuality": jpeg_quality,
                "widthCm": width_cm_large,
            },
            "ocr_overlay_image": {
                "container": row.get("ocr_overlay_container") or "",
                "blobName": row.get("ocr_overlay_blob_name") or "",
                "resizePercentage": resize_percentage,
                "jpegQuality": jpeg_quality,
                "widthCm": width_cm_large,
            },
            "barcode_overlay_image": {
                "container": row.get("barcode_overlay_container") or "",
                "blobName": row.get("barcode_overlay_blob_name") or "",
                "resizePercentage": resize_percentage,
                "jpegQuality": jpeg_quality,
                "widthCm": width_cm_small,
            },
            "barcode_roi_image": {
                "container": row.get("barcode_roi_container") or "",
                "blobName": row.get("barcode_roi_blob_name") or "",
                "resizePercentage": resize_percentage,
                "jpegQuality": jpeg_quality,
                "widthCm": width_cm_small,
            },
        }

        logging.info("********************* replacements: %s", replacements)
        logging.info("********************* image_paths: %s", image_paths)

        return replacements, image_paths

    except Exception as exc:
        logging.error(
            "[get_report_replacements_and_image_paths] error for instance_id %s: %s",
            instance_id,
            exc,
        )
        return {}, {}

# def get_report_replacements_and_image_paths(instance_id, user_comment):
#     """
#     Build the replacements dictionary and image path metadata used to fill the DOCX template.
#     """
#     replacements = {
#         "{{instance_id}}": instance_id,
#         "{{created_date}}": "2025/10/10",
#         "{{created_time}}": "13:00:45",
#         "{{requested_by_user_id}}": "user123",
#         "{{requested_by_user_name}}": "Álvaro Morales",
#         "{{requested_by_user_email}}": "alvaro.m@company.com",
#         "{{requested_by_user_role}}": "Operator",
#         "{{client_app_version}}": "1.5.2",
#         "{{expected_prod_code}}": "PROD-ABC-456",
#         "{{expected_prod_desc}}": "Paracetamol 500mg - Tablets",
#         "{{expected_lot}}": "LOT-2025-09-001",
#         "{{validation_lot_ok}}": "✔",
#         "{{expected_exp_date}}": "2027/12/31",
#         "{{validation_exp_date_ok}}": "✔",
#         "{{expected_pack_date}}": "2025/09/20",
#         "{{validation_pack_date_ok}}": "✘",
#         "{{validation_barcode_detected_ok}}": "✘",
#         "{{validation_barcode_legible_ok}}": "✔",
#         "{{barcode_payload_decoded_value}}": "GS1-98765432101234",
#         "{{barcode_payload_barcode_symbology}}": "DataMatrix",
#         "{{input_container}}": "cont-in-2025",
#         "{{input_blob_name}}": "input_001.jpg",
#         "{{processed_image_container}}": "cont-proc-2025",
#         "{{processed_image_blob_name}}": "processed_001.jpg",
#         "{{ocr_overlay_container}}": "cont-ocr-2025",
#         "{{ocr_overlay_blob_name}}": "ocr_overlay_001.png",
#         "{{barcode_overlay_container}}": "cont-bar-2025",
#         "{{barcode_overlay_blob_name}}": "barcode_overlay_001.png",
#         "{{barcode_roi_container}}": "cont-roi-2025",
#         "{{barcode_roi_blob_name}}": "barcode_roi_001.png",
#         "{{VALOR_AND}}": "✔",
#         "{{validation_barcode_ok}}": "✔",
#         "{{validation_summary}}": "✘",
#         "{{user_comment}}": user_comment,
#         "{{report_container}}": "cont-report-2025",
#         "{{report_blob_name}}": "report_001.docx",
#     }

#     image_paths = {
#         "input_image": {
#             "container": "input",
#             "blobName": "uploads/0a0643fc-fd95-480f-94cc-459f21d03aeb.jpg",
#             "resizePercentage": 40,
#             "jpegQuality": 70,
#             "widthCm": 10.0,
#         },
#         "processed_image": {
#             "container": "output",
#             "blobName": "final/ocr/processed/03de1e46-ede1-4354-a890-69b550c08c33.png",
#             "resizePercentage": 40,
#             "jpegQuality": 70,
#             "widthCm": 10.0,
#         },
#         "ocr_overlay_image": {
#             "container": "output",
#             "blobName": "final/ocr/overlay/04f75521-4400-4d79-8e30-ded2952200a9.png",
#             "resizePercentage": 40,
#             "jpegQuality": 70,
#             "widthCm": 10.0,
#         },
#         "barcode_overlay_image": {
#             "container": "output",
#             "blobName": "final/barcode/overlay/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
#             "resizePercentage": 40,
#             "jpegQuality": 70,
#             "widthCm": 7.0,
#         },
#         "barcode_roi_image": {
#             "container": "output",
#             "blobName": "final/barcode/roi/02d7cd2d-5913-4778-a7ea-b0093bb75f45.png",
#             "resizePercentage": 40,
#             "jpegQuality": 70,
#             "widthCm": 7.0,
#         },
#     }

#     return replacements, image_paths
