#!/bin/sh
# Runs once on first Postgres init, after 001_init.sql. Sets LOGIN + PASSWORD for the app roles.
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v proxy_password="$PROXY_DB_PASSWORD" -v reader_password="$READER_DB_PASSWORD" \
  -f /sql/002_roles_login.sql
