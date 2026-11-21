-- Compatibility migration for databases where 001 was applied before the
-- delivered-artifact provenance fields were introduced.
BEGIN;

ALTER TABLE ndvi_gee_processing_runs
    ADD COLUMN IF NOT EXISTS provenance_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
    ADD COLUMN IF NOT EXISTS source_artifacts JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE ndvi_gee_processing_runs
    DROP CONSTRAINT IF EXISTS chk_gee_run_provenance_status;
ALTER TABLE ndvi_gee_processing_runs
    ADD CONSTRAINT chk_gee_run_provenance_status
    CHECK (provenance_status IN ('verified', 'unverified'));

ALTER TABLE ndvi_gee_processing_runs
    DROP CONSTRAINT IF EXISTS chk_gee_run_source_artifacts;
ALTER TABLE ndvi_gee_processing_runs
    ADD CONSTRAINT chk_gee_run_source_artifacts
    CHECK (jsonb_typeof(source_artifacts) = 'array');

COMMIT;
