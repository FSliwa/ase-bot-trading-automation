# Database Migrations

This directory contains SQL migrations that can be applied to keep the database schema in sync with the backend services.

## Applying migrations

Run each SQL script sequentially using your preferred database client. For example, with `psql`:

```
psql "$DATABASE_URL" -f 20241012001_create_api_keys_table.sql
```

Ensure the `users` table exists before applying the API key migration.
