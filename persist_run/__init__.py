import os
import psycopg  # psycopg v3
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

POSTGRES_URL = os.environ["POSTGRES_URL"]  # e.g., "postgresql://user:pass@host:5432/dbname"

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
    proc_blob = (out.get("processedImageBlob") or {})
    ocr_overlay = (out.get("ocrOverlayBlob") or {})
    bc_overlay = (barcode.get("barcodeOverlayBlob") or {})
    bc_roi = (barcode.get("barcodeRoiBlob") or {})

    # UPSERT
    sql = """
    INSERT INTO "VisionPipelineLog" (
      "instanceId","createdAt","finishedAt",
      "requestedByUserId","requestedByUserRole","requestedByUserEmail",
      "clientAppVersion","clientIp","clientUserAgent","requestContextPayload",
      "inputContainer","inputBlobName",
      "expectedOrder","expectedBatch","expectedExpiry",
      "validationOrderOK","validationBatchOK","validationExpiryOK",
      "validationBarcodeDetectedOK","validationBarcodeLegibleOK","validationBarcodeOK",
      "validationSummary",
      "processedImageContainer","processedImageBlobName",
      "ocrOverlayContainer","ocrOverlayBlobName",
      "barcodeOverlayContainer","barcodeOverlayBlobName",
      "barcodeRoiContainer","barcodeRoiBlobName",
      "ocrPayload","barcodePayload"
    ) VALUES (
      %(instanceId)s,%(createdAt)s, now(),
      %(requestedByUserId)s,%(requestedByUserRole)s,%(requestedByUserEmail)s,
      %(clientAppVersion)s,%(clientIp)s,%(clientUserAgent)s,%(requestContextPayload)s,
      %(inputContainer)s,%(inputBlobName)s,
      %(expectedOrder)s,%(expectedBatch)s,%(expectedExpiry)s,
      %(validationOrderOK)s,%(validationBatchOK)s,%(validationExpiryOK)s,
      %(validationBarcodeDetectedOK)s,%(validationBarcodeLegibleOK)s,%(validationBarcodeOK)s,
      %(validationSummary)s,
      %(processedImageContainer)s,%(processedImageBlobName)s,
      %(ocrOverlayContainer)s,%(ocrOverlayBlobName)s,
      %(barcodeOverlayContainer)s,%(barcodeOverlayBlobName)s,
      %(barcodeRoiContainer)s,%(barcodeRoiBlobName)s,
      %(ocrPayload)s,%(barcodePayload)s
    )
    ON CONFLICT ("instanceId") DO UPDATE SET
      "finishedAt" = now(),
      "requestedByUserId"    = EXCLUDED."requestedByUserId",
      "requestedByUserRole"  = EXCLUDED."requestedByUserRole",
      "requestedByUserEmail" = EXCLUDED."requestedByUserEmail",
      "clientAppVersion"     = EXCLUDED."clientAppVersion",
      "clientIp"             = EXCLUDED."clientIp",
      "clientUserAgent"      = EXCLUDED."clientUserAgent",
      "requestContextPayload"= EXCLUDED."requestContextPayload",
      "validationOrderOK" = EXCLUDED."validationOrderOK",
      "validationBatchOK" = EXCLUDED."validationBatchOK",
      "validationExpiryOK" = EXCLUDED."validationExpiryOK",
      "validationBarcodeDetectedOK" = EXCLUDED."validationBarcodeDetectedOK",
      "validationBarcodeLegibleOK" = EXCLUDED."validationBarcodeLegibleOK",
      "validationBarcodeOK" = EXCLUDED."validationBarcodeOK",
      "validationSummary" = EXCLUDED."validationSummary",
      "processedImageContainer" = EXCLUDED."processedImageContainer",
      "processedImageBlobName"  = EXCLUDED."processedImageBlobName",
      "ocrOverlayContainer"     = EXCLUDED."ocrOverlayContainer",
      "ocrOverlayBlobName"      = EXCLUDED."ocrOverlayBlobName",
      "barcodeOverlayContainer" = EXCLUDED."barcodeOverlayContainer",
      "barcodeOverlayBlobName"  = EXCLUDED."barcodeOverlayBlobName",
      "barcodeRoiContainer"     = EXCLUDED."barcodeRoiContainer",
      "barcodeRoiBlobName"      = EXCLUDED."barcodeRoiBlobName",
      "ocrPayload"              = EXCLUDED."ocrPayload",
      "barcodePayload"          = EXCLUDED."barcodePayload";
    """

    params = {
      "instanceId": instance_id,
      "createdAt": created_time,

      # Who initiated the run
      "requestedByUserId": (req_user.get("id")),
      "requestedByUserRole": req_user.get("role"),
      "requestedByUserEmail": req_user.get("email"),
      "clientAppVersion": req_client.get("appVersion"),
      "clientIp": req_client.get("ip"),
      "clientUserAgent": req_client.get("userAgent"),
      "requestContextPayload": Jsonb(req_ctx) if req_ctx else None,

      "inputContainer": input_obj.get("container"),
      "inputBlobName":  input_obj.get("blobName"),

      "expectedOrder": expected.get("order"),
      "expectedBatch": expected.get("batch"),
      "expectedExpiry": expected.get("expiry"),

      "validationOrderOK":           val.get("orderOK"),
      "validationBatchOK":           val.get("batchOK"),
      "validationExpiryOK":          val.get("expiryOK"),
      "validationBarcodeDetectedOK": val.get("barcodeDetectedOK"),
      "validationBarcodeLegibleOK":  val.get("barcodeLegibleOK"),
      "validationBarcodeOK":         val.get("barcodeOK"),
      "validationSummary":           val.get("validationSummary"),

      "processedImageContainer": proc_blob.get("container"),
      "processedImageBlobName":  proc_blob.get("blobName"),

      "ocrOverlayContainer": ocr_overlay.get("container"),
      "ocrOverlayBlobName":  ocr_overlay.get("blobName"),

      "barcodeOverlayContainer": bc_overlay.get("container"),
      "barcodeOverlayBlobName":  bc_overlay.get("blobName"),

      "barcodeRoiContainer": bc_roi.get("container"),
      "barcodeRoiBlobName":  bc_roi.get("blobName"),

      # Wrap dicts in Jsonb for psycopg3 to convert to PostgreSQL JSONB
      "ocrPayload": Jsonb(ocr) if ocr else None,
      "barcodePayload": Jsonb(barcode) if barcode else None,
    }

    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
        conn.commit()

    return {"ok": True, "instanceId": instance_id}
