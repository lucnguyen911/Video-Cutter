-- Rollback migration for video_licenses and app_versions

DROP FUNCTION IF EXISTS activate_or_verify_video_license_v2(text, text, integer, text[], text);

DROP POLICY IF EXISTS "Allow anon read-only" ON video_licenses;

ALTER TABLE video_licenses DROP COLUMN IF EXISTS hwid_v2;
ALTER TABLE video_licenses DROP COLUMN IF EXISTS hwid_version;
ALTER TABLE video_licenses DROP COLUMN IF EXISTS legacy_hwid;
ALTER TABLE video_licenses DROP COLUMN IF EXISTS activated_at;
ALTER TABLE video_licenses DROP COLUMN IF EXISTS last_seen_at;
ALTER TABLE video_licenses DROP COLUMN IF EXISTS migration_completed_at;

ALTER TABLE app_versions DROP COLUMN IF EXISTS minimum_supported_version;
ALTER TABLE app_versions DROP COLUMN IF EXISTS enforcement;
ALTER TABLE app_versions DROP COLUMN IF EXISTS package_type;
ALTER TABLE app_versions DROP COLUMN IF EXISTS sha256;
ALTER TABLE app_versions DROP COLUMN IF EXISTS file_size;
ALTER TABLE app_versions DROP COLUMN IF EXISTS is_active;
ALTER TABLE app_versions DROP COLUMN IF EXISTS published_at;
