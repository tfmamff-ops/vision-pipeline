import logging
import os

import psycopg  # psycopg v3
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

POSTGRES_URL = os.environ["POSTGRES_URL"]
MISSING_VALUE = "—"
CHECK_MARK = "✓"
CROSS_MARK = "✗"


def _bool_to_mark(value) -> str:
    """Return '✓' for True, '✗' for False, '' for None."""
    if value is True:
        return CHECK_MARK
    return CROSS_MARK


def _fetch_pipeline_row(instance_id: str) -> dict | None:
    """Retrieve the pipeline log row for the provided instance id."""
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

            return cur.fetchone()


def _format_created_strings(created_at) -> tuple[str, str]:
    """Return formatted date and time strings for the created_at column."""
    if not created_at:
        return "", ""

    created_date_str = created_at.strftime("%d/%m/%Y")
    created_time_str = created_at.strftime("%H:%M:%S")

    offset = created_at.utcoffset()
    if offset is not None:
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        total_minutes = abs(total_minutes)
        hours, minutes = divmod(total_minutes, 60)
        created_time_str = f"{created_time_str} {sign}{hours:02d}:{minutes:02d}"

    return created_date_str, created_time_str


def _extract_barcode_fields(payload) -> tuple[str, str]:
    """Safely extract barcode decoded value and symbology."""
    if not isinstance(payload, dict):
        return MISSING_VALUE, MISSING_VALUE

    barcode_data = payload.get("barcodeData")
    source = barcode_data if isinstance(barcode_data, dict) else payload

    decoded_value = source.get("decodedValue") or MISSING_VALUE
    barcode_symbology = source.get("barcodeSymbology") or MISSING_VALUE

    return decoded_value, barcode_symbology


def _string_fields(
    row: dict, mapping: list[tuple[str, str]], default: str = ""
) -> dict:
    return {placeholder: row.get(key) or default for placeholder, key in mapping}


def _mark_fields(row: dict, mapping: list[tuple[str, str]]) -> dict:
    return {placeholder: _bool_to_mark(row.get(key)) for placeholder, key in mapping}


def _validation_ocr_ok(row: dict) -> str:
    flags = (
        row.get("validation_lot_ok"),
        row.get("validation_exp_date_ok"),
        row.get("validation_pack_date_ok"),
    )
    return _bool_to_mark(all(flags))


def _build_replacements(
    row: dict,
    created_date_str: str,
    created_time_str: str,
    decoded_value: str,
    barcode_symbology: str,
    user_comment: str,
    out_container: str,
    out_blob_name_pdf: str,
) -> dict:
    """Return the replacements dictionary filled with row data."""
    replacements = {
        "{{instance_id}}": row["instance_id"],
        "{{created_date}}": created_date_str,
        "{{created_time}}": created_time_str,
        "{{barcode_payload_decoded_value}}": decoded_value,
        "{{barcode_payload_barcode_symbology}}": barcode_symbology,
        "{{validation_ocr_ok}}": _validation_ocr_ok(row),
        "{{validation_barcode_ok}}": _bool_to_mark(row.get("validation_barcode_ok")),
        "{{validation_summary}}": _bool_to_mark(row.get("validation_summary")),
        "{{user_comment}}": user_comment,
        "{{report_container}}": out_container,
        "{{report_blob_name}}": out_blob_name_pdf,
    }

    replacements.update(
        _string_fields(
            row,
            [
                ("{{requested_by_user_id}}", "requested_by_user_id"),
                ("{{requested_by_user_name}}", "requested_by_user_name"),
                ("{{requested_by_user_email}}", "requested_by_user_email"),
                ("{{requested_by_user_role}}", "requested_by_user_role"),
                ("{{client_app_version}}", "client_app_version"),
                ("{{expected_prod_code}}", "expected_prod_code"),
                ("{{expected_prod_desc}}", "expected_prod_desc"),
                ("{{expected_lot}}", "expected_lot"),
                ("{{expected_exp_date}}", "expected_exp_date"),
                ("{{expected_pack_date}}", "expected_pack_date"),
                ("{{input_container}}", "input_container"),
                ("{{input_blob_name}}", "input_blob_name"),
                ("{{processed_image_container}}", "processed_image_container"),
                ("{{processed_image_blob_name}}", "processed_image_blob_name"),
                ("{{ocr_overlay_container}}", "ocr_overlay_container"),
                ("{{ocr_overlay_blob_name}}", "ocr_overlay_blob_name"),
            ],
        )
    )

    replacements.update(
        _string_fields(
            row,
            [
                ("{{barcode_overlay_container}}", "barcode_overlay_container"),
                ("{{barcode_overlay_blob_name}}", "barcode_overlay_blob_name"),
                ("{{barcode_roi_container}}", "barcode_roi_container"),
                ("{{barcode_roi_blob_name}}", "barcode_roi_blob_name"),
            ],
            default=MISSING_VALUE,
        )
    )

    replacements.update(
        _mark_fields(
            row,
            [
                ("{{validation_lot_ok}}", "validation_lot_ok"),
                ("{{validation_exp_date_ok}}", "validation_exp_date_ok"),
                ("{{validation_pack_date_ok}}", "validation_pack_date_ok"),
                (
                    "{{validation_barcode_detected_ok}}",
                    "validation_barcode_detected_ok",
                ),
                ("{{validation_barcode_legible_ok}}", "validation_barcode_legible_ok"),
            ],
        )
    )

    return replacements


