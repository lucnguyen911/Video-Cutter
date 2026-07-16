-- ============================================================
-- 004: Migrate app_versions table for video_cutter
-- ============================================================
-- Run this in Supabase SQL Editor
--
-- Strategy: Add new 'video_cutter' row. Keep old 'video_factory'
-- row for backward compatibility with old clients.
-- ============================================================

-- Add new columns to app_versions if they don't exist
ALTER TABLE app_versions
  ADD COLUMN IF NOT EXISTS minimum_supported_version TEXT,
  ADD COLUMN IF NOT EXISTS enforcement TEXT NOT NULL DEFAULT 'optional',
  ADD COLUMN IF NOT EXISTS package_type TEXT NOT NULL DEFAULT 'full',
  ADD COLUMN IF NOT EXISTS sha256 TEXT,
  ADD COLUMN IF NOT EXISTS file_size BIGINT,
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ DEFAULT NOW();

-- Insert video_cutter row (if not exists)
INSERT INTO app_versions (
  app_id,
  latest_version,
  minimum_supported_version,
  download_url,
  changelog,
  enforcement,
  package_type,
  sha256,
  file_size,
  is_active,
  published_at
)
SELECT
  'video_cutter',
  COALESCE(
    (SELECT latest_version FROM app_versions WHERE app_id = 'video_factory' LIMIT 1),
    '1.0.0'
  ),
  '1.0.0',
  COALESCE(
    (SELECT download_url FROM app_versions WHERE app_id = 'video_factory' LIMIT 1),
    ''
  ),
  COALESCE(
    (SELECT changelog FROM app_versions WHERE app_id = 'video_factory' LIMIT 1),
    'Initial release'
  ),
  'optional',
  'full',
  NULL,
  NULL,
  TRUE,
  NOW()
WHERE NOT EXISTS (
  SELECT 1 FROM app_versions WHERE app_id = 'video_cutter'
);

-- Add backward compatibility: copy update_type to enforcement for old rows
-- This handles clients that read 'update_type' field
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'app_versions' AND column_name = 'update_type'
  ) THEN
    UPDATE app_versions
    SET enforcement = update_type
    WHERE enforcement = 'optional'
      AND update_type IS NOT NULL
      AND update_type != '';
  END IF;
END $$;

COMMENT ON COLUMN app_versions.enforcement IS 'optional or forced';
COMMENT ON COLUMN app_versions.package_type IS 'full (installer) or patch (zip)';
COMMENT ON COLUMN app_versions.sha256 IS 'SHA-256 hash of the download package';
COMMENT ON COLUMN app_versions.file_size IS 'Size of the download package in bytes';
