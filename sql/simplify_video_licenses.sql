-- One-table / one-HWID-column migration for Video Cutter.
-- Preconditions:
--   1) The current application (HWID v3) is deployed.
--   2) Every active license is intentionally limited to one device.
-- Run the whole file once in Supabase SQL Editor.

BEGIN;

-- The earlier optional admin view references hwid_v3. This migration keeps
-- only the base table, so remove that presentation-only object first.
DROP VIEW IF EXISTS public.video_licenses_admin;

-- Store the current v3 binding in the familiar `hwid` column before removing
-- the implementation-specific v3 columns. Legacy rows with no hwid_v3 remain
-- untouched until their next successful v3 activation, when the RPC upgrades them.
UPDATE public.video_licenses
SET hwid = hwid_v3
WHERE NULLIF(hwid_v3, '') IS NOT NULL
  AND hwid IS DISTINCT FROM hwid_v3;

-- This product licenses one device per key. Make the displayed field enforce
-- the same policy as the server-side RPC.
UPDATE public.video_licenses
SET max_devices = 1
WHERE max_devices IS DISTINCT FROM 1;

ALTER TABLE public.video_licenses
  ALTER COLUMN max_devices SET DEFAULT 1,
  ALTER COLUMN max_devices SET NOT NULL;

ALTER TABLE public.video_licenses
  DROP CONSTRAINT IF EXISTS video_licenses_max_devices_one;

ALTER TABLE public.video_licenses
  ADD CONSTRAINT video_licenses_max_devices_one CHECK (max_devices = 1);

-- Replace the RPC before deleting the old technical columns. Its public
-- signature does not change, so the current desktop application needs no code
-- change. It keeps one-device enforcement and supports a one-time legacy-to-v3
-- upgrade by replacing `hwid` only after a legacy candidate matches.
CREATE OR REPLACE FUNCTION public.activate_or_verify_video_license_v3(
    p_license_key text,
    p_hwid_v3 text,
    p_hwid_version integer,
    p_legacy_candidates text[],
    p_app_version text
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_license public.video_licenses%ROWTYPE;
BEGIN
    IF p_license_key IS NULL OR length(trim(p_license_key)) < 10
       OR p_hwid_v3 IS NULL OR p_hwid_v3 !~ '^[0-9a-f]{64}$'
       OR p_hwid_version <> 3 THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_DATA_INVALID', 'message', 'Dữ liệu kích hoạt không hợp lệ.');
    END IF;

    SELECT * INTO v_license
      FROM public.video_licenses
     WHERE license_key = trim(p_license_key)
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_NOT_FOUND', 'message', 'Key bản quyền không tồn tại.');
    END IF;
    IF v_license.is_active IS NOT TRUE THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_DISABLED', 'message', 'Key bản quyền đã bị vô hiệu hóa.');
    END IF;
    IF v_license.expired_at IS NOT NULL AND v_license.expired_at < now() THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_EXPIRED', 'message', 'Mã kích hoạt đã hết hạn.');
    END IF;

    -- Unbound key: bind it to the first v3 device.
    IF NULLIF(v_license.hwid, '') IS NULL THEN
        UPDATE public.video_licenses SET hwid = p_hwid_v3 WHERE id = v_license.id;
        RETURN json_build_object('valid', true, 'status', 'ACTIVATED', 'message', 'Kích hoạt thành công.', 'expired_at', v_license.expired_at);
    END IF;

    -- Already bound to this exact v3 device.
    IF v_license.hwid = p_hwid_v3 THEN
        RETURN json_build_object('valid', true, 'status', 'VALID', 'message', 'Bản quyền hợp lệ.', 'expired_at', v_license.expired_at);
    END IF;

    -- An old HWID can be replaced once only if the same machine proves it by
    -- presenting one of its locally-derived legacy candidates.
    IF p_legacy_candidates IS NOT NULL AND v_license.hwid = ANY(p_legacy_candidates) THEN
        UPDATE public.video_licenses SET hwid = p_hwid_v3 WHERE id = v_license.id;
        RETURN json_build_object('valid', true, 'status', 'MIGRATED', 'message', 'Đã nâng cấp định danh thiết bị.', 'expired_at', v_license.expired_at);
    END IF;

    RETURN json_build_object('valid', false, 'status', 'DEVICE_MISMATCH', 'message', 'Key đã được dùng ở máy khác.');
END;
$$;

REVOKE ALL ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) TO anon, authenticated;

ALTER TABLE public.video_licenses
  DROP COLUMN IF EXISTS hwid_v3,
  DROP COLUMN IF EXISTS hwid_v3_version,
  DROP COLUMN IF EXISTS hwid_v3_migrated_at;

COMMENT ON COLUMN public.video_licenses.hwid IS
  'Canonical hardware binding (HWID v3 for all new and migrated licenses).';

COMMIT;
