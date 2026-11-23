# Sourced by the Software Collections image on every start, after it has created the owner role and the
# database (its postgresql-init hooks run before that, so they cannot be used). Idempotent: roles are
# created once and their passwords kept in step with the Secret; the collection schema is created once,
# by the owner role, as in the compose stack.
psql -v ON_ERROR_STOP=1 \
  -v writer="${COLLECTION_WRITER_PASSWORD}" -v reader="${COLLECTION_READER_PASSWORD}" -v mlflow="${MLFLOW_DB_PASSWORD}" <<'SQL'
SELECT 'CREATE ROLE collection_writer LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'collection_writer') \gexec
SELECT 'CREATE ROLE collection_reader LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'collection_reader') \gexec
SELECT 'CREATE ROLE mlflow LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mlflow') \gexec
ALTER ROLE collection_writer PASSWORD :'writer';
ALTER ROLE collection_reader PASSWORD :'reader';
ALTER ROLE mlflow PASSWORD :'mlflow';
SELECT 'CREATE DATABASE mlflow OWNER mlflow' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow') \gexec
SQL
if [ "$(psql -tA -d "${POSTGRESQL_DATABASE}" -c "SELECT to_regclass('collection.audit_events') IS NULL")" = "t" ]; then
  psql -v ON_ERROR_STOP=1 -d "${POSTGRESQL_DATABASE}" -c "SET ROLE \"${POSTGRESQL_USER}\"" -f /sql/001_schema.sql
fi