def _build_image_paths(row: dict) -> dict:
    """Return the static image path definitions filled with row data."""
    resize_percentage = 40
    jpeg_quality = 70
    width_cm_large = 10.0
    width_cm_small = 7.0

    def _image_entry(container_key: str, blob_key: str, width_cm: float) -> dict:
        return {
            "container": row.get(container_key) or "",
            "blobName": row.get(blob_key) or "",
            "resizePercentage": resize_percentage,
            "jpegQuality": jpeg_quality,
            "widthCm": width_cm,
        }

    return {
        "input_image": _image_entry(
            "input_container", "input_blob_name", width_cm_large
        ),
        "processed_image": _image_entry(
            "processed_image_container",
            "processed_image_blob_name",
            width_cm_large,
        ),
        "ocr_overlay_image": _image_entry(
            "ocr_overlay_container",
            "ocr_overlay_blob_name",
            width_cm_large,
        ),
        "barcode_overlay_image": _image_entry(
            "barcode_overlay_container",
            "barcode_overlay_blob_name",
            width_cm_small,
        ),
        "barcode_roi_image": _image_entry(
            "barcode_roi_container",
            "barcode_roi_blob_name",
            width_cm_small,
        ),
    }


def get_report_replacements_and_image_paths(
    instance_id: str, user_comment: str, out_container: str, out_blob_name_pdf: str
) -> tuple[dict, dict]:
    """
    Build the dictionaries 'replacements' and 'image_paths' using the row stored
    in vision.vision_pipeline_log for the given instance_id.

    If no row is found, returns ({}, {}).
    """

    try:
        row = _fetch_pipeline_row(instance_id)
    except Exception as exc:
        logger.error(
            "error for instance_id %s: %s",
            instance_id,
            exc,
        )
        return {}, {}

    if row is None:
        logger.error(
            "instance_id %s not found in vision_pipeline_log",
            instance_id,
        )
        return {}, {}

    created_date_str, created_time_str = _format_created_strings(row.get("created_at"))
    decoded_value, barcode_symbology = _extract_barcode_fields(
        row.get("barcode_payload") or {}
    )

    replacements = _build_replacements(
        row,
        created_date_str,
        created_time_str,
        decoded_value,
        barcode_symbology,
        user_comment,
        out_container,
        out_blob_name_pdf,
    )
    image_paths = _build_image_paths(row)

    logger.info("replacements: %s", replacements)
    logger.info("image_paths: %s", image_paths)

    return replacements, image_paths
