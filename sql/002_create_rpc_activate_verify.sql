-- ============================================================
-- 002: Create RPC function activate_or_verify_video_license_v2
-- ============================================================
-- Run this in Supabase SQL Editor
--
-- This function handles all license operations atomically:
--   1. LICENSE_NOT_FOUND — key doesn't exist
--   2. LICENSE_DISABLED — is_active = false
--   3. LICENSE_EXPIRED — expired_at < now
--   4. VALID — hwid_v2 matches, update last_seen_at
--   5. DEVICE_MISMATCH — hwid_v2 doesn't match
--   6. ACTIVATED — first bind (no hwid yet)
--   7. MIGRATED — legacy hwid matched, upgraded to v2
--   8. LEGACY_DEVICE_MISMATCH — has legacy hwid, no candidate matches
-- ============================================================

CREATE OR REPLACE FUNCTION activate_or_verify_video_license_v2(
  p_license_key TEXT,
  p_hwid_v2 TEXT,
  p_hwid_version INTEGER DEFAULT 2,
  p_legacy_candidates TEXT[] DEFAULT '{}',
  p_app_version TEXT DEFAULT ''
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER  -- Runs with table owner privileges
AS $$
DECLARE
  v_license RECORD;
  v_candidate TEXT;
  v_result JSON;
BEGIN
  -- Lock the row for atomic read-modify-write
  SELECT *
  INTO v_license
  FROM video_licenses
  WHERE license_key = p_license_key
  FOR UPDATE;

  -- Case 1: Key not found
  IF NOT FOUND THEN
    RETURN json_build_object(
      'status', 'LICENSE_NOT_FOUND',
      'message', 'Key bản quyền không tồn tại.'
    );
  END IF;

  -- Case 2: License disabled
  IF v_license.is_active = FALSE THEN
    RETURN json_build_object(
      'status', 'LICENSE_DISABLED',
      'message', 'Key bản quyền đã bị vô hiệu hóa.'
    );
  END IF;

  -- Case 3: License expired
  IF v_license.expired_at IS NOT NULL
     AND v_license.expired_at < NOW() THEN
    RETURN json_build_object(
      'status', 'LICENSE_EXPIRED',
      'message', 'Mã kích hoạt đã hết hạn.',
      'expires_at', v_license.expired_at
    );
  END IF;

  -- Case 4: hwid_v2 already bound and matches
  IF v_license.hwid_v2 IS NOT NULL AND v_license.hwid_v2 = p_hwid_v2 THEN
    UPDATE video_licenses
    SET last_seen_at = NOW()
    WHERE license_key = p_license_key;

    RETURN json_build_object(
      'status', 'VALID',
      'message', 'Bản quyền hợp lệ.',
      'expires_at', v_license.expired_at
    );
  END IF;

  -- Case 5: hwid_v2 already bound but different device
  IF v_license.hwid_v2 IS NOT NULL AND v_license.hwid_v2 != p_hwid_v2 THEN
    RETURN json_build_object(
      'status', 'DEVICE_MISMATCH',
      'message', 'Key đã được sử dụng ở máy khác.'
    );
  END IF;

  -- Case 6: No HWID bound at all (neither v1 nor v2)
  IF (v_license.hwid IS NULL OR v_license.hwid = '')
     AND (v_license.hwid_v2 IS NULL OR v_license.hwid_v2 = '') THEN
    UPDATE video_licenses
    SET
      hwid_v2 = p_hwid_v2,
      hwid_version = p_hwid_version,
      activated_at = NOW(),
      last_seen_at = NOW()
    WHERE license_key = p_license_key;

    RETURN json_build_object(
      'status', 'ACTIVATED',
      'message', 'Kích hoạt bản quyền thành công trên máy này!',
      'expires_at', v_license.expired_at
    );
  END IF;

  -- Case 7: Has legacy HWID (v1), try to match candidates
  IF v_license.hwid IS NOT NULL AND v_license.hwid != '' THEN
    FOREACH v_candidate IN ARRAY p_legacy_candidates
    LOOP
      IF v_license.hwid = v_candidate THEN
        -- Legacy HWID matches — migrate to v2
        UPDATE video_licenses
        SET
          hwid_v2 = p_hwid_v2,
          hwid_version = p_hwid_version,
          legacy_hwid = v_license.hwid,
          migration_completed_at = NOW(),
          last_seen_at = NOW()
        WHERE license_key = p_license_key;

        RETURN json_build_object(
          'status', 'MIGRATED',
          'message', 'Bản quyền đã được chuyển đổi sang thiết bị mới thành công!',
          'expires_at', v_license.expired_at
        );
      END IF;
    END LOOP;

    -- Case 8: Legacy HWID exists but no candidate matches
    RETURN json_build_object(
      'status', 'LEGACY_DEVICE_MISMATCH',
      'message', 'Key đã được sử dụng ở máy khác (legacy).'
    );
  END IF;

  -- Fallback (should not reach here)
  RETURN json_build_object(
    'status', 'SERVER_ERROR',
    'message', 'Lỗi xử lý bản quyền không xác định.'
  );
END;
$$;

-- Grant execute to anon role (for Supabase client)
GRANT EXECUTE ON FUNCTION activate_or_verify_video_license_v2(TEXT, TEXT, INTEGER, TEXT[], TEXT)
  TO anon;

GRANT EXECUTE ON FUNCTION activate_or_verify_video_license_v2(TEXT, TEXT, INTEGER, TEXT[], TEXT)
  TO authenticated;
