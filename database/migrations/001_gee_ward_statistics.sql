-- ============================================================
-- 1. Ranh giới 167 xa/phuong tu GeoJSON goc
-- ============================================================
CREATE TABLE administrative_wards (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Gia tri wardCode goc, luon xu ly nhu chuoi.
    ward_code VARCHAR(100) NOT NULL,
    ward VARCHAR(255) NOT NULL,

    -- ward_type la gia tri chuan hoa; raw giu nguyen tu GeoJSON.
    ward_type VARCHAR(10) NOT NULL,
    ward_type_raw VARCHAR(255) NOT NULL,

    -- Chi nhan thuoc tinh geom_km2 hop le tu nguon.
    -- Khong thay bang ST_Area cua geometry.
    geom_km2 NUMERIC(16, 6) NOT NULL
        CHECK (geom_km2 > 0),

    -- Luu geometry tu GeoJSON goc, sau MakeValid/CollectionExtract,
    -- tuyet doi khong Simplify.
    geom GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,

    boundary_version VARCHAR(100) NOT NULL,
    boundary_source VARCHAR(500),
    valid_from DATE,
    valid_to DATE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_administrative_wards_type
        CHECK (ward_type IN ('phuong', 'xa')),

    CONSTRAINT chk_administrative_wards_raw_type
        CHECK (btrim(ward_type_raw) <> ''),

    CONSTRAINT chk_administrative_wards_boundary_version
        CHECK (btrim(boundary_version) <> ''),

    CONSTRAINT chk_administrative_wards_valid_period
        CHECK (
            valid_from IS NULL
            OR valid_to IS NULL
            OR valid_to >= valid_from
        ),

    CONSTRAINT chk_administrative_wards_geometry
        CHECK (
            ST_SRID(geom) = 4326
            AND ST_GeometryType(geom) = 'ST_MultiPolygon'
            AND NOT ST_IsEmpty(geom)
            AND ST_IsValid(geom)
        ),

    -- Mot wardCode co the ton tai lai o version ranh gioi moi.
    CONSTRAINT uq_administrative_wards_code_version
        UNIQUE (ward_code, boundary_version),

    -- Dung cho khoa ngoai ghep, buoc dung boundary version.
    CONSTRAINT uq_administrative_wards_id_version
        UNIQUE (id, boundary_version)
);

CREATE INDEX idx_administrative_wards_geom
    ON administrative_wards USING GIST (geom);

CREATE INDEX idx_administrative_wards_boundary_version
    ON administrative_wards (boundary_version);


-- ============================================================
-- 2. Provenance cua mot GEE processing run cho dung mot nam
-- ============================================================
CREATE TABLE ndvi_gee_processing_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_key VARCHAR(150) NOT NULL UNIQUE,

    observation_year SMALLINT NOT NULL
        CHECK (observation_year BETWEEN 2015 AND 2025),

    gee_source VARCHAR(500) NOT NULL,
    gee_image_collection VARCHAR(500),

    -- The delivered artifacts do not contain a reproducible GEE export
    -- manifest.  Keep that fact queryable instead of implying provenance.
    provenance_status VARCHAR(30) NOT NULL DEFAULT 'unverified',
    source_artifacts JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Danh sach asset/image ID thuc te sau cloud filtering.
    source_image_ids JSONB NOT NULL,

    -- period_end la EXCLUSIVE, dung quy uoc ee.FilterDate(start, end).
    -- Vi du toan bo nam 2015: 2015-01-01 den 2016-01-01.
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    composite_method VARCHAR(100) NOT NULL,
    reducer_method VARCHAR(100) NOT NULL,
    ndvi_method_version VARCHAR(100) NOT NULL,

    output_crs VARCHAR(50) NOT NULL,
    resolution_m NUMERIC(12, 3) NOT NULL
        CHECK (resolution_m > 0),

    cloud_mask_method VARCHAR(255) NOT NULL,
    cloud_mask_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,

    boundary_version VARCHAR(100) NOT NULL,

    -- SHA-256 hexadecimal lower-case cua manifest chuan hoa.
    source_fingerprint VARCHAR(64) NOT NULL UNIQUE,

    notes TEXT,

    -- Cho phep NULL voi historical data khong ghi nhan thoi diem xu ly.
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_gee_run_period
        CHECK (period_end > period_start),

    -- Mot run nam N chi duoc dung period nam trong nam N.
    CONSTRAINT chk_gee_run_observation_year
        CHECK (
            period_start >= make_date(observation_year, 1, 1)
            AND period_end <= make_date(observation_year + 1, 1, 1)
        ),

    CONSTRAINT chk_gee_run_images
        CHECK (
            jsonb_typeof(source_image_ids) = 'array'
    ),

    CONSTRAINT chk_gee_run_provenance_status
        CHECK (provenance_status IN ('verified', 'unverified')),

    CONSTRAINT chk_gee_run_source_artifacts
        CHECK (jsonb_typeof(source_artifacts) = 'array'),

    CONSTRAINT chk_gee_run_cloud_parameters
        CHECK (jsonb_typeof(cloud_mask_parameters) = 'object'),

    CONSTRAINT chk_gee_run_boundary_version
        CHECK (btrim(boundary_version) <> ''),

    CONSTRAINT chk_gee_run_processing_times
        CHECK (
            processing_completed_at IS NULL
            OR processing_started_at IS NULL
            OR processing_completed_at >= processing_started_at
        ),

    CONSTRAINT chk_gee_run_fingerprint
        CHECK (source_fingerprint ~ '^[0-9a-f]{64}$'),

    -- Dung cho khoa ngoai ghep tu statistics.
    CONSTRAINT uq_gee_run_id_boundary_year
        UNIQUE (id, boundary_version, observation_year)
);

