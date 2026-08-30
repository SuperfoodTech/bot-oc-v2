-- Shopee regular-hours API uses 1=Sunday through 7=Saturday. Earlier builds
-- incorrectly stored that response as 1=Monday through 7=Sunday. Rotate the
-- persisted JSON keys once so existing schedules match the corrected parser.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations
        WHERE version = '010_fix_shopee_weekday_mapping'
    ) THEN
        UPDATE outlet_states
        SET shopee_regular_hours = jsonb_build_object(
            'Senin',  COALESCE(shopee_regular_hours->'Selasa',  '[]'::jsonb),
            'Selasa', COALESCE(shopee_regular_hours->'Rabu',    '[]'::jsonb),
            'Rabu',   COALESCE(shopee_regular_hours->'Kamis',   '[]'::jsonb),
            'Kamis',  COALESCE(shopee_regular_hours->'Jumat',   '[]'::jsonb),
            'Jumat',  COALESCE(shopee_regular_hours->'Sabtu',   '[]'::jsonb),
            'Sabtu',  COALESCE(shopee_regular_hours->'Minggu',  '[]'::jsonb),
            'Minggu', COALESCE(shopee_regular_hours->'Senin',   '[]'::jsonb)
        )
        WHERE shopee_regular_hours IS NOT NULL;

        INSERT INTO schema_migrations (version)
        VALUES ('010_fix_shopee_weekday_mapping');
    END IF;
END $$;
