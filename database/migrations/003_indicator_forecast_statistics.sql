-- Additive local schema for the 2025 thermal workflow and ward-level 2026 forecast.
-- Existing NDVI statistics remain untouched. Apply inside one transaction.
BEGIN;

CREATE TABLE IF NOT EXISTS ward_thermal_statistics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ward_id BIGINT NOT NULL,
    boundary_version VARCHAR(100) NOT NULL,
    year SMALLINT NOT NULL CHECK (year = 2025),
    ndvi_mean_source DOUBLE PRECISION NOT NULL CHECK (ndvi_mean_source BETWEEN -1 AND 1),
    lst_mean_c DOUBLE PRECISION,
    tvdi_mean DOUBLE PRECISION,
    source_file VARCHAR(500) NOT NULL,
    source_workflow VARCHAR(500) NOT NULL,
    source_checksum VARCHAR(64) NOT NULL CHECK (source_checksum ~ '^[0-9a-f]{64}$'),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_thermal_lst_finite CHECK (lst_mean_c IS NULL OR lst_mean_c BETWEEN -100 AND 150),
    CONSTRAINT chk_thermal_tvdi_range CHECK (tvdi_mean IS NULL OR tvdi_mean BETWEEN 0 AND 1),
    CONSTRAINT fk_thermal_ward_version FOREIGN KEY (ward_id, boundary_version)
        REFERENCES administrative_wards (id, boundary_version) ON DELETE RESTRICT,
    CONSTRAINT uq_thermal_ward_year_source UNIQUE (ward_id, boundary_version, year, source_checksum)
);

CREATE INDEX IF NOT EXISTS idx_thermal_year_source
    ON ward_thermal_statistics (year, source_checksum);

CREATE TABLE IF NOT EXISTS ndvi_forecast_model_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    artifact_checksum VARCHAR(64) NOT NULL UNIQUE CHECK (artifact_checksum ~ '^[0-9a-f]{64}$'),
    metrics_checksum VARCHAR(64) NOT NULL CHECK (metrics_checksum ~ '^[0-9a-f]{64}$'),
    source_metadata JSONB NOT NULL,
    validation_strategy TEXT,
    evaluation_period TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_forecast_model_metadata CHECK (jsonb_typeof(source_metadata) = 'object')
);

CREATE TABLE IF NOT EXISTS ward_ndvi_forecasts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ward_id BIGINT NOT NULL,
    boundary_version VARCHAR(100) NOT NULL,
    forecast_year SMALLINT NOT NULL CHECK (forecast_year = 2026),
    predicted_ndvi DOUBLE PRECISION NOT NULL CHECK (predicted_ndvi BETWEEN -1 AND 1),
    model_run_id BIGINT NOT NULL REFERENCES ndvi_forecast_model_runs (id) ON DELETE RESTRICT,
    source_file VARCHAR(500) NOT NULL,
    source_checksum VARCHAR(64) NOT NULL CHECK (source_checksum ~ '^[0-9a-f]{64}$'),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_forecast_ward_version FOREIGN KEY (ward_id, boundary_version)
        REFERENCES administrative_wards (id, boundary_version) ON DELETE RESTRICT,
    CONSTRAINT uq_forecast_ward_year_model_source UNIQUE (ward_id, boundary_version, forecast_year, model_run_id, source_checksum)
);

CREATE INDEX IF NOT EXISTS idx_ward_forecasts_year_source
    ON ward_ndvi_forecasts (forecast_year, source_checksum);

COMMIT;
