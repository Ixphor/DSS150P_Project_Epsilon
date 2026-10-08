# CFPB Complaint Resolution Data Engineering Pipeline

**Group Epsilon** | DSS150P - Fundamentals of Data Engineering | Mapúa University

---

## Project Overview

A reproducible, automated data engineering pipeline that ingests, validates, integrates, and curates CFPB consumer complaint data (~18 million records) and enriches it with FDIC institution financials and U.S. Census demographics. It follows the Medallion architecture (Raw → Staging → Curated), runs on PostgreSQL, is orchestrated by Apache Airflow, and is fully containerized with Docker Compose.

---

## Problem Statement

Consumers file millions of complaints about financial products with the CFPB, but the raw database cannot answer the questions regulators, analysts, and journalists actually ask:

* Where and when are complaints rising, and in which products?
* Do complaints track state-level demographics such as poverty and income?
* Which banks draw the most complaints relative to their size, and do large banks respond more slowly than small ones?

The raw data cannot answer these on its own. Complaints name a company, not a bank record. They carry a state code, not demographic context. They contain anomalies (for example, 7,050 complaints sent to the company before they were received) and arrive daily through an API that caps results per query. Answering these questions requires integrating three independent sources.

### Stakeholders

| Stakeholder | What they need? |
| --- | --- |
| **Regulators and Policy Analysts** | Trends by state, product, and bank size; response-time performance |
| **Data Analysts and BI Developers** | A clean star schema and marts they can query without cleaning anything |
| **Data Scientists** | Analysis-ready, typed, partitioned Parquet files |
| **Course Instructors and Reviewers** | A reproducible, documented, rerunnable pipeline with visible quality controls |

---

## Team Members & Roles

| Name | Role / Pipeline Stage Owned |
| --- | --- |
| **Ashley Galit** | FDIC Code Compiler (extract, ingest, validate, transform) |
| **Derek Tyler Ong** | Census & Curated Code Compiler (extract, ingest, validate, transform) |
| **Thazel Tumaneng** | CFPB Code Compiler (extract, ingest, validate, transform) |

---

## Data Source Inventory

| Source | Provider | Access Method | Format | Volume | Refresh | Primary Key | Authentication |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **CFPB Consumer Complaints Bulk** | Consumer Financial Protection Bureau | Automated download of `complaints.csv.zip` | CSV | ~18.2M rows | One-time bootstrap | `complaint_id` | None |
| **CFPB Consumer Complaints (API)** | Consumer Financial Protection Bureau | Paginated Search API | JSON | Daily increments | Daily (watermark minus 14-day lookback) | `complaint_id` | None |
| **FDIC BankFind Institutions** | Federal Deposit Insurance Corporation | REST API, filter `ACTIVE:1`, 1,000 per page | JSON (plus Parquet copy) | ~4,200 institutions, 150 source columns | Each DAG run | `cert` | None |
| **Census ACS 5-year (2022)** | U.S. Census Bureau | REST API, `for=state:*` | JSON (list of lists) | 52 rows (50 states, DC, Puerto Rico) | Each DAG run | `state_fips` | Optional key |

### Census Variables Extracted

| Variable | Meaning |
| --- | --- |
| `B01003_001E` | Total population |
| `B19013_001E` | Median household income |
| `B17001_002E` | Population below the poverty line |
| `B02001_002E` | White alone |
| `B02001_003E` | Black or African American alone |

---

## Architecture

### ERD
See `docs/erd.md`.

#### Table Reference

| Table | Grain | Source | Notes |
| --- | --- | --- | --- |
| `curated.fact_complaints` | One row per complaint | CFPB staging | Primary key `complaint_id`; foreign keys to all five dimensions; indexed on date, year/month, state, company, institution |
| `curated.dim_company` | One row per company name | CFPB staging | Identity surrogate key; `company_key` is the normalized name used for matching |
| `curated.dim_product` | Product x sub-product | CFPB staging | |
| `curated.dim_issue` | Issue x sub-issue | CFPB staging | |
| `curated.dim_geography` | One row per state or territory | Census | Joined on state abbreviation through a FIPS reference table |
| `curated.dim_institution` | One row per active FDIC institution | FDIC | Includes `asset_tier` |
| `curated.bridge_company_institution` | One row per matched company | Derived | Links CFPB company to FDIC institution |