CREATE INDEX idx_gee_runs_boundary_year
    ON ndvi_gee_processing_runs (boundary_version, observation_year);

CREATE INDEX idx_gee_runs_period
    ON ndvi_gee_processing_runs (period_start, period_end);


-- ============================================================
-- 3. NDVI theo xa/phuong, nam va GEE processing run
-- ============================================================
CREATE TABLE ward_ndvi_statistics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    ward_id BIGINT NOT NULL,
    processing_run_id BIGINT NOT NULL,

    -- Luu tuong minh de hai FK ghep buoc cung version/cung nam.
    boundary_version VARCHAR(100) NOT NULL,
    year SMALLINT NOT NULL
        CHECK (year BETWEEN 2015 AND 2025),

    mean_ndvi DOUBLE PRECISION NOT NULL
        CHECK (mean_ndvi BETWEEN -1 AND 1),

    min_ndvi DOUBLE PRECISION NOT NULL
        CHECK (min_ndvi BETWEEN -1 AND 1),

    max_ndvi DOUBLE PRECISION NOT NULL
        CHECK (max_ndvi BETWEEN -1 AND 1),

    std_dev_ndvi DOUBLE PRECISION NOT NULL
        CHECK (std_dev_ndvi >= 0),

    pixel_count BIGINT NOT NULL
        CHECK (pixel_count > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_ward_ndvi_value_order
        CHECK (
            min_ndvi <= mean_ndvi
            AND mean_ndvi <= max_ndvi
        ),

    -- Ward phai thuoc chinh boundary version ghi tren statistics.
    CONSTRAINT fk_ward_ndvi_ward_version
        FOREIGN KEY (ward_id, boundary_version)
        REFERENCES administrative_wards (id, boundary_version)
        ON DELETE RESTRICT,

    -- Run phai dung boundary version va dung observation_year.
    CONSTRAINT fk_ward_ndvi_run_version_year
        FOREIGN KEY (processing_run_id, boundary_version, year)
        REFERENCES ndvi_gee_processing_runs (
            id,
            boundary_version,
            observation_year
        )
        ON DELETE RESTRICT,

    -- Moi run chi co mot thong ke cho mot ward.
    CONSTRAINT uq_ward_ndvi_run_ward
        UNIQUE (processing_run_id, ward_id)
);

CREATE INDEX idx_ward_ndvi_statistics_ward_year
    ON ward_ndvi_statistics (ward_id, year);

CREATE INDEX idx_ward_ndvi_statistics_year
    ON ward_ndvi_statistics (year);

CREATE INDEX idx_ward_ndvi_statistics_run
    ON ward_ndvi_statistics (processing_run_id);
