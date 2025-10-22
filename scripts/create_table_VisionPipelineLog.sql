-- Creates the VisionPipelineLog table to store execution logs of the Vision Pipeline.
-- Compatible with Azure Database for PostgreSQL (v12+).
-- Safe to execute multiple times (uses IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS "VisionPipelineLog" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "instanceId" text UNIQUE NOT NULL,
  "createdAt" timestamptz NOT NULL DEFAULT now(),
  "finishedAt" timestamptz,

  "inputContainer" text,
  "inputBlobName"  text,

  "expectedOrder" text,
  "expectedBatch" text,
  "expectedExpiry" text,

  "detectedOrder" text,
  "detectedBatch" text,
  "detectedExpiry" text,

  "decodedBarcodeValue" text,
  "barcodeSymbology" text,
  "barcodeDetected" boolean,
  "barcodeLegible" boolean,

  "validationOrderOK" boolean,
  "validationBatchOK" boolean,
  "validationExpiryOK" boolean,
  "validationBarcodeDetectedOK" boolean,
  "validationBarcodeLegibleOK" boolean,
  "validationBarcodeOK" boolean,
  "validationSummary" boolean,

  "processedImageContainer" text,
  "processedImageBlobName"  text,
  "ocrOverlayContainer"     text,
  "ocrOverlayBlobName"      text,
  "barcodeOverlayContainer" text,
  "barcodeOverlayBlobName"  text,
  "barcodeRoiContainer"     text,
  "barcodeRoiBlobName"      text,

  "ocrPayload" jsonb,
  "barcodePayload" jsonb,

  -- Constraint to ensure finishedAt >= createdAt
  CONSTRAINT valid_finish CHECK ("finishedAt" IS NULL OR "finishedAt" >= "createdAt")
);

-- Basic indexes
CREATE INDEX IF NOT EXISTS pr_created_idx ON "VisionPipelineLog" ("createdAt");
CREATE INDEX IF NOT EXISTS pr_valsum_idx ON "VisionPipelineLog" ("validationSummary");
CREATE INDEX IF NOT EXISTS pr_barcode_idx ON "VisionPipelineLog" ("decodedBarcodeValue");

-- Composite index for common query pattern (date range + validation filter)
CREATE INDEX IF NOT EXISTS pr_date_valsum_idx ON "VisionPipelineLog" ("createdAt", "validationSummary");

-- Optional: GIN indexes for JSONB querying (uncomment if needed)
CREATE INDEX IF NOT EXISTS pr_ocr_gin_idx ON "VisionPipelineLog" USING GIN ("ocrPayload");
CREATE INDEX IF NOT EXISTS pr_barcode_gin_idx ON "VisionPipelineLog" USING GIN ("barcodePayload");

-- Documentation
COMMENT ON TABLE "VisionPipelineLog" IS 'Vision pipeline execution audit log with OCR and barcode validation results';
COMMENT ON COLUMN "VisionPipelineLog"."instanceId" IS 'Durable Functions orchestration instance ID (unique identifier)';
COMMENT ON COLUMN "VisionPipelineLog"."validationSummary" IS 'Overall validation result: true if all checks passed';
COMMENT ON COLUMN "VisionPipelineLog"."ocrPayload" IS 'Complete Azure Computer Vision OCR response (JSONB)';
COMMENT ON COLUMN "VisionPipelineLog"."barcodePayload" IS 'Complete barcode detection and decoding results (JSONB)';