### Medallion Architecture

| Layer | Schema / Folder | Purpose | Allowed Operations | Not Allowed |
| --- | --- | --- | --- | --- |
| **Files** | `data/raw/` | Permanent, replayable copy of every extract | Save API responses and downloads untouched, with ingestion metadata | Any transformation |
| **Raw** | `raw` | Source data as received, plus lineage | Typed load, primary keys, `ingested_at`, `source_system`, `batch_id` | Cleaning, joins |
| **Staging** | `staging` | Filtered, cleaned, validated | Trim, standardize, derive fields, quarantine invalid rows | Joins across sources |
| **Curated** | `curated` | Integrated single source of truth | Cross-source joins, surrogate keys, constraints, marts | Source-specific cleaning |

### Key Design Decisions

| Decision | Explanation |
| --- | --- |
| **Files before database** | Every extract is saved to `data/raw/` first, so any load can be replayed without calling the source again. |
| **Quarantine, never silently drop** | Invalid CFPB rows go to `staging.complaints_rejected` with a reject reason. The runner checks that `staged + rejected = raw`. |
| **Validation gates raise exceptions** | A failed check raises `ValidationError`, which fails the Airflow task and blocks all downstream tasks. |
| **Atomic rebuilds** | Staging and curated SQL run as one transaction, so readers never see a half-built table and a failure leaves the previous version in place. |
| **Docker Compose for parity** | One `docker compose up` gives every teammate the same PostgreSQL, Airflow, and Python environment. |
| **Bridge table for FDIC** | A CFPB company name does not map one-to-one to an FDIC institution, so matching is explicit, ranked, and auditable. |
| **Incremental after bootstrap** | The full CSV is loaded once. Daily runs pull only new complaints through the API and upsert them. |

---

## Repository Structure

```
DSS150P_Project_Epsilon/
├── README.md
├── requirements.txt
├── Dockerfile                        # Airflow 2.7.1 / Python 3.10 + project dependencies
├── docker-compose.yml                # postgres, airflow-init, webserver, scheduler
├── .env.example                      # copy to .env (never commit .env)
├── .gitignore
├── config/                           # mounted into Airflow containers
├── dags/
│   └── medallion_architecture_pipeline.py
├── data/
│   ├── raw/                          # untouched extracts (git-ignored)
│   │   ├── complaints.csv
│   │   ├── cfpb_api/
│   │   ├── fdic/
│   │   └── census/
│   ├── staging/                      # staging reference Parquet (git-ignored)
│   └── curated/                      # partitioned Parquet and mart files (git-ignored)
├── logs/                             # Airflow task logs (git-ignored)
├── notebooks/                        # source profiling scripts
│   ├── profile_cfpb.py
│   ├── profile_fdic.py
│   └── profile_census.py
├── outputs/
│   ├── cfpb_profiling/
│   ├── fdic_profiling/
│   ├── census_profiling/
│   ├── validation/                   # CSV report per validation gate
│   └── format_comparison/            # format benchmark and partition demo
├── sql/
│   ├── init/01_init_schema.sql       # database, schemas, raw tables (first start only)
│   ├── reference/state_fips_seed.sql # state abbreviation <-> FIPS map
│   ├── staging/                      # 00_functions, stage_cfpb, stage_fdic, stage_census
│   ├── curated/                      # build_curated.sql, build_mart.sql
│   └── queries/representative_queries.sql
├── src/
│   ├── extract/                      # extract_cfpb_bulk, extract_cfpb_api, extract_fdic, extract_census
│   ├── load/                         # load_cfpb, load_cfpb_api, load_fdic, load_census, cfpb_common
│   ├── transform/                    # stage, build_curated, build_mart
│   ├── validation/                   # common + validate_cfpb/fdic/census/curated/mart
│   ├── export/                       # export_curated, benchmark_formats, read_partition_demo
│   └── utils/                        # config, db, http, logging_config
└── tests/                            # pytest suite
```

