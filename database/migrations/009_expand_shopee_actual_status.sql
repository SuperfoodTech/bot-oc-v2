ALTER TABLE outlet_states DROP CONSTRAINT IF EXISTS outlet_states_shopee_actual_status_check;

UPDATE outlet_states
   SET shopee_actual_status = 'ON'
 WHERE shopee_actual_status = 'OPEN';

UPDATE outlet_states
   SET shopee_actual_status = 'CLOSED'
 WHERE shopee_actual_status IN ('OFF', 'CLOSE');

ALTER TABLE outlet_states
    ADD CONSTRAINT outlet_states_shopee_actual_status_check
    CHECK (shopee_actual_status IN ('ON', 'PAUSE', 'CLOSED', 'UNKNOWN'));
