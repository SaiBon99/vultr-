-- Sets LOGIN + PASSWORD on the app roles. Run with psql -v proxy_password=... -v reader_password=...
-- Idempotent. apply_sql.py does the same through psycopg for Vultr Managed PG.
ALTER ROLE quarantine_proxy LOGIN PASSWORD :'proxy_password';
ALTER ROLE memory_reader LOGIN PASSWORD :'reader_password';
