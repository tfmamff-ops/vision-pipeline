-- Azure Database for PostgreSQL - Vision Pipeline Run Table
-- Compatible with PostgreSQL 12+

CREATE TABLE IF NOT EXISTS "VisionPipelineRun" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  "instanceId" text UNIQUE NOT NULL,
  "createdAt" timestamptz NOT NULL DEFAULT now(),
  "finishedAt" timestamptz,
  
  -- Computed columns for reports and monitoring
  "processedDate" date GENERATED ALWAYS AS (DATE("finishedAt")) STORED,
  "processingDurationMs" integer GENERATED ALWAYS AS (
    CASE WHEN "finishedAt" IS NOT NULL 
    THEN CAST(EXTRACT(EPOCH FROM ("finishedAt" - "createdAt")) * 1000 AS integer)
    ELSE NULL END
  ) STORED,

  -- Input reference
  "inputContainer" text,
  "inputBlobName"  text,

  -- Expected data (from request)
  "expectedOrder" text,
  "expectedBatch" text,
  "expectedExpiry" text,

  -- Detected data (parsed from OCR - can be populated later if needed)
  "detectedOrder" text,
  "detectedBatch" text,
  "detectedExpiry" text,

  -- Barcode data
  "decodedBarcodeValue" text,
  "barcodeSymbology" text,
  "barcodeDetected" boolean,
  "barcodeLegible" boolean,

  -- Validation results
  "validationOrderOK" boolean,
  "validationBatchOK" boolean,
  "validationExpiryOK" boolean,
  "validationBarcodeDetectedOK" boolean,
  "validationBarcodeLegibleOK" boolean,
  "validationBarcodeOK" boolean,
  "validationSummary" boolean,

  -- Output blob references
  "processedImageContainer" text,
  "processedImageBlobName"  text,
  "ocrOverlayContainer"     text,
  "ocrOverlayBlobName"      text,
  "barcodeOverlayContainer" text,
  "barcodeOverlayBlobName"  text,
  "barcodeRoiContainer"     text,
  "barcodeRoiBlobName"      text,

  -- Full payloads (JSONB for flexible querying)
  "ocrPayload" jsonb,
  "barcodePayload" jsonb,

  -- Constraint to ensure finishedAt is after createdAt
  CONSTRAINT valid_finish CHECK ("finishedAt" IS NULL OR "finishedAt" >= "createdAt")
);

-- Basic indexes for common queries
CREATE INDEX IF NOT EXISTS vpr_created_idx ON "VisionPipelineRun" ("createdAt");
CREATE INDEX IF NOT EXISTS vpr_valsum_idx ON "VisionPipelineRun" ("validationSummary");
CREATE INDEX IF NOT EXISTS vpr_barcode_idx ON "VisionPipelineRun" ("decodedBarcodeValue");
CREATE INDEX IF NOT EXISTS vpr_date_idx ON "VisionPipelineRun" ("processedDate");

-- Composite index for common filtering pattern (date range + validation status)
CREATE INDEX IF NOT EXISTS vpr_date_valsum_idx ON "VisionPipelineRun" ("createdAt", "validationSummary");

-- Optional GIN indexes for JSONB querying (uncomment if needed)
-- CREATE INDEX IF NOT EXISTS vpr_ocr_gin_idx ON "VisionPipelineRun" USING GIN ("ocrPayload");
-- CREATE INDEX IF NOT EXISTS vpr_barcode_gin_idx ON "VisionPipelineRun" USING GIN ("barcodePayload");

-- Comments for documentation
COMMENT ON TABLE "VisionPipelineRun" IS 'Stores complete audit trail of vision pipeline orchestration runs with validation results';
COMMENT ON COLUMN "VisionPipelineRun"."instanceId" IS 'Durable Functions orchestration instance ID (unique)';
COMMENT ON COLUMN "VisionPipelineRun"."processedDate" IS 'Computed: date part of finishedAt for date-based reporting';
COMMENT ON COLUMN "VisionPipelineRun"."processingDurationMs" IS 'Computed: total processing time in milliseconds';
COMMENT ON COLUMN "VisionPipelineRun"."validationSummary" IS 'Overall validation result: true if all validations passed';
COMMENT ON COLUMN "VisionPipelineRun"."ocrPayload" IS 'Complete Azure Computer Vision OCR response (JSONB)';
COMMENT ON COLUMN "VisionPipelineRun"."barcodePayload" IS 'Complete barcode detection and decoding results (JSONB)';
