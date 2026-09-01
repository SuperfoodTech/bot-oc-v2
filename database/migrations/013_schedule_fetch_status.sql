ALTER TABLE outlet_states
    ADD COLUMN IF NOT EXISTS schedule_fetch_status varchar(32);

ALTER TABLE outlet_states
    ADD COLUMN IF NOT EXISTS schedule_fetch_attempted_at timestamptz;

ALTER TABLE outlet_states
    ADD COLUMN IF NOT EXISTS schedule_fetch_succeeded_at timestamptz;

ALTER TABLE outlet_states
    ADD COLUMN IF NOT EXISTS schedule_fetch_error text;

UPDATE outlet_states
   SET schedule_fetch_status = CASE
       WHEN EXISTS (
           SELECT 1
             FROM jsonb_each(COALESCE(shopee_regular_hours, '{}'::jsonb)) AS day(name, intervals)
            WHERE jsonb_typeof(intervals) = 'array'
              AND jsonb_array_length(intervals) > 0
       ) THEN 'READY'
       ELSE 'NOT_FETCHED_YET'
   END
 WHERE schedule_fetch_status IS NULL
    OR BTRIM(schedule_fetch_status) = ''
    OR schedule_fetch_status NOT IN ('NOT_FETCHED_YET', 'FETCH_RETRYING', 'FETCHED_EMPTY', 'READY');

UPDATE outlet_states
   SET schedule_fetch_attempted_at = COALESCE(schedule_fetch_attempted_at, last_checked_at),
       schedule_fetch_succeeded_at = COALESCE(schedule_fetch_succeeded_at, last_checked_at)
 WHERE schedule_fetch_status = 'READY'
   AND last_checked_at IS NOT NULL;

ALTER TABLE outlet_states
    ALTER COLUMN schedule_fetch_status SET DEFAULT 'NOT_FETCHED_YET';

UPDATE outlet_states
   SET schedule_fetch_status = 'NOT_FETCHED_YET'
 WHERE schedule_fetch_status IS NULL;

ALTER TABLE outlet_states
    ALTER COLUMN schedule_fetch_status SET NOT NULL;

ALTER TABLE outlet_states
    DROP CONSTRAINT IF EXISTS outlet_states_schedule_fetch_status_check;

ALTER TABLE outlet_states
    ADD CONSTRAINT outlet_states_schedule_fetch_status_check
    CHECK (schedule_fetch_status IN ('NOT_FETCHED_YET', 'FETCH_RETRYING', 'FETCHED_EMPTY', 'READY'));

INSERT INTO schema_migrations (version) VALUES ('013_schedule_fetch_status')
ON CONFLICT (version) DO NOTHING;