## Installation and Prerequisites

Requirements
- Docker / Docker Compose
- Python 3.11+

Dependencies (requirements.txt)
- pandas==2.3.3
- requests==2.34.2
- psycopg2-binary==2.9.13
- python-dotenv==1.2.3
- pyarrow==25.0.1
- pytest==9.1.1
- curl_cffi
- ijson
- scipy
- statsmodels
- matplotlib
- plotly

## Configuration
Copy .env.example to .env and fill in local values. Never commit .env.

## Running the pipeline
```
# 1. Build the image and start PostgreSQL, Airflow init, webserver, scheduler
docker compose up -d --build

# 2. Check that all services are healthy
docker compose ps

# 3. Open the Airflow UI: http://localhost:8080 (username/password from .env)
```
1. In the Airflow UI, find the DAG medallion_architecture_pipeline and unpause it.
2. Click Trigger DAG w/ config to start a run now (or wait for the @daily schedule).
3. Watch the task graph. The first run downloads and loads the full CFPB CSV (about 18 million rows), so it takes a long time. Later runs are incremental and fast.

Useful Commands
```
docker compose logs -f airflow-scheduler      # follow the scheduler
docker compose down                           # stop (data volume is kept)
docker compose down -v                        # stop AND delete the database volume (full reset)
```

Manual CLI Execution Steps
```
docker compose up -d postgres

# ---------- CFPB ----------
# Download complaints.csv (skipped if it exists; --force to re-download)
python -m src.extract.extract_cfpb_bulk

# Bulk load (skipped if the table already has rows; --force to reload, --min-date YYYY-MM-DD for a demo slice)
python -m src.load.load_cfpb

# Incremental pull (also: --since, --until, --probe)
python -m src.extract.extract_cfpb_api --lookback-days 14
python -m src.load.load_cfpb_api                   # upsert on complaint_id
python -m src.validation.validate_cfpb             # gate
python -m src.transform.stage cfpb                 # raw -> staging (+ quarantine)

# ---------- FDIC ----------
python -m src.extract.extract_fdic
python -m src.load.load_fdic
python -m src.validation.validate_fdic             # gate
python -m src.transform.stage fdic

# ---------- Census ----------
python -m src.extract.extract_census
python -m src.load.load_census
python -m src.validation.validate_census           # gate
python -m src.transform.stage census

# ---------- Curated and Data Products ----------
python -m src.transform.build_curated              # star schema (takes several minutes on 18M rows)
python -m src.validation.validate_curated          # gate
python -m src.transform.build_mart                 # view + two marts
python -m src.validation.validate_mart             # gate

# ---------- File Layer ----------
python -m src.export.export_curated                # add --since-year 2026 to refresh only recent partitions
python -m src.export.benchmark_formats --rows 200000
python -m src.export.read_partition_demo           # add --year 2026 --month 8 for a specific partition

# ---------- Query the Results ----------
docker compose exec postgres psql -U airflow -d cfpb_pipeline -f /dev/stdin < sql/queries/representative_queries.sql

# ---------- Source Profiling ----------
python -m notebooks.profile_cfpb      # needs raw CFPB data loaded in PostgreSQL
python -m notebooks.profile_fdic      # uses the latest raw file, or fetches one
python -m notebooks.profile_census    # needs one raw Census file from extract_census
```
## Data Quality and Validation

Validation runs automatically after every major stage. Each validator builds a list of checks, writes a CSV report, and calls `enforce()`, which raises `ValidationError` if any check fails. That fails the Airflow task and stops everything downstream.

| Status | Meaning |
| --- | --- |
| **PASS** | No failed rows |
| **WARN** | Failures are within tolerance (default 1.0%), or the rule is warning-only |
| **FAIL** | An error-level rule exceeds its tolerance. The pipeline stops. |

