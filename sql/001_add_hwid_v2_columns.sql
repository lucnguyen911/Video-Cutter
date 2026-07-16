-- ============================================================
-- 001: Add HWID v2 columns to video_licenses
-- ============================================================
-- Run this in Supabase SQL Editor
-- This migration adds columns for HWID v2 support while
-- keeping the existing 'hwid' column for backward compatibility.
-- ============================================================

ALTER TABLE video_licenses
  ADD COLUMN IF NOT EXISTS hwid_v2 TEXT,
  ADD COLUMN IF NOT EXISTS hwid_version INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS legacy_hwid TEXT,
  ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS migration_completed_at TIMESTAMPTZ;

-- Index for faster lookups by hwid_v2
CREATE INDEX IF NOT EXISTS idx_video_licenses_hwid_v2
  ON video_licenses (hwid_v2);

COMMENT ON COLUMN video_licenses.hwid_v2 IS 'HWID v2: SHA256 of MachineGuid (stable)';
COMMENT ON COLUMN video_licenses.hwid_version IS '1=legacy (WMIC+disk), 2=MachineGuid';
COMMENT ON COLUMN video_licenses.legacy_hwid IS 'Original HWID before migration to v2';
COMMENT ON COLUMN video_licenses.activated_at IS 'When the license was first bound to a device';
COMMENT ON COLUMN video_licenses.last_seen_at IS 'Last successful verification timestamp';
COMMENT ON COLUMN video_licenses.migration_completed_at IS 'When HWID was migrated from v1 to v2';
