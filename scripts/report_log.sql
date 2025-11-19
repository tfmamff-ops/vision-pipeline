-- Creates the report_log table to store information about each generated report
-- (PDF and DOCX) produced by the Vision Pipeline reporting function.
-- Includes a foreign key referencing vision.vision_pipeline_log(instance_id).
-- Compatible with Azure Database for PostgreSQL (v12+).
-- Safe to execute multiple times (uses IF NOT EXISTS).

CREATE SCHEMA IF NOT EXISTS vision;

CREATE TABLE IF NOT EXISTS vision.report_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- === Foreign reference to the pipeline execution ===
  instance_id text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),

  -- === User context ===
  user_comment text,
  accepted     boolean NOT NULL,

  -- === Storage references ===
  container       text NOT NULL,
  pdf_blob_name  text NOT NULL,
  docx_blob_name text NOT NULL,

  -- === Foreign Key constraint enforcing integrity ===
  CONSTRAINT report_log_instance_fk
    FOREIGN KEY (instance_id)
    REFERENCES vision.vision_pipeline_log (instance_id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
);

-- === Indexes ===
CREATE INDEX IF NOT EXISTS reportlog_instance_idx
  ON vision.report_log (instance_id);

CREATE INDEX IF NOT EXISTS reportlog_created_idx
  ON vision.report_log (created_at);

CREATE INDEX IF NOT EXISTS reportlog_accepted_idx
  ON vision.report_log (accepted);

-- === Documentation ===
COMMENT ON TABLE vision.report_log IS
'Stores metadata of each generated report (PDF and DOCX) linked to a pipeline execution.';

COMMENT ON COLUMN vision.report_log.instance_id IS
'Foreign key referencing vision_pipeline_log.instance_id, identifying the pipeline run for this report.';

COMMENT ON COLUMN vision.report_log.user_comment IS
'User-provided comment included in the generated report.';

COMMENT ON COLUMN vision.report_log.accepted IS
'True if the operator marked the report as accepted; false if rejected.';

COMMENT ON COLUMN vision.report_log.container IS
'Blob Storage container where the PDF and DOCX reports were saved.';

COMMENT ON COLUMN vision.report_log.pdf_blob_name IS
'Blob name for the generated PDF report.';

COMMENT ON COLUMN vision.report_log.docx_blob_name IS
'Blob name for the generated DOCX report.';