---

### Validation Gates and Latest Results

*Results from the latest recorded run (October 2026). Exact counts change as new complaints arrive.*

| Gate | Script | Checks and Result | What it Covers |
| --- | --- | --- | --- |
| **CFPB (raw)** | `validate_cfpb.py` | 8 checks: 6 PASS, 2 WARN | Table not empty, duplicate IDs, null core fields, invalid timely enum, missing or negative SLA lag, future dates, ZIP format, freshness within 14 days |
| **FDIC (raw JSON)** | `validate_fdic.py` | 11 checks: 10 PASS, 1 WARN | Duplicate CERT, row-count floor, metadata count, null core keys, state codes, asset values, active flag, ZIP, established dates |
| **Census (raw)** | `validate_census.py` | 5 checks: 5 PASS | Schema columns, exactly 52 rows, unique FIPS, FIPS format, positive population and income |
| **Curated** | `validate_curated.py` | 8 checks: 7 PASS, 1 WARN | Fact rows equal staged rows, unique IDs, no orphan keys, valid lag and date range, 52 states, state match rate, FDIC crosswalk matched |
| **Marts** | `validate_mart.py` | 6 checks: 6 PASS | Marts not empty, mart totals reconcile to the fact table, percentages between 0 and 100, internal consistency |

---

## Known Limitations and Assumptions

| Area | Limitation or Assumption |
| --- | --- |
| **FDIC matching** | Matching uses normalized names, not a shared key. Only about 6.9% of complaints (1,260,308 of 18.2M) link to an FDIC institution, most likely because many complained-about companies (for example credit bureaus and debt collectors) are not FDIC-insured banks. Some name collisions may still resolve to the wrong institution. |
| **Closed banks** | The FDIC extract requests active institutions only. Complaints about banks that have since closed will not match. Because the FDIC loader upserts and never deletes, an institution that closes later is not removed from `raw.raw_fdic_institutions`. |
| **Census vintage and grain** | Demographics are ACS 2022 5-year estimates at state level only. They do not change between runs, and no county or ZIP detail is available. |
| **Surrogate keys** | Dimension keys (`company_id`, `product_id`, `issue_id`) are regenerated on every curated rebuild, so they are stable within a build but not across builds. Use the natural keys (`company_name`, `cert`, `complaint_id`) when comparing runs. |
| **Full rebuilds** | Staging, curated, and marts are rebuilt in full on each run (a deliberate trade-off for atomicity and simplicity). The curated build takes several minutes on 18M rows. |
| **API cap** | The CFPB API cannot page past about 10,000 hits per query, so busy windows are split automatically. Any split gap is logged, not silently ignored. |
| **CFPB API access** | The CFPB API blocks standard Python HTTP clients at the TLS level, so the API extractor uses `curl_cffi` (browser impersonation). This depends on the provider's current behavior. |
| **State coverage** | About 0.4% of complaints have no usable state and therefore no Census context. |
| **Single database server** | PostgreSQL hosts both the pipeline data and Airflow's metadata (in separate databases) on one container, which is fine for a course project, not for production. |
| **Executor and security** | `LocalExecutor`, credentials in `.env`, and no TLS between containers are suitable for development only. |
| **Historical data** | Complaints are upserted, so a complaint that the CFPB later updates is refreshed, but one the CFPB deletes is not removed from raw. |

---

## Future Improvements

1. Add a CI workflow (GitHub Actions) that runs `pytest` and a lint step on every pull request.
2. Add alerting (email or Slack) in `notify_failure` instead of log-only notification.
3. Make staging and curated loads incremental (merge only changed partitions) to shorten daily runs.
4. Use stable surrogate keys (hash-based) so dimension keys survive rebuilds.
5. Improve company-to-institution matching with the FDIC LEI field (about 54% populated) and fuzzy matching with a review queue.
6. Handle closed institutions by tracking FDIC status changes (slowly changing dimension).
7. Add county-level Census data to unlock finer geographic