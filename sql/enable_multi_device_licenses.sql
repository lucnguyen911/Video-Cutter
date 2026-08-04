-- Video Cutter: one-table, multi-device license migration.
-- Use THIS file instead of simplify_video_licenses.sql.
-- It keeps one physical table: public.video_licenses.
-- The desktop app keeps calling the same v3 RPC, so no application rebuild is
-- needed for this server-side change.

BEGIN;

-- The old presentation-only view is not needed and can block schema changes.
DROP VIEW IF EXISTS public.video_licenses_admin;

-- device_hwids is the sole device-binding source of truth. It contains only
-- opaque, one-way HWID hashes; it does not contain serial numbers or raw
-- machine identifiers.
ALTER TABLE public.video_licenses
  ADD COLUMN IF NOT EXISTS device_hwids jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.video_licenses
  DROP CONSTRAINT IF EXISTS video_licenses_device_hwids_array;

ALTER TABLE public.video_licenses
  ADD CONSTRAINT video_licenses_device_hwids_array
  CHECK (jsonb_typeof(device_hwids) = 'array');

-- Move existing bindings into the array. Prefer v3 where it exists; otherwise
-- retain the legacy value so the same machine can prove and upgrade it once.
-- Dynamic SQL deliberately supports both the current schema and a database
-- where an earlier one-column migration was already completed.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'video_licenses' AND column_name = 'hwid_v3'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'video_licenses' AND column_name = 'hwid'
    ) THEN
        EXECUTE $copy$
            UPDATE public.video_licenses
               SET device_hwids = CASE
                    WHEN NULLIF(hwid_v3, '') IS NOT NULL THEN jsonb_build_array(hwid_v3)
                    WHEN NULLIF(hwid, '') IS NOT NULL THEN jsonb_build_array(hwid)
                    ELSE '[]'::jsonb
               END
             WHERE jsonb_array_length(device_hwids) = 0
        $copy$;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'video_licenses' AND column_name = 'hwid'
    ) THEN
        EXECUTE $copy$
            UPDATE public.video_licenses
               SET device_hwids = CASE
                    WHEN NULLIF(hwid, '') IS NOT NULL THEN jsonb_build_array(hwid)
                    ELSE '[]'::jsonb
               END
             WHERE jsonb_array_length(device_hwids) = 0
        $copy$;
    END IF;
END;
$$;
-- max_devices is now an actual server-enforced limit. Existing NULL or invalid
-- values become one; valid values such as 2 or 3 are retained.
UPDATE public.video_licenses
SET max_devices = 1
WHERE max_devices IS NULL OR max_devices < 1;

ALTER TABLE public.video_licenses
  ALTER COLUMN max_devices SET DEFAULT 1,
  ALTER COLUMN max_devices SET NOT NULL;

ALTER TABLE public.video_licenses
  DROP CONSTRAINT IF EXISTS video_licenses_max_devices_one,
  DROP CONSTRAINT IF EXISTS video_licenses_max_devices_positive;

ALTER TABLE public.video_licenses
  ADD CONSTRAINT video_licenses_max_devices_positive CHECK (max_devices >= 1);

-- Same public signature as the current application. FOR UPDATE makes the
-- count-and-append operation atomic, so parallel activations cannot exceed
-- max_devices.
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
    v_device_count integer;
    v_legacy_index integer;
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

    -- A device already on the list is always valid and consumes no new slot.
    IF v_license.device_hwids @> jsonb_build_array(p_hwid_v3) THEN
        RETURN json_build_object('valid', true, 'status', 'VALID', 'message', 'Bản quyền hợp lệ.', 'expired_at', v_license.expired_at);
    END IF;

    -- One-time safe migration: replace, rather than append, a matching old
    -- local HWID. This preserves its existing device slot.
    IF p_legacy_candidates IS NOT NULL THEN
        SELECT device.ordinality - 1
          INTO v_legacy_index
          FROM jsonb_array_elements_text(v_license.device_hwids) WITH ORDINALITY AS device(hwid, ordinality)
         WHERE device.hwid = ANY(p_legacy_candidates)
         LIMIT 1;

        IF FOUND THEN
            UPDATE public.video_licenses
               SET device_hwids = jsonb_set(
                   v_license.device_hwids,
                   ARRAY[v_legacy_index::text],
                   to_jsonb(p_hwid_v3),
                   false
               )
             WHERE id = v_license.id;
            RETURN json_build_object('valid', true, 'status', 'MIGRATED', 'message', 'Đã nâng cấp định danh thiết bị.', 'expired_at', v_license.expired_at);
        END IF;
    END IF;

    v_device_count := jsonb_array_length(v_license.device_hwids);
    IF v_device_count >= v_license.max_devices THEN
        RETURN json_build_object('valid', false, 'status', 'DEVICE_LIMIT_REACHED', 'message', 'Key đã đạt số lượng thiết bị tối đa.');
    END IF;

    UPDATE public.video_licenses
       SET device_hwids = v_license.device_hwids || jsonb_build_array(p_hwid_v3)
     WHERE id = v_license.id;

    RETURN json_build_object('valid', true, 'status', 'ACTIVATED', 'message', 'Kích hoạt thành công.', 'expired_at', v_license.expired_at);
END;
$$;

REVOKE ALL ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.activate_or_verify_video_license_v3(text, text, integer, text[], text) TO anon, authenticated;

-- Keep the table clean: legacy and implementation-specific one-device columns
-- are now represented by device_hwids.
ALTER TABLE public.video_licenses
  DROP COLUMN IF EXISTS hwid,
  DROP COLUMN IF EXISTS hwid_v3,
  DROP COLUMN IF EXISTS hwid_v3_version,
  DROP COLUMN IF EXISTS hwid_v3_migrated_at;

COMMENT ON COLUMN public.video_licenses.device_hwids IS
  'Canonical list of bound device HWID v3 hashes. Managed only by the license RPC.';
COMMENT ON COLUMN public.video_licenses.max_devices IS
  'Maximum number of distinct devices permitted for this license.';

COMMIT;
