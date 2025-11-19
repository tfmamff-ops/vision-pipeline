import os

import psycopg  # psycopg v3
from psycopg.types.json import Jsonb

POSTGRES_URL = os.environ[
    "POSTGRES_URL"
]  # e.g., "postgresql://user:pass@host:5432/dbname"


def main(ref: dict) -> dict:
    """
    Idempotently persist a pipeline run.
    - Map key fields to relational columns.
    - Store full payloads in JSONB.
    """
    instance_id = ref.get("instanceId")
    created_time = ref.get("createdTime")
    input_obj = ref.get("input", {})
    out = ref.get("output", {})
    ocr = out.get("ocrResult")
    barcode = out.get("barcode", {})
    val = out.get("validation", {})

    # Expected data from the request (already an object in this flow)
    expected = input_obj.get("expectedData", {})

    # Request context (who/what triggered the run)
    req_ctx = input_obj.get("requestContext", {}) or {}
    req_user = req_ctx.get("user", {}) or {}
    req_client = req_ctx.get("client", {}) or {}

    # Blob extras
    proc_blob = out.get("processedImageBlob") or {}
    ocr_overlay = out.get("ocrOverlayBlob") or {}
    bc_overlay = barcode.get("barcodeOverlayBlob") or {}
    bc_roi = barcode.get("barcodeRoiBlob") or {}

    # UPSERT
    sql = """
    INSERT INTO vision.vision_pipeline_log (
      instance_id, created_at, finished_at,
      requested_by_user_id, requested_by_user_name, requested_by_user_role, requested_by_user_email,
      client_app_version, client_ip, client_user_agent, request_context_payload,
      input_container, input_blob_name,
      expected_prod_code, expected_prod_desc,
      expected_lot, expected_exp_date, expected_pack_date,
      validation_lot_ok, validation_exp_date_ok, validation_pack_date_ok, 
      validation_barcode_detected_ok, validation_barcode_legible_ok, validation_barcode_ok,
      validation_summary,
      processed_image_container, processed_image_blob_name,
      ocr_overlay_container, ocr_overlay_blob_name,
      barcode_overlay_container, barcode_overlay_blob_name,
      barcode_roi_container, barcode_roi_blob_name,
      ocr_payload, barcode_payload
    ) VALUES (
      %(instance_id)s, %(created_at)s, now(),
      %(requested_by_user_id)s, %(requested_by_user_name)s, %(requested_by_user_role)s, %(requested_by_user_email)s,
      %(client_app_version)s, %(client_ip)s, %(client_user_agent)s, %(request_context_payload)s,
      %(input_container)s, %(input_blob_name)s,
      %(expected_prod_code)s, %(expected_prod_desc)s,
      %(expected_lot)s, %(expected_exp_date)s, %(expected_pack_date)s, 
      %(validation_lot_ok)s, %(validation_exp_date_ok)s, %(validation_pack_date_ok)s,
      %(validation_barcode_detected_ok)s, %(validation_barcode_legible_ok)s, %(validation_barcode_ok)s,
      %(validation_summary)s,
      %(processed_image_container)s, %(processed_image_blob_name)s,
      %(ocr_overlay_container)s, %(ocr_overlay_blob_name)s,
      %(barcode_overlay_container)s, %(barcode_overlay_blob_name)s,
      %(barcode_roi_container)s, %(barcode_roi_blob_name)s,
      %(ocr_payload)s, %(barcode_payload)s
    )
    ON CONFLICT (instance_id) DO UPDATE SET
      finished_at = now(),
      requested_by_user_id = EXCLUDED.requested_by_user_id,
      requested_by_user_name = EXCLUDED.requested_by_user_name,
      requested_by_user_role = EXCLUDED.requested_by_user_role,
      requested_by_user_email = EXCLUDED.requested_by_user_email,
      client_app_version = EXCLUDED.client_app_version,
      client_ip = EXCLUDED.client_ip,
      client_user_agent = EXCLUDED.client_user_agent,
      request_context_payload = EXCLUDED.request_context_payload,
      expected_prod_code = EXCLUDED.expected_prod_code,
      expected_prod_desc = EXCLUDED.expected_prod_desc,
      expected_lot = EXCLUDED.expected_lot,
      expected_exp_date = EXCLUDED.expected_exp_date,
      expected_pack_date = EXCLUDED.expected_pack_date,
      validation_lot_ok = EXCLUDED.validation_lot_ok,
      validation_exp_date_ok = EXCLUDED.validation_exp_date_ok,
      validation_pack_date_ok = EXCLUDED.validation_pack_date_ok,
      validation_barcode_detected_ok = EXCLUDED.validation_barcode_detected_ok,
      validation_barcode_legible_ok = EXCLUDED.validation_barcode_legible_ok,
      validation_barcode_ok = EXCLUDED.validation_barcode_ok,
      validation_summary = EXCLUDED.validation_summary,
      processed_image_container = EXCLUDED.processed_image_container,
      processed_image_blob_name = EXCLUDED.processed_image_blob_name,
      ocr_overlay_container = EXCLUDED.ocr_overlay_container,
      ocr_overlay_blob_name = EXCLUDED.ocr_overlay_blob_name,
      barcode_overlay_container = EXCLUDED.barcode_overlay_container,
      barcode_overlay_blob_name = EXCLUDED.barcode_overlay_blob_name,
      barcode_roi_container = EXCLUDED.barcode_roi_container,
      barcode_roi_blob_name = EXCLUDED.barcode_roi_blob_name,
      ocr_payload = EXCLUDED.ocr_payload,
      barcode_payload = EXCLUDED.barcode_payload;
    """

    params = {
        "instance_id": instance_id,
        "created_at": created_time,
        # Who initiated the run
        "requested_by_user_id": req_user.get("id"),
        "requested_by_user_name": req_user.get("name"),
        "requested_by_user_role": req_user.get("role"),
        "requested_by_user_email": req_user.get("email"),
        "client_app_version": req_client.get("appVersion"),
        "client_ip": req_client.get("ip"),
        "client_user_agent": req_client.get("userAgent"),
        "request_context_payload": Jsonb(req_ctx) if req_ctx else None,
        "input_container": input_obj.get("container"),
        "input_blob_name": input_obj.get("blobName"),
        # Expected product data
        "expected_prod_code": expected.get("prodCode"),
        "expected_prod_desc": expected.get("prodDesc"),
        "expected_lot": expected.get("lot"),
        "expected_exp_date": expected.get("expDate"),
        "expected_pack_date": expected.get("packDate"),
        # Validation flags
        "validation_lot_ok": val.get("lotOk"),
        "validation_exp_date_ok": val.get("expDateOk"),
        "validation_pack_date_ok": val.get("packDateOk"),
        "validation_barcode_detected_ok": val.get("barcodeDetectedOk"),
        "validation_barcode_legible_ok": val.get("barcodeLegibleOk"),
        "validation_barcode_ok": val.get("barcodeOk"),
        "validation_summary": val.get("validationSummary"),
        "processed_image_container": proc_blob.get("container"),
        "processed_image_blob_name": proc_blob.get("blobName"),
        "ocr_overlay_container": ocr_overlay.get("container"),
        "ocr_overlay_blob_name": ocr_overlay.get("blobName"),
        "barcode_overlay_container": bc_overlay.get("container"),
        "barcode_overlay_blob_name": bc_overlay.get("blobName"),
        "barcode_roi_container": bc_roi.get("container"),
        "barcode_roi_blob_name": bc_roi.get("blobName"),
        # Wrap dicts in Jsonb for psycopg3 to convert to PostgreSQL JSONB
        "ocr_payload": Jsonb(ocr) if ocr else None,
        "barcode_payload": Jsonb(barcode) if barcode else None,
    }

    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()

    return {"ok": True, "instanceId": instance_id}
