-- PostgreSQL initialisation script
-- Runs once when the postgres container is first created.
-- The main 'forge' database is created automatically by POSTGRES_DB env var.

-- Create the MLflow tracking database
CREATE DATABASE forge_mlflow
    WITH OWNER forge
    ENCODING 'UTF8'
    LC_COLLATE 'en_US.utf8'
    LC_CTYPE 'en_US.utf8';

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE forge TO forge;
GRANT ALL PRIVILEGES ON DATABASE forge_mlflow TO forge;

-- Enable useful extensions on the main database
\c forge

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
