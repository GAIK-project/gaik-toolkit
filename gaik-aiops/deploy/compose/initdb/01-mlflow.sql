-- MLflow tracking store, a separate database on the same server (local development only).
-- Real deployments create the role with a password from the secrets store.
CREATE ROLE mlflow LOGIN PASSWORD 'mlflow-local-only';
CREATE DATABASE mlflow OWNER mlflow;
