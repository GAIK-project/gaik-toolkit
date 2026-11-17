-- A read-only role for the Postgres agent demo (api/routers/postgres_agent.py).
--
-- The model writes the agent's SQL, so it runs on a role that can only read the two
-- demo tables. Run this once as the database owner, after the API has started once
-- (the API creates and fills the demo schema on its first request). Keep the password
-- you generate: it goes into the agent's connection string.
--
--   AGENT_PASSWORD="$(openssl rand -hex 24)"
--   PGOPTIONS='-c log_statement=none' psql "$DATABASE_URL" \
--        -v agent_password="$AGENT_PASSWORD" -f api/scripts/postgres_agent_role.sql
--
-- (PGOPTIONS keeps the ALTER ROLE ... PASSWORD statement out of the server log if
-- statement logging is on; the password is briefly visible in the local process list.)
-- Then set, on the API deployment only:
--
--   POSTGRES_AGENT_DATABASE_URL=postgresql://gaik_sql_agent:$AGENT_PASSWORD@<host>:5432/<db>
--
-- The API checks the role before the agent answers and refuses one that can write,
-- create objects, is a member of another role, can call a SECURITY DEFINER function or
-- can read a relation outside the demo schema. GET /postgres-agent/status reports
-- own_read_only_role=true only when the role passed. After fixing a refused role,
-- restart the API.
--
-- What this role keeps by default, as every role does: it may create temporary tables
-- (PUBLIC has TEMP on the database) and call ordinary functions PUBLIC may execute.
-- default_transaction_read_only below is a default a session can turn off; the agent
-- also runs every query in a read-only transaction with a function allow-list (gaik).
-- On PostgreSQL 14 or older PUBLIC can also create in the public schema; the check
-- then refuses the role, and the owner decides whether to revoke that from PUBLIC.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE gaik_sql_agent LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gaik_sql_agent') \gexec

ALTER ROLE gaik_sql_agent WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    PASSWORD :'agent_password';
ALTER ROLE gaik_sql_agent SET default_transaction_read_only = on;
ALTER ROLE gaik_sql_agent SET statement_timeout = '15s';

SELECT format('GRANT CONNECT ON DATABASE %I TO gaik_sql_agent', current_database()) \gexec
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM gaik_sql_agent;

-- Read the demo tables, nothing else.
GRANT USAGE ON SCHEMA gaik_postgres_agent_demo TO gaik_sql_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA gaik_postgres_agent_demo FROM gaik_sql_agent;
GRANT SELECT ON gaik_postgres_agent_demo.customers, gaik_postgres_agent_demo.orders
    TO gaik_sql_agent;
