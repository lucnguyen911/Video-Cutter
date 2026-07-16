-- ============================================================
-- 005: Rollback — Undo all migrations
-- ============================================================
-- Run this in Supabase SQL Editor ONLY if you need to revert.
-- Execute sections in reverse order (bottom to top).
-- ============================================================

-- ── Rollback 004: app_versions ──
DELETE FROM app_versions WHERE app_id = 'video_cutter';

ALTER TABLE app_versions
  DROP COLUMN IF EXISTS minimum_supported_version,
  DROP COLUMN IF EXISTS enforcement,
  DROP COLUMN IF EXISTS package_type,
  DROP COLUMN IF EXISTS sha256,
  DROP COLUMN IF EXISTS file_size,
  DROP COLUMN IF EXISTS is_active,
  DROP COLUMN IF EXISTS published_at;

-- ── Rollback 003: RLS policies ──
DROP POLICY IF EXISTS "Allow anon select by key" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon insert" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon update" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon delete" ON video_licenses;
ALTER TABLE video_licenses DISABLE ROW LEVEL SECURITY;

-- ── Rollback 002: RPC function ──
DROP FUNCTION IF EXISTS activate_or_verify_video_license_v2(TEXT, TEXT, INTEGER, TEXT[], TEXT);

-- ── Rollback 001: HWID v2 columns ──
DROP INDEX IF EXISTS idx_video_licenses_hwid_v2;

ALTER TABLE video_licenses
  DROP COLUMN IF EXISTS hwid_v2,
  DROP COLUMN IF EXISTS hwid_version,
  DROP COLUMN IF EXISTS legacy_hwid,
  DROP COLUMN IF EXISTS activated_at,
  DROP COLUMN IF EXISTS last_seen_at,
  DROP COLUMN IF EXISTS migration_completed_at;
