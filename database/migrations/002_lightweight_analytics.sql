-- Deprecated: the current PostgreSQL schema is initialized from database/schema.sql.
-- Kept only so old project references do not break. Safe to execute.

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
