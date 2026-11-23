-- Local development roles only. Real deployments create these roles with
-- passwords from the secrets store.
CREATE ROLE collection_writer LOGIN PASSWORD 'writer-local-only';
CREATE ROLE collection_reader LOGIN PASSWORD 'reader-local-only';
