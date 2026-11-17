-- A read-only role for the Postgres agent demo (api/routers/postgres_agent.py).
--
-- The model writes the agent's SQL, so it runs on a role that can only read the two
-- demo tables. Run this once as the database owner, after the API has started once
-- (the API creates and fills the demo schema on its first request):
--
--   psql "$DATABASE_URL" -v agent_password="$(openssl rand -hex 24)" \
--        -f api/scripts/postgres_agent_role.sql
--
-- Then set, on the API deployment only:
--
--   POSTGRES_AGENT_DATABASE_URL=postgresql://gaik_sql_agent:<password>@<host>:5432/<db>
--
-- The API checks the role before the agent answers and refuses one that can write,
-- create objects or read a table outside the demo schema (see /postgres-agent/status).

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE gaik_sql_agent LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gaik_sql_agent') \gexec

ALTER ROLE gaik_sql_agent WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    PASSWORD :'agent_password';
ALTER ROLE gaik_sql_agent SET default_transaction_read_only = on;
ALTER ROLE gaik_sql_agent SET statement_timeout = '15s';

-- No objects of its own anywhere (PostgreSQL 15 and later already keep PUBLIC out of
-- creating in the public schema; this makes older servers do the same).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM gaik_sql_agent;
SELECT format('GRANT CONNECT ON DATABASE %I TO gaik_sql_agent', current_database()) \gexec

-- Read the demo tables, nothing else.
GRANT USAGE ON SCHEMA gaik_postgres_agent_demo TO gaik_sql_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA gaik_postgres_agent_demo FROM gaik_sql_agent;
GRANT SELECT ON gaik_postgres_agent_demo.customers, gaik_postgres_agent_demo.orders
    TO gaik_sql_agent;
