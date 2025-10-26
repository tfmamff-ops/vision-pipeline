-- Creates the vision_pipeline_log table to store execution logs of the Vision Pipeline,
-- including operator/auditor identity and client metadata.
-- Compatible with Azure Database for PostgreSQL (v12+).
-- Safe to execute multiple times (uses IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS vision_pipeline_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,

  -- === Request origin / operator context ===
  requested_by_user_id    text NOT NULL, -- stable unique ID from auth provider at execution time
  requested_by_user_name  text,          -- human-readable name snapshot at execution time (for audit/report)
  requested_by_user_role  text,          -- application-level role at execution time (qa_operator, auditor, admin, etc.)
  requested_by_user_email text,          -- email snapshot at execution time (for human-readable audit)

  client_app_version      text,          -- frontend/app version that initiated this run (e.g. "web-1.0.0")
  client_ip               text,          -- public IP observed by backend API
  client_user_agent       text,          -- user agent / device string
  request_context_payload jsonb,         -- full requestContext as received (user + client), for full traceability

  -- === Input references ===
  input_container text,
  input_blob_name text,

  -- === Expected product information (what the operator said the box SHOULD say) ===
  expected_prod_code    text, -- medication code (from expectedData.prodCode)
  expected_prod_desc    text, -- medication description/name (from expectedData.prodDesc)
  expected_lot          text,
  expected_exp_date     text,
  expected_pack_date    text,

  -- === Validation flags (true if OK) ===
  validation_lot_ok                  boolean,
  validation_exp_date_ok             boolean,
  validation_pack_date_ok            boolean,
  validation_barcode_detected_ok     boolean,
  validation_barcode_legible_ok      boolean,
  validation_barcode_ok              boolean,
  validation_summary                 boolean, -- overall result

  -- === Output blobs (processed images, overlays, ROI) ===
  processed_image_container text,
  processed_image_blob_name text,
  ocr_overlay_container     text,
  ocr_overlay_blob_name     text,
  barcode_overlay_container text,
  barcode_overlay_blob_name text,
  barcode_roi_container     text,
  barcode_roi_blob_name     text,

  -- === Raw payloads for deep inspection / debugging ===
  ocr_payload     jsonb,
  barcode_payload jsonb,

  -- Constraint to ensure finished_at >= created_at
  CONSTRAINT vision_pipeline_log_valid_finish CHECK (
    finished_at IS NULL OR finished_at >= created_at
  )
);

-- Basic indexes
CREATE INDEX IF NOT EXISTS vpl_created_idx
  ON vision_pipeline_log (created_at);

CREATE INDEX IF NOT EXISTS vpl_valsum_idx
  ON vision_pipeline_log (validation_summary);

-- Composite index for common query pattern (date range + validation filter)
CREATE INDEX IF NOT EXISTS vpl_date_valsum_idx
  ON vision_pipeline_log (created_at, validation_summary);

CREATE INDEX IF NOT EXISTS vpl_user_idx
  ON vision_pipeline_log (requested_by_user_id);

CREATE INDEX IF NOT EXISTS vpl_user_date_idx
  ON vision_pipeline_log (requested_by_user_id, created_at);

CREATE INDEX IF NOT EXISTS vpl_userrole_idx
  ON vision_pipeline_log (requested_by_user_role);

CREATE INDEX IF NOT EXISTS vpl_appver_idx
  ON vision_pipeline_log (client_app_version);

-- Lookups by medication code declared by the operator
CREATE INDEX IF NOT EXISTS vpl_expected_code_idx
  ON vision_pipeline_log (expected_prod_code);

-- Common filter: product code within date range
CREATE INDEX IF NOT EXISTS vpl_expected_code_date_idx
  ON vision_pipeline_log (expected_prod_code, created_at);

-- JSON search indexes
CREATE INDEX IF NOT EXISTS vpl_ocr_gin_idx
  ON vision_pipeline_log USING GIN (ocr_payload);

CREATE INDEX IF NOT EXISTS vpl_barcode_gin_idx
  ON vision_pipeline_log USING GIN (barcode_payload);

-- Documentation
COMMENT ON TABLE vision_pipeline_log IS
'Vision pipeline execution audit log including OCR and barcode validation results, operator identity, and client metadata.';

COMMENT ON COLUMN vision_pipeline_log.instance_id IS
'Durable Functions orchestration instance ID (unique identifier).';

COMMENT ON COLUMN vision_pipeline_log.requested_by_user_id IS
'Stable unique user ID from the authentication provider who initiated this pipeline run.';

COMMENT ON COLUMN vision_pipeline_log.requested_by_user_name IS
'Human-readable snapshot of the user name at execution time (e.g. "Bob Smith").';

COMMENT ON COLUMN vision_pipeline_log.requested_by_user_role IS
'Role of the requester at execution time (qa_operator, auditor, admin, etc.).';

COMMENT ON COLUMN vision_pipeline_log.requested_by_user_email IS
'Email of the requester at execution time, stored for human-readable audits or reports.';

COMMENT ON COLUMN vision_pipeline_log.client_app_version IS
'Version of the frontend or mobile client used to trigger this run (e.g. "web-1.0.0").';

COMMENT ON COLUMN vision_pipeline_log.client_ip IS
'Public IP address observed by the backend when the request was received.';

COMMENT ON COLUMN vision_pipeline_log.client_user_agent IS
'User agent string of the client (browser or device signature).';

COMMENT ON COLUMN vision_pipeline_log.request_context_payload IS
'Full requestContext (user + client) as received, stored as JSONB for forensic traceability.';

COMMENT ON COLUMN vision_pipeline_log.expected_prod_code IS
'Medication code provided in expectedData (declared by the operator as ground truth).';

COMMENT ON COLUMN vision_pipeline_log.expected_prod_desc IS
'Medication description/name provided in expectedData (declared by the operator as ground truth).';

COMMENT ON COLUMN vision_pipeline_log.validation_summary IS
'Overall validation result: true if all individual checks passed.';

COMMENT ON COLUMN vision_pipeline_log.ocr_payload IS
'Full Azure Computer Vision OCR response (JSONB).';

COMMENT ON COLUMN vision_pipeline_log.barcode_payload IS
'Full barcode detection and decoding result (JSONB).';
