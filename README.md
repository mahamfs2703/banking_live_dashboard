# banking-dashboard

Streamlit in Snowflake dashboard for a near-real-time banking pipeline. It reads only from the `MARTS` schema and shows current KPIs, trends and recent activity in IST.

Part of a three-repo project:

| Repo | Purpose |
| --- | --- |
| https://github.com/mahamfs2703/banking_generator | Simulated source activity |
| https://github.com/mahamfs2703/banking-dbt | Transformations that produce the marts |
| **banking-dashboard** (this repo) | The dashboard |

## What it shows

- **Header**: title, pipeline subtitle, and a "Last synced" pill (green within 7 hours of the last sync, amber up to 13, red beyond).
- **KPI cards**: transactions, completed value, success rate, average ticket size. If there are no transactions today (IST), the cards fall back to the latest day with data and say so. Each card shows the change against the previous day with data.
- **Transactions per minute**: last 60 minutes up to the newest data, with empty minutes filled as zero.
- **Failed rate by hour**: last 24 IST-aligned hours. Hours with no transactions are left empty rather than shown as 0%.
- **Top 5 merchants** by completed value.
- **Recent transactions**: latest 20, with colored status.
- Manual **Refresh** button and a 60-second query cache. No auto-refresh.

All queries exclude soft-deleted rows (`is_deleted`). All times are converted to `Asia/Kolkata`.

## Data it reads

From `DB_BANKING.MARTS`: `FCT_TRANSACTIONS`, `DIM_MERCHANT`, `AGG_TXN_VOLUME_PER_MINUTE`, `AGG_TOP_MERCHANTS`.

## Snowflake setup

| Object | Name |
| --- | --- |
| App | `DB_BANKING.APP.BANKING_DASHBOARD` |
| Role (read-only on `MARTS`) | `BANKING_APP_ROLE` |
| Query warehouse | `DBT_PRACTICE_WH` (XS, 60 s auto-suspend) |
| Compute pool (container runtime) | `BANKING_APP_POOL` (`CPU_X64_XS`, 1 node, 60 s auto-suspend) |

Run as `ACCOUNTADMIN`:

```sql
CREATE ROLE IF NOT EXISTS BANKING_APP_ROLE;
CREATE SCHEMA IF NOT EXISTS DB_BANKING.APP;

CREATE COMPUTE POOL IF NOT EXISTS BANKING_APP_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_SUSPEND_SECS = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

GRANT USAGE ON DATABASE DB_BANKING TO ROLE BANKING_APP_ROLE;
GRANT USAGE ON SCHEMA DB_BANKING.MARTS TO ROLE BANKING_APP_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA DB_BANKING.MARTS TO ROLE BANKING_APP_ROLE;
GRANT SELECT ON ALL VIEWS IN SCHEMA DB_BANKING.MARTS TO ROLE BANKING_APP_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DB_BANKING.MARTS TO ROLE BANKING_APP_ROLE;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA DB_BANKING.MARTS TO ROLE BANKING_APP_ROLE;

GRANT USAGE, CREATE STREAMLIT ON SCHEMA DB_BANKING.APP TO ROLE BANKING_APP_ROLE;
GRANT USAGE ON WAREHOUSE DBT_PRACTICE_WH TO ROLE BANKING_APP_ROLE;
GRANT USAGE ON COMPUTE POOL BANKING_APP_POOL TO ROLE BANKING_APP_ROLE;

SET me = CURRENT_USER();
GRANT ROLE BANKING_APP_ROLE TO USER IDENTIFIER($me);
```

`FUTURE` grants matter because dbt can rebuild tables, which would otherwise drop their grants.

## Files

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | The app |
| `snowflake.yml` | App definition: main file, query warehouse, compute pool |
| `pyproject.toml` | Python dependencies (`streamlit[snowflake]`) |
| `.streamlit/config.toml` | Theme |

`snowflake.yml`:

```yaml
definition_version: 2
entities:
  streamlit_app:
    type: streamlit
    main_file: streamlit_app.py
    title: "Banking Live Dashboard"
    query_warehouse: "DBT_PRACTICE_WH"
    compute_pool: "BANKING_APP_POOL"
    artifacts:
      - pyproject.toml
      - streamlit_app.py
      - .streamlit/config.toml
```

## Deploy

1. In Snowsight, open **Workspaces** and add this folder as a Streamlit app (or connect the repo via a Git-backed workspace).
2. Switch to `BANKING_APP_ROLE`. The deploying role owns the app.
3. Deploy with database `DB_BANKING`, schema `APP`, warehouse `DBT_PRACTICE_WH`, compute pool `BANKING_APP_POOL`, app name `BANKING_DASHBOARD`.
4. Open it from **Projects > Streamlit**.

## Theme

| Role | Color |
| --- | --- |
| Background | `#0A1F33` |
| Panels | `#12304A` |
| Text | `#E8EEF4` |
| Accent | `#14B8A6` (teal) |
| COMPLETED / PENDING / FAILED / REVERSED | `#2FB36D` / `#E5A93B` / `#E05252` / `#8B84D6` |

Cards use a small custom CSS block injected with `st.markdown`. It works on Streamlit 1.66.0 in this runtime.

## Operating notes

- The app runs on a compute pool, which bills while it is running. Suspend it when you are done:

```sql
ALTER COMPUTE POOL BANKING_APP_POOL SUSPEND;
```

- Fresh data appears only after the full chain has run: generator, replication connector, dbt task. Click **Refresh** to bypass the 60-second cache.
