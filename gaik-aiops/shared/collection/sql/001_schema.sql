-- Collection, storage and correlation layer: schema v0.
-- Expects the roles collection_writer and collection_reader to exist
-- (created by the deployment, see deploy/compose/initdb/).

CREATE SCHEMA IF NOT EXISTS collection;

-- Security audit trail (WP4 S4). Append-only: rows can be removed only after
-- their retention period has passed, and never changed.
CREATE TABLE IF NOT EXISTS collection.audit_events (
    id               bigserial PRIMARY KEY,
    event_time       timestamptz NOT NULL,
    received_at      timestamptz NOT NULL DEFAULT now(),
    trace_id         text,
    span_id          text,
    service_name     text NOT NULL,
    event_name       text NOT NULL,
    outcome          text,
    actor_pseudo_id  text,
    client_address   text,
    resource_type    text,
    resource_id      text,
    attributes       jsonb NOT NULL DEFAULT '{}'::jsonb,
    retention_until  timestamptz NOT NULL
);

-- Operational logs and any other event class (WP5 central logging).
CREATE TABLE IF NOT EXISTS collection.log_events (
    id               bigserial PRIMARY KEY,
    event_time       timestamptz NOT NULL,
    received_at      timestamptz NOT NULL DEFAULT now(),
    trace_id         text,
    span_id          text,
    service_name     text NOT NULL,
    event_class      text NOT NULL,
    event_name       text,
    severity         text,
    body             jsonb,
    attributes       jsonb NOT NULL DEFAULT '{}'::jsonb,
    resource         jsonb NOT NULL DEFAULT '{}'::jsonb,
    retention_until  timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_events_trace_idx ON collection.audit_events (trace_id);
CREATE INDEX IF NOT EXISTS audit_events_time_idx ON collection.audit_events (event_time);
CREATE INDEX IF NOT EXISTS audit_events_retention_idx ON collection.audit_events (retention_until);
CREATE INDEX IF NOT EXISTS log_events_trace_idx ON collection.log_events (trace_id);
CREATE INDEX IF NOT EXISTS log_events_time_idx ON collection.log_events (event_time);
CREATE INDEX IF NOT EXISTS log_events_retention_idx ON collection.log_events (retention_until);

CREATE OR REPLACE FUNCTION collection.audit_events_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'audit events are immutable';
    END IF;
    IF OLD.retention_until > now() THEN
        RAISE EXCEPTION 'audit event % is still within its retention period', OLD.id;
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS audit_events_guard ON collection.audit_events;
CREATE TRIGGER audit_events_guard
    BEFORE UPDATE OR DELETE ON collection.audit_events
    FOR EACH ROW EXECUTE FUNCTION collection.audit_events_guard();

DROP TRIGGER IF EXISTS audit_events_no_truncate ON collection.audit_events;
CREATE OR REPLACE FUNCTION collection.audit_events_no_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit events cannot be truncated';
END;
$$;
CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON collection.audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION collection.audit_events_no_truncate();

-- Removes expired rows from both tables. Run on a schedule by the schema owner.
CREATE OR REPLACE FUNCTION collection.purge_expired() RETURNS TABLE (audit_deleted bigint, logs_deleted bigint)
LANGUAGE plpgsql AS $$
DECLARE
    a bigint;
    l bigint;
BEGIN
    DELETE FROM collection.audit_events WHERE retention_until <= now();
    GET DIAGNOSTICS a = ROW_COUNT;
    DELETE FROM collection.log_events WHERE retention_until <= now();
    GET DIAGNOSTICS l = ROW_COUNT;
    RETURN QUERY SELECT a, l;
END;
$$;

-- One timeline per trace across both stores.
CREATE OR REPLACE VIEW collection.correlated_events AS
    SELECT trace_id, event_time, 'audit'::text AS event_class, service_name, event_name,
           outcome AS detail, attributes
      FROM collection.audit_events
    UNION ALL
    SELECT trace_id, event_time, event_class, service_name, event_name,
           severity AS detail, attributes
      FROM collection.log_events;

REVOKE ALL ON ALL TABLES IN SCHEMA collection FROM PUBLIC;
REVOKE ALL ON FUNCTION collection.purge_expired() FROM PUBLIC;
GRANT USAGE ON SCHEMA collection TO collection_writer, collection_reader;
GRANT INSERT ON collection.audit_events, collection.log_events TO collection_writer;
GRANT USAGE ON SEQUENCE collection.audit_events_id_seq, collection.log_events_id_seq TO collection_writer;
GRANT SELECT ON collection.audit_events, collection.log_events, collection.correlated_events TO collection_reader;
