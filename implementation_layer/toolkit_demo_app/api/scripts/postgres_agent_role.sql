-- A read-only role for the Postgres agent demo (api/routers/postgres_agent.py).
--
-- The model writes the agent's SQL, so it runs on a role that can only read the two
-- demo tables. Run this once as the database owner, after the API has started once
-- (the API creates and fills the demo schema on its first request):
--
--   psql "$DATABASE_URL" -f api/scripts/postgres_agent_role.sql
--
-- The script sets no password, so none reaches the server or its log. Set it
-- afterwards from psql, which sends only a SCRAM verifier, and keep it for the
-- connection string:
--
--   psql "$DATABASE_URL" -c '\password gaik_sql_agent'
--
-- Then set, on the API deployment only:
--
--   POSTGRES_AGENT_DATABASE_URL=postgresql://gaik_sql_agent:<password>@<host>:5432/<db>
--
-- Use no `options` (e.g. a role switch) in that URL: the agent's connection ignores
-- them, and the check refuses a connection whose role differs from its login.
--
-- The API checks the role before the agent answers, and again every ten minutes, and
-- refuses one that can write, create objects, has the replication attribute, is a
-- member of another role, can call a SECURITY DEFINER function or a function that reads
-- or lists server files, can read a relation besides the demo tables or a large
-- object, or when default privileges grant it future objects or an extension that
-- reaches other hosts or files is installed. GET /postgres-agent/status reports
-- own_read_only_role=true only when the last check passed.
--
-- What this role keeps by default, as every role does: it may create temporary tables
-- (PUBLIC has TEMP on the database), call ordinary functions PUBLIC may execute, and
-- connect to the cluster's other databases where PUBLIC keeps CONNECT; the check sees
-- only this database. default_transaction_read_only below is a default a session can
-- turn off; the agent also runs every query in a read-only transaction with a function
-- allow-list (gaik). On PostgreSQL 14 or older PUBLIC can also create in the public
-- schema; the check then refuses the role, and the owner decides whether to revoke that.
--
-- An existing role with this name keeps its password; its settings and grants below
-- are set again.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE gaik_sql_agent LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gaik_sql_agent') \gexec

ALTER ROLE gaik_sql_agent WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    NOREPLICATION;
ALTER ROLE gaik_sql_agent SET default_transaction_read_only = on;
ALTER ROLE gaik_sql_agent SET statement_timeout = '15s';

SELECT format('GRANT CONNECT ON DATABASE %I TO gaik_sql_agent', current_database()) \gexec
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM gaik_sql_agent;

-- Read the demo tables, nothing else.
GRANT USAGE ON SCHEMA gaik_postgres_agent_demo TO gaik_sql_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA gaik_postgres_agent_demo FROM gaik_sql_agent;
GRANT SELECT ON gaik_postgres_agent_demo.customers, gaik_postgres_agent_demo.orders
    TO gaik_sql_agent;
