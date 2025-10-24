-- Creates the VisionPipelineLog table to store execution logs of the Vision Pipeline,
-- including operator/auditor identity and client metadata.
-- Compatible with Azure Database for PostgreSQL (v12+).
-- Safe to execute multiple times (uses IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS "VisionPipelineLog" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "instanceId" text UNIQUE NOT NULL,
  "createdAt" timestamptz NOT NULL DEFAULT now(),
  "finishedAt" timestamptz,

  -- === Request origin / operator context ===
  "requestedByUserId"    text NOT NULL, -- stable unique ID from auth provider at execution time
  "requestedByUserName"  text,          -- human-readable name snapshot at execution time (for audit/report)
  "requestedByUserRole"  text,          -- application-level role at execution time (qa_operator, auditor, admin, etc.)
  "requestedByUserEmail" text,          -- email snapshot at execution time (for human-readable audit)
  "clientAppVersion"     text,          -- frontend/app version that initiated this run (e.g. "web-1.3.7")
  "clientIp"             text,          -- public IP observed by backend API
  "clientUserAgent"      text,          -- user agent / device string
  "requestContextPayload" jsonb,        -- full requestContext as received (user + client), for full traceability

  -- === Input references ===
  "inputContainer" text,
  "inputBlobName"  text,

  "expectedOrder" text,
  "expectedBatch" text,
  "expectedExpiry" text,

  -- === Validation flags ===
  "validationOrderOK" boolean,
  "validationBatchOK" boolean,
  "validationExpiryOK" boolean,
  "validationBarcodeDetectedOK" boolean,
  "validationBarcodeLegibleOK" boolean,
  "validationBarcodeOK" boolean,
  "validationSummary" boolean,

  -- === Output blobs (processed images, overlays, ROI) ===
  "processedImageContainer" text,
  "processedImageBlobName"  text,
  "ocrOverlayContainer"     text,
  "ocrOverlayBlobName"      text,
  "barcodeOverlayContainer" text,
  "barcodeOverlayBlobName"  text,
  "barcodeRoiContainer"     text,
  "barcodeRoiBlobName"      text,

  -- === Raw payloads for deep inspection / debugging ===
  "ocrPayload" jsonb,
  "barcodePayload" jsonb,

  -- Constraint to ensure finishedAt >= createdAt
  CONSTRAINT valid_finish CHECK ("finishedAt" IS NULL OR "finishedAt" >= "createdAt")
);

-- Basic indexes
CREATE INDEX IF NOT EXISTS pr_created_idx
  ON "VisionPipelineLog" ("createdAt");

CREATE INDEX IF NOT EXISTS pr_valsum_idx
  ON "VisionPipelineLog" ("validationSummary");

-- Composite index for common query pattern (date range + validation filter)
CREATE INDEX IF NOT EXISTS pr_date_valsum_idx
  ON "VisionPipelineLog" ("createdAt", "validationSummary");

CREATE INDEX IF NOT EXISTS pr_user_idx
  ON "VisionPipelineLog" ("requestedByUserId");

CREATE INDEX IF NOT EXISTS pr_user_date_idx
  ON "VisionPipelineLog" ("requestedByUserId", "createdAt");

CREATE INDEX IF NOT EXISTS pr_userrole_idx
  ON "VisionPipelineLog" ("requestedByUserRole");

CREATE INDEX IF NOT EXISTS pr_appver_idx
  ON "VisionPipelineLog" ("clientAppVersion");

CREATE INDEX IF NOT EXISTS pr_ocr_gin_idx
  ON "VisionPipelineLog" USING GIN ("ocrPayload");

CREATE INDEX IF NOT EXISTS pr_barcode_gin_idx
  ON "VisionPipelineLog" USING GIN ("barcodePayload");

-- Documentation
COMMENT ON TABLE "VisionPipelineLog" IS
'Vision pipeline execution audit log including OCR and barcode validation results, operator identity, and client metadata.';

COMMENT ON COLUMN "VisionPipelineLog"."instanceId" IS
'Durable Functions orchestration instance ID (unique identifier).';

COMMENT ON COLUMN "VisionPipelineLog"."requestedByUserId" IS
'Stable unique user ID from the authentication provider who initiated this pipeline run.';

COMMENT ON COLUMN "VisionPipelineLog"."requestedByUserName" IS
'Human-readable snapshot of the user name at execution time (e.g. "Laura Fernández").';

COMMENT ON COLUMN "VisionPipelineLog"."requestedByUserRole" IS
'Role of the requester at execution time (qa_operator, auditor, admin, etc.).';

COMMENT ON COLUMN "VisionPipelineLog"."requestedByUserEmail" IS
'Email of the requester at execution time, stored for human-readable audits or reports.';

COMMENT ON COLUMN "VisionPipelineLog"."clientAppVersion" IS
'Version of the frontend or mobile client used to trigger this run (e.g. "web-1.3.7").';

COMMENT ON COLUMN "VisionPipelineLog"."clientIp" IS
'Public IP address observed by the backend when the request was received.';

COMMENT ON COLUMN "VisionPipelineLog"."clientUserAgent" IS
'User agent string of the client (browser or device signature).';

COMMENT ON COLUMN "VisionPipelineLog"."requestContextPayload" IS
'Full requestContext (user + client) as received, stored as JSONB for forensic traceability.';

COMMENT ON COLUMN "VisionPipelineLog"."validationSummary" IS
'Overall validation result: true if all individual checks passed.';

COMMENT ON COLUMN "VisionPipelineLog"."ocrPayload" IS
'Full Azure Computer Vision OCR response (JSONB).';

COMMENT ON COLUMN "VisionPipelineLog"."barcodePayload" IS
'Full barcode detection and decoding result (JSONB).';
