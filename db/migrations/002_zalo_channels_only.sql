-- Navigator only publishes Zalo-native destinations.  Evidence retained in
-- source JSON is not imported as a searchable website record.
DELETE FROM services WHERE service_type = 'website';

ALTER TABLE services
    DROP CONSTRAINT IF EXISTS services_active_zalo_channel_check;
ALTER TABLE services
    ADD CONSTRAINT services_active_zalo_channel_check
    CHECK (NOT active OR service_type IN ('oa', 'mini_app'));
