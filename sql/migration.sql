-- Video Cutter security migration: HWID v3, least-privilege RLS, safe update metadata.
-- Run in Supabase SQL Editor as the project owner. It preserves the v2 RPC so
-- existing released clients continue to work while v3 clients migrate once.

ALTER TABLE public.video_licenses ADD COLUMN IF NOT EXISTS hwid_v3 text;
ALTER TABLE public.video_licenses ADD COLUMN IF NOT EXISTS hwid_v3_version integer;
ALTER TABLE public.video_licenses ADD COLUMN IF NOT EXISTS hwid_v3_migrated_at timestamptz;

ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS minimum_supported_version text;
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS enforcement text DEFAULT 'optional';
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS package_type text DEFAULT 'full';
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS sha256 text;
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS file_size bigint;
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
ALTER TABLE public.app_versions ADD COLUMN IF NOT EXISTS published_at timestamptz NOT NULL DEFAULT now();

-- License data must never be readable from the browser/desktop client.
ALTER TABLE public.video_licenses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow anon read-only" ON public.video_licenses;
DROP POLICY IF EXISTS "Public can read video licenses" ON public.video_licenses;
REVOKE ALL ON TABLE public.video_licenses FROM anon, authenticated;

-- The client can read only the active update row. Write access remains owner/server-only.
ALTER TABLE public.app_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public can read active app versions" ON public.app_versions;
DROP POLICY IF EXISTS "Allow anon read-only" ON public.app_versions;
CREATE POLICY "Public can read active app versions"
  ON public.app_versions FOR SELECT TO anon, authenticated
  USING (is_active IS TRUE);
REVOKE ALL ON TABLE public.app_versions FROM anon, authenticated;
GRANT SELECT ON TABLE public.app_versions TO anon, authenticated;

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
    v_now timestamptz := now();
    v_candidate text;
    v_candidate_matches boolean := false;
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
    IF v_license.is_active IS FALSE THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_DISABLED', 'message', 'Key bản quyền đã bị vô hiệu hóa.');
    END IF;
    IF v_license.expired_at IS NOT NULL AND v_license.expired_at < v_now THEN
        RETURN json_build_object('valid', false, 'status', 'LICENSE_EXPIRED', 'message', 'Mã kích hoạt đã hết hạn.');
    END IF;

    IF COALESCE(v_license.hwid_v3, '') <> '' THEN
        IF v_license.hwid_v3 <> p_hwid_v3 THEN
            RETURN json_build_object('valid', false, 'status', 'DEVICE_MISMATCH', 'message', 'Key đã được dùng ở máy khác.');
        END IF;
        RETURN json_build_object('valid', true, 'status', 'VALID', 'message', 'Bản quyền hợp lệ.', 'expired_at', v_license.expired_at);
    END IF;

    -- A v2/legacy value is accepted only as proof to bind this exact license once.
    IF p_legacy_candidates IS NOT NULL THEN
        FOREACH v_candidate IN ARRAY p_legacy_candidates LOOP
            -- The deployed legacy schema uses `hwid`; it has no `hwid_v2` column.
            IF v_candidate = v_license.hwid THEN
                v_candidate_matches := true;
                EXIT;
            END IF;
        END LOOP;
    END IF;

    IF COALESCE(v_license.hwid, '') <> '' THEN
        IF NOT v_candidate_matches THEN
            RETURN json_build_object('valid', false, 'status', 'DEVICE_MISMATCH', 'message', 'Thiết bị hiện tại không khớp máy đã kích hoạt.');
        END IF;
        UPDATE public.video_licenses
           SET hwid_v3 = p_hwid_v3,
               hwid_v3_version = p_hwid_version,
               hwid_v3_migrated_at = v_now
         WHERE id = v_license.id;
        RETURN json_build_object('valid', true, 'status', 'MIGRATED', 'message', 'Đã nâng cấp định danh thiết bị.', 'expired_at', v_license.expired_at);
    END IF;

    UPDATE public.video_licenses
       SET hwid_v3 = p_hwid_v3,
           hwid_v3_version = p_hwid_version
     WHERE id = v_license.id;
    RETURN json_build_object('valid', true, 'status', 'ACTIVATED', 'message', 'Kích hoạt thành công.', 'expired_at', v_license.expired_at);
END;
$$;

REVOKE ALL ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) TO anon, authenticated;