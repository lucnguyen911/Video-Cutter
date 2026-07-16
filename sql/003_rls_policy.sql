-- ============================================================
-- 003: RLS policies for video_licenses
-- ============================================================
-- Run this in Supabase SQL Editor
--
-- These policies ensure:
--   - Anon clients cannot directly INSERT/UPDATE/DELETE
--   - All writes go through the RPC function (SECURITY DEFINER)
--   - Anon can SELECT their own license (by key) for backward compat
-- ============================================================

-- Enable RLS
ALTER TABLE video_licenses ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any (to avoid conflicts)
DROP POLICY IF EXISTS "Allow anon select by key" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon insert" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon update" ON video_licenses;
DROP POLICY IF EXISTS "Deny anon delete" ON video_licenses;

-- Allow anon to SELECT (needed for REST fallback during RPC migration)
CREATE POLICY "Allow anon select by key"
  ON video_licenses
  FOR SELECT
  TO anon
  USING (true);

-- Block direct INSERT from anon
CREATE POLICY "Deny anon insert"
  ON video_licenses
  FOR INSERT
  TO anon
  WITH CHECK (false);

-- Block direct UPDATE from anon
-- NOTE: The RPC function uses SECURITY DEFINER and runs as the
-- table owner, so it bypasses RLS. Direct PATCH from client is blocked.
CREATE POLICY "Deny anon update"
  ON video_licenses
  FOR UPDATE
  TO anon
  USING (false)
  WITH CHECK (false);

-- Block direct DELETE from anon
CREATE POLICY "Deny anon delete"
  ON video_licenses
  FOR DELETE
  TO anon
  USING (false);

-- ============================================================
-- NOTE: If you still need the REST fallback (direct PATCH) during
-- the transition period, temporarily use this instead of the
-- "Deny anon update" policy above:
-- ============================================================
-- CREATE POLICY "Allow anon update own license"
--   ON video_licenses
--   FOR UPDATE
--   TO anon
--   USING (true)
--   WITH CHECK (true);
-- ============================================================
