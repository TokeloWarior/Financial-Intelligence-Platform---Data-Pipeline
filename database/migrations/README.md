# Database Migrations

This project uses Alembic to manage PostgreSQL schema changes.

Alembic is now the source of truth for database structure.  
Do not edit or rerun old reset SQL scripts when adding schemas, tables, columns, indexes, or constraints.

---

## Database Layering

The database is organised into the following PostgreSQL schemas:

- `raw` - source data exactly as ingested
- `clean` - validated and standardised operational data
- `gold` - analytics-ready business outputs
- `ml` - model inputs, features, predictions, and explanations
- `fip` - Financial Intelligence Platform application tables
- `ops` - ingestion logs, rejected records, data quality results, and audit data

---

## One-Time Fresh Reset

Use this only when intentionally starting from a clean local database.

This removes Docker volumes and wipes all local database data.


Normal Development Workflow
---------------------------

### 1\. Start the database

`docker compose up -d postgres`

### 2\. Apply all pending migrations

`alembic upgrade head`

### 3\. Check current migration version

`alembic current`

### 4\. View migration history

`alembic history`

Adding a New Table, Schema, Column, or Index
--------------------------------------------

Create a new migration:

`alembic revision -m "describe change here"`

Then edit the generated file inside:

`database/migrations/versions/`

Apply it:

`alembic upgrade head`

Rolling Back One Migration
--------------------------

`alembic downgrade -1`

Rolling Back to Base
--------------------

Use carefully. This drops all objects managed by migrations.

`alembic downgrade base`

Important Rules
---------------

*   Do not use DROP SCHEMA ... CASCADE in normal migrations unless intentionally removing a full schema.
    
*   Do not modify already-applied migration files.
    
*   Always create a new migration for new changes.
    
*   Keep migrations small and focused.
    
*   The raw, clean, gold, ml, fip, and ops schemas should be created only by Alembic.
    
*   Old SQL files are legacy references only.
    
*   Pipeline code should assume migrations have already been applied.
    
*   FIP should read from gold, ml, and fip tables, not directly from raw.
    

Recommended Commands
--------------------

### Fresh local setup

- `docker compose down -v`
- `docker compose up -d postgres`
- `alembic upgrade head`

### Daily development

- `docker compose up -d postgres`
- `alembic upgrade head`

### Add a migration

`alembic revision -m "add new database change"`

### Apply migration

`alembic upgrade head`

### Rollback last migration

`alembic downgrade -1`