# Data Dictionary

Field-level documentation for the key **raw**, **staging** and **curated** tables of the CFPB Complaint Resolution pipeline (database `cfpb_pipeline`, PostgreSQL). Column names, types and keys are taken from `sql/init/01_init_schema.sql`, `src/load/*.py`, `sql/staging/*.sql` and `sql/curated/*.sql`. Quality rules are the ones enforced in `src/validation/validate_*.py` and in the staging SQL. The machine-readable versions of the rules live in `contracts/`.

## Conventions

| Item | Convention |
| --- | --- |
| Layers | `raw` = as received plus lineage columns. `staging` = cleaned, typed, one source only, invalid rows quarantined. `curated` = integrated star schema and marts. |
| Lineage columns | Raw CFPB tables carry `ingested_at`, `source_system`, `batch_id`. |
| Nullability | "Yes" means the column may be NULL. Columns without a `NOT NULL` constraint are listed as "Yes" even if the validators currently find no NULLs. |
| Money units | FDIC `asset`, `deposits`, `net_income` are in **thousands of USD**, as reported by FDIC. |
| Name matching | `staging.normalize_name()` upper-cases, replaces `&` with `AND`, strips punctuation and corporate suffixes (INC, CORP, CO, LLC, LTD, NA, N A, NATIONAL ASSOCIATION, SSB, FSB, THE). The result is the `*_key` used to match CFPB companies to FDIC institutions. |
| Surrogate keys | `company_id`, `product_id`, `issue_id` are identity values regenerated on every curated rebuild. Compare runs on natural keys (`company_name`, `cert`, `complaint_id`). |
| Rerun strategy | Raw: upsert on primary key (or skip if loaded). Staging and curated: full rebuild inside one transaction. Parquet: replace-partition. |
| Violation actions | **fail** = raise `ValidationError`, task fails, downstream tasks blocked. **quarantine** = row written to `staging.complaints_rejected`. **warn** = reported only. **tolerance** = failing-row percentage allowed before an `error` rule becomes FAIL (`MAX_REJECT_PCT`, default 1.0). |

---

## 1. Raw layer

### 1.1 `raw.raw_cfpb_complaints`

| | |
| --- | --- |
| **Grain** | One row per CFPB complaint |
| **Source** | CFPB bulk CSV (`cfpb_bulk`, one-time bootstrap) and CFPB Search API (`cfpb_api`, daily increments) |
| **Primary key** | `complaint_id` |
| **Load strategy** | Bulk: skipped if table has rows (`--force` truncates and reloads). API: `INSERT ... ON CONFLICT (complaint_id) DO UPDATE` |
| **Indexes** | `date_received`, `product` |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `complaint_id` | BIGINT | No (PK) | Unique CFPB complaint number | Unique. `duplicate_complaint_ids` must be 0 (fail) |
| `date_received` | DATE | Yes | Date CFPB received the complaint | Not NULL (quarantine `null_core_field`). Not in the future (quarantine `future_date_received`) |
| `product` | TEXT | Yes | Financial product complained about | Not NULL (quarantine `null_core_field`) |
| `sub_product` | TEXT | Yes | More specific product | Blank becomes `Not specified` in staging |
| `issue` | TEXT | Yes | Main issue category | Blank becomes `Not specified` in staging |
| `sub_issue` | TEXT | Yes | More specific issue | Blank becomes `Not specified` in staging |
| `company_public_response` | TEXT | Yes | Company's optional public statement | Free text |
| `company` | TEXT | Yes | Company the complaint is about | Not NULL (quarantine `null_core_field`) |
| `state` | TEXT | Yes | Consumer's state or territory code | Normalised to upper case in staging; blank becomes NULL |
| `zip_code` | TEXT | Yes | Consumer's (partly masked) ZIP | Pattern `^[0-9X]{5}$`, otherwise set to NULL in staging (warn `invalid_zip_format`) |
| `tags` | TEXT | Yes | Consumer group tag, e.g. older American, servicemember | Blank becomes `No Tag` in staging |
| `submitted_via` | TEXT | Yes | Channel used to submit | Free text (e.g. Web, Phone, Referral, Postal mail, Email, Fax) |
| `date_sent_to_company` | DATE | Yes | Date CFPB sent it to the company | Not NULL and not before `date_received` (quarantine `missing_or_negative_sla_lag`) |
| `company_response_to_consumer` | TEXT | Yes | Company's closing response category | Free text. API field `company_response` is mapped here |
| `timely_response` | TEXT | Yes | Whether the company responded on time | `Yes`, `No` or NULL (quarantine `invalid_timely_enum` otherwise). API field `timely` is mapped here |
| `ingested_at` | TIMESTAMP | Yes | Time the row was loaded or last refreshed | Default `CURRENT_TIMESTAMP`; reset to `NOW()` on upsert |
| `source_system` | TEXT | Yes | Origin of the row | `cfpb_api` for API loads; bulk label for CSV loads |
| `batch_id` | TEXT | Yes | Extract batch identifier (derived from the raw file name) | Free text |

### 1.2 `raw.raw_fdic_institutions`

| | |
| --- | --- |
| **Grain** | One row per FDIC institution (certificate) |
| **Source** | FDIC BankFind API, filter `ACTIVE:1`, 1,000 records per page |
| **Primary key** | `cert` |
| **Load strategy** | Upsert on `cert`. Never deletes, so a later-closed institution stays in raw |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `cert` | BIGINT | No (PK) | FDIC certificate number | Unique (`duplicate_cert`, fail). Not NULL (`null_core_keys`, fail) |
| `name` | TEXT | Yes | Institution name | Not NULL (`null_core_keys`) |
| `name_hcr` | TEXT | Yes | Holding company name | Optional |
| `city` | TEXT | Yes | Headquarters city | Not NULL (`null_core_keys`) |
| `state` | TEXT | Yes | Headquarters state code (postal) | One of the 50 states, DC and US territories (`invalid_state_code`, fail) |
| `state_name` | TEXT | Yes | Headquarters state name | |
| `zip` | TEXT | Yes | Headquarters ZIP | Starts with 5 digits (warn `invalid_zip_format`) |
| `asset` | BIGINT | Yes | Total assets, thousands USD | Greater than 0 (`nonpositive_asset`, fail). NULL is a warning (`null_asset`) |
| `deposits` | BIGINT | Yes | Total deposits, thousands USD | |
| `net_income` | BIGINT | Yes | Net income, thousands USD | May be negative |
| `roa` | NUMERIC(15,4) | Yes | Return on assets | |
| `roe` | NUMERIC(15,4) | Yes | Return on equity | |
| `offices` | INTEGER | Yes | Number of offices | |
| `bank_class` | TEXT | Yes | FDIC institution class code | Verify definitions against FDIC BankFind documentation |
| `charter` | TEXT | Yes | Charter type | |
| `regulator` | TEXT | Yes | Primary federal regulator | |
| `active` | INTEGER | Yes | 1 if currently active | Must be 1 (`not_active`, fail) |
| `inactive` | INTEGER | Yes | 1 if inactive | |
| `established_date` | DATE | Yes | Date established | Not in the future, parseable (warn) |
| `date_updated` | DATE | Yes | Last update date at FDIC | |
| `run_date` | DATE | Yes | FDIC extract run date | |
| `report_date` | DATE | Yes | Financial reporting period date | |
| `ingested_at` | TIMESTAMP | Yes | Time the row was loaded | Default `NOW()` |

Dataset-level rules: at least 1,000 rows (`row_count_floor`, fail) and the API `record_count` must equal the rows received (`metadata_count_matches`, fail).

### 1.3 `raw.raw_census_state`

| | |
| --- | --- |
| **Grain** | One row per state, DC or Puerto Rico (52 rows) |
| **Source** | Census ACS 5-year (2022) API, `for=state:*` |
| **Primary key** | `state_fips` |
| **Load strategy** | Upsert on `state_fips`. Census jam/sentinel codes (-666666666, -888888888, -999999999, -555555555, -222222222) are loaded as NULL |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `state_fips` | TEXT | No (PK) | 2-digit state FIPS code | Unique, 2-digit format (`unique_state_fips`, `valid_fips_format`) |
| `name` | TEXT | Yes | State name | |
| `total_population` | NUMERIC | Yes | ACS `B01003_001E` total population | Greater than 0 (`population_income_positive`) |
| `median_household_income` | NUMERIC | Yes | ACS `B19013_001E`, USD | Greater than 0 (`population_income_positive`) |
| `poverty_population` | NUMERIC | Yes | ACS `B17001_002E` people below poverty line | |
| `white_alone` | NUMERIC | Yes | ACS `B02001_002E` | |
| `black_alone` | NUMERIC | Yes | ACS `B02001_003E` | |
| `ingested_at` | TIMESTAMP | Yes | Time the row was loaded | Default `NOW()` |

Dataset-level rules: all expected columns present (`schema_columns_present`) and exactly 52 rows (`row_count_is_52`).

---

## 2. Staging layer

### 2.1 `staging.complaints`

| | |
| --- | --- |
| **Grain** | One row per valid CFPB complaint |
| **Source** | `raw.raw_cfpb_complaints` through view `staging.v_cfpb_classified` where `reject_reason IS NULL` |
| **Primary key** | `complaint_id` |
| **Rebuild** | Dropped and recreated in one transaction on every run |
| **Reconciliation** | `staged + rejected = raw`, otherwise the stage task raises |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `complaint_id` | BIGINT | No (PK) | Complaint number | Unique |
| `date_received` | DATE | No in practice | Date received | Guaranteed non-NULL and not in the future by the quarantine rules |
| `date_sent_to_company` | DATE | No in practice | Date sent to the company | Guaranteed non-NULL and not before `date_received` |
| `response_lag_days` | INTEGER | No in practice | `date_sent_to_company - date_received` | Greater than or equal to 0 |
| `received_year` | SMALLINT | No in practice | Year of `date_received` | |
| `received_month` | SMALLINT | No in practice | Month of `date_received` | 1 to 12 |
| `product` | TEXT | No in practice | Trimmed product | |
| `sub_product` | TEXT | No | Trimmed sub-product | `Not specified` when blank |
| `issue` | TEXT | No | Trimmed issue | `Not specified` when blank |
| `sub_issue` | TEXT | No | Trimmed sub-issue | `Not specified` when blank |
| `company` | TEXT | No in practice | Upper-cased, trimmed company name | |
| `state` | TEXT | Yes | Upper-cased state code | NULL when blank |
| `zip_code` | TEXT | Yes | Valid 5-character ZIP | NULL when it fails `^[0-9X]{5}$` |
| `tags` | TEXT | No | Consumer tag | `No Tag` when blank |
| `submitted_via` | TEXT | Yes | Submission channel | |
| `company_public_response` | TEXT | Yes | Company public response | |
| `company_response_to_consumer` | TEXT | Yes | Company response category | |
| `timely_response` | TEXT | Yes | Timely flag as received | `Yes`, `No` or NULL |
| `is_timely` | BOOLEAN | Yes | `timely_response = 'Yes'` | NULL when `timely_response` is NULL |
| `source_system` | TEXT | Yes | Origin of the row | |
| `batch_id` | TEXT | Yes | Extract batch id | |
| `ingested_at` | TIMESTAMP | Yes | Raw load time | |

### 2.2 `staging.complaints_rejected` (quarantine)

| | |
| --- | --- |
| **Grain** | One row per CFPB complaint that failed a quarantine rule |
| **Source** | `staging.v_cfpb_classified` where `reject_reason IS NOT NULL` |
| **Rule order** | First matching rule wins (order below) |

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `complaint_id` | BIGINT | No | Complaint number |
| `date_received` | DATE | Yes | As received |
| `date_sent_to_company` | DATE | Yes | As received |
| `product` | TEXT | Yes | As received |
| `company` | TEXT | Yes | As received |
| `timely_response` | TEXT | Yes | As received |
| `reject_reason` | TEXT | No | One of the four values below |
| `source_system` | TEXT | Yes | Origin of the row |
| `batch_id` | TEXT | Yes | Extract batch id |
| `rejected_at` | TIMESTAMP | No | Time of the staging run (`NOW()`) |

| `reject_reason` | Condition |
| --- | --- |
| `null_core_field` | `date_received`, `product` or `company` is NULL |
| `invalid_timely_enum` | `timely_response` is not NULL and not `Yes` / `No` |
| `missing_or_negative_sla_lag` | `date_sent_to_company` is NULL or earlier than `date_received` |
| `future_date_received` | `date_received` is after today |

### 2.3 `staging.fdic_institutions`

| | |
| --- | --- |
| **Grain** | One row per active FDIC institution |
| **Source** | `raw.raw_fdic_institutions` where `cert IS NOT NULL AND active = 1` |
| **Primary key** | `cert` |
| **Indexes** | `name_key`, `holding_company_key` |
| **Reconciliation** | Staged rows must equal raw rows with `active = 1` |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `cert` | BIGINT | No (PK) | FDIC certificate | Unique |
| `name` | TEXT | Yes | Trimmed institution name | |
| `name_key` | TEXT | Yes | `normalize_name(name)` | Join key to `dim_company.company_key` |
| `holding_company_name` | TEXT | Yes | Holding company (blank becomes NULL) | |
| `holding_company_key` | TEXT | Yes | `normalize_name(name_hcr)` | Second join key to `dim_company.company_key` |
| `city` | TEXT | Yes | City (blank becomes NULL) | |
| `state` | TEXT | Yes | Upper-cased state code | |
| `state_name` | TEXT | Yes | State name | |
| `zip5` | TEXT | Yes | First 5 digits of ZIP | NULL if ZIP does not start with 5 digits |
| `asset` | BIGINT | Yes | Total assets, thousands USD | |
| `deposits` | BIGINT | Yes | Deposits, thousands USD | |
| `net_income` | BIGINT | Yes | Net income, thousands USD | |
| `roa` | NUMERIC(15,4) | Yes | Return on assets | |
| `roe` | NUMERIC(15,4) | Yes | Return on equity | |
| `offices` | INTEGER | Yes | Number of offices | |
| `bank_class` | TEXT | Yes | FDIC institution class code | |
| `charter` | TEXT | Yes | Charter type | |
| `regulator` | TEXT | Yes | Primary regulator | |
| `asset_tier` | TEXT | No | Size band from `asset` (thousands USD) | `Over $250B` (>= 250,000,000), `$10B - $250B` (>= 10,000,000), `$1B - $10B` (>= 1,000,000), `Under $1B`, `Unknown` (asset NULL or <= 0) |
| `asset_missing` | BOOLEAN | No | `asset IS NULL OR asset <= 0` | |
| `established_date` | DATE | Yes | Date established | |
| `report_date` | DATE | Yes | Reporting period date | |
| `ingested_at` | TIMESTAMP | Yes | Raw load time | |

### 2.4 `staging.census_state`

| | |
| --- | --- |
| **Grain** | One row per state, DC or Puerto Rico |
| **Source** | `raw.raw_census_state` left-joined to `curated.state_abbr_fips_map` on `state_fips` |
| **Primary key** | `state_fips` |
| **Reconciliation** | Staged rows must equal raw rows |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `state_fips` | TEXT | No (PK) | State FIPS code | Unique |
| `state_abbr` | TEXT | Yes | Postal abbreviation from the reference map | NULL means no mapping (logged by the stage task) |
| `state_name` | TEXT | Yes | Trimmed state name | |
| `total_population` | NUMERIC | Yes | Total population | |
| `median_household_income` | NUMERIC | Yes | Median household income, USD | |
| `poverty_population` | NUMERIC | Yes | People below poverty line | |
| `poverty_rate_pct` | NUMERIC | Yes | `100 * poverty_population / total_population`, 2 decimals | 0 to 100 |
| `white_alone` | NUMERIC | Yes | White alone population | |
| `pct_white_alone` | NUMERIC | Yes | Percent of total population, 2 decimals | 0 to 100 |
| `black_alone` | NUMERIC | Yes | Black or African American alone population | |
| `pct_black_alone` | NUMERIC | Yes | Percent of total population, 2 decimals | 0 to 100 |
| `ingested_at` | TIMESTAMP | Yes | Raw load time | |

### 2.5 `curated.state_abbr_fips_map` (reference)

| Column | Type | Nullable | Meaning |
| --- | --- | --- | --- |
| `state_abbr` | TEXT | No (PK) | Postal abbreviation |
| `state_fips` | TEXT | No | State FIPS code |
| `state_name` | TEXT | Yes | State name |

Seeded by `sql/reference/state_fips_seed.sql`. It lives in the `curated` schema but is **not** dropped by the curated rebuild.

---

## 3. Curated layer (star schema)

### 3.1 `curated.fact_complaints`

| | |
| --- | --- |
| **Grain** | One row per valid complaint |
| **Source** | `staging.complaints` joined to the dimensions below |
| **Primary key** | `complaint_id` |
| **Foreign keys** | `company_id`, `product_id`, `issue_id`, `state_fips`, `institution_cert` |
| **Indexes** | `date_received`, `(received_year, received_month)`, `state_fips`, `company_id`, `institution_cert` (partial, non-NULL) |
| **Rule** | Row count must equal `staging.complaints` (`fact_matches_staging_rowcount`) |

| Column | Type | Nullable | Meaning | Allowed values / rule |
| --- | --- | --- | --- | --- |
| `complaint_id` | BIGINT | No (PK) | Complaint number | Unique (`unique_complaint_id`) |
| `company_id` | INT | No (FK) | Link to `dim_company` | No orphans (`no_orphan_company_keys`) |
| `product_id` | INT | No (FK) | Link to `dim_product` | |
| `issue_id` | INT | No (FK) | Link to `dim_issue` | |
| `state_fips` | TEXT | Yes (FK) | Link to `dim_geography` | NULL when state is missing or unmatched. At least 95% must match (`state_match_rate`, fail) |
| `institution_cert` | BIGINT | Yes (FK) | Link to `dim_institution` through the bridge | NULL for non-FDIC companies. At least one complaint must match (`fdic_crosswalk_matched_some`) |
| `date_received` | DATE | No | Date received | Within valid range (`date_received_in_valid_range`) |
| `date_sent_to_company` | DATE | Yes | Date sent to company | |
| `response_lag_days` | INT | Yes | Days between received and sent | Greater than or equal to 0 (`response_lag_non_negative`) |
| `received_year` | SMALLINT | No | Year received | Partition key for Parquet |
| `received_month` | SMALLINT | No | Month received | 1 to 12. Partition key for Parquet |
| `zip_code` | TEXT | Yes | Valid ZIP or NULL | |
| `tags` | TEXT | Yes | Consumer tag | `No Tag` when blank |
| `submitted_via` | TEXT | Yes | Channel | |
| `company_public_response` | TEXT | Yes | Public response | |
| `company_response_to_consumer` | TEXT | Yes | Response category | |
| `timely_response` | TEXT | Yes | `Yes` / `No` | |
| `is_timely` | BOOLEAN | Yes | Timely flag | |
| `batch_id` | TEXT | Yes | Extract batch id | |
| `ingested_at` | TIMESTAMP | Yes | Raw load time | |

### 3.2 `curated.dim_company`

**Grain:** one row per distinct staged company name. **Source:** `staging.complaints`.

| Column | Type | Nullable | Meaning | Rule |
| --- | --- | --- | --- | --- |
| `company_id` | INT (identity) | No (PK) | Surrogate key | Regenerated each build |
| `company_name` | TEXT | No | Upper-cased company name | Unique |
| `company_key` | TEXT | Yes | `normalize_name(company_name)` | Used for FDIC matching |

### 3.3 `curated.dim_product`

**Grain:** one row per product and sub-product. **Source:** `staging.complaints`.

| Column | Type | Nullable | Meaning | Rule |
| --- | --- | --- | --- | --- |
| `product_id` | INT (identity) | No (PK) | Surrogate key | Regenerated each build |
| `product_name` | TEXT | No | Product | Unique together with `sub_product_name` |
| `sub_product_name` | TEXT | No | Sub-product | `Not specified` when blank |

### 3.4 `curated.dim_issue`

**Grain:** one row per issue and sub-issue. **Source:** `staging.complaints`.

| Column | Type | Nullable | Meaning | Rule |
| --- | --- | --- | --- | --- |
| `issue_id` | INT (identity) | No (PK) | Surrogate key | Regenerated each build |
| `issue_name` | TEXT | No | Issue | Unique together with `sub_issue_name` |
| `sub_issue_name` | TEXT | No | Sub-issue | `Not specified` when blank |

### 3.5 `curated.dim_geography`

**Grain:** one row per state, DC or Puerto Rico. **Source:** `staging.census_state`. Columns, types and meanings are the same as `staging.census_state` (section 2.4) except that `ingested_at` is not carried and `state_name` is `NOT NULL`. Keys: `state_fips` PK, `state_abbr` UNIQUE. `poverty_rate_pct`, `pct_white_alone` and `pct_black_alone` are `NUMERIC(6,2)`. Rule: exactly 52 rows (`dim_geography_has_52_states`).

### 3.6 `curated.dim_institution`

**Grain:** one row per active FDIC institution. **Source:** `staging.fdic_institutions`. Columns, types and meanings are the same as section 2.3 except that `ingested_at` is not carried and `name` is `NOT NULL`. Keys: `cert` PK. Indexes on `name_key` and `holding_company_key`.

### 3.7 `curated.bridge_company_institution`

| | |
| --- | --- |
| **Grain** | One row per CFPB company that matched an FDIC institution |
| **Source** | `dim_company` joined to `dim_institution` |
| **Primary key** | `company_id` (FK to `dim_company`). `cert` is FK to `dim_institution` |
| **Match logic** | Rank 1 is `institution_name` match (`company_key = name_key`), preferred over `holding_company` match (`company_key = holding_company_key`). Ties go to the largest `asset`, then lowest `cert` |

| Column | Type | Nullable | Meaning | Allowed values |
| --- | --- | --- | --- | --- |
| `company_id` | INT | No (PK, FK) | CFPB company | |
| `cert` | BIGINT | No (FK) | Matched FDIC institution | |
| `match_type` | TEXT | No | How the match was made | `institution_name`, `holding_company` |
| `candidate_institutions` | BIGINT | No | Number of distinct institutions that matched this company | At least 1. Values above 1 mean the match is ambiguous |

### 3.8 `curated.mart_complaints_monthly`

| | |
| --- | --- |
| **Grain** | Month x state x product x institution asset tier |
| **Source** | `fact_complaints` with `dim_product`, `dim_geography`, `dim_institution` |
| **Primary key** | `(received_year, received_month, state_fips, product_name, asset_tier)` |

| Column | Type | Nullable | Meaning | Rule |
| --- | --- | --- | --- | --- |
| `received_year` | SMALLINT | No | Year | |
| `received_month` | SMALLINT | No | Month | 1 to 12 |
| `state_fips` | TEXT | No | State FIPS | `NA` when unknown |
| `state_abbr` | TEXT | No | State abbreviation | `NA` when unknown |
| `product_name` | TEXT | No | Product | |
| `asset_tier` | TEXT | No | Institution size tier | `Not FDIC-matched` when no institution |
| `complaints` | BIGINT | No | Complaint count | Sum equals fact row count (`monthly_mart_sums_to_fact`) |
| `timely_complaints` | BIGINT | No | Complaints with `is_timely = true` | At most `complaints` (`counts_internally_consistent`) |
| `timely_pct` | NUMERIC | Yes | Percent timely among complaints with a known timely flag | 0 to 100 (`timely_pct_between_0_and_100`) |
| `avg_response_lag_days` | NUMERIC | Yes | Mean `response_lag_days`, 2 decimals | |
| `state_population` | NUMERIC | Yes | State population | |
| `state_median_income` | NUMERIC | Yes | State median household income | |
| `state_poverty_rate_pct` | NUMERIC | Yes | State poverty rate | |

### 3.9 `curated.mart_institution_scorecard`

| | |
| --- | --- |
| **Grain** | FDIC institution x year (only complaints matched to an institution) |
| **Source** | `fact_complaints` joined to `dim_institution` |
| **Primary key** | `(cert, received_year)` |

| Column | Type | Nullable | Meaning | Rule |
| --- | --- | --- | --- | --- |
| `cert` | BIGINT | No | FDIC certificate | |
| `received_year` | SMALLINT | No | Year | |
| `institution_name` | TEXT | No | Institution name | |
| `holding_company_name` | TEXT | Yes | Holding company | |
| `asset_tier` | TEXT | Yes | Size tier | |
| `hq_state` | TEXT | Yes | Headquarters state | |
| `asset_thousands_usd` | BIGINT | Yes | Total assets, thousands USD | |
| `roa` | NUMERIC(15,4) | Yes | Return on assets | |
| `complaints` | BIGINT | No | Complaint count | Sum equals matched fact rows (`scorecard_sums_to_matched_complaints`) |
| `timely_pct` | NUMERIC | Yes | Percent timely | 0 to 100 |
| `avg_response_lag_days` | NUMERIC | Yes | Mean response lag | |
| `complaints_per_billion_assets` | NUMERIC | Yes | `complaints / (asset / 1,000,000)` (asset is in thousands, so the divisor is billions of USD) | At least 0 (`complaints_per_billion_assets_non_negative`) |

### 3.10 `curated.v_complaints_enriched` (view, exported to Parquet)

**Grain:** one row per complaint with every dimension attached. Columns are those of `fact_complaints` plus `company_name`, `product_name`, `sub_product_name`, `issue_name`, `sub_issue_name`, `state_abbr`, `state_name`, `state_population`, `state_median_income`, `state_poverty_rate_pct`, `institution_name`, `institution_asset_tier`, `institution_asset_thousands_usd` (numeric columns cast to `float8`). Dropped by the curated rebuild (`CASCADE`) and recreated by `build_mart.sql`.

---

## 4. File layer

| Path | Grain | Partitioning | Rerun behaviour |
| --- | --- | --- | --- |
| `data/raw/...` | One file per extract | By source and timestamp | Untouched, replayable |
| `data/staging/fdic_institutions.parquet`, `census_state.parquet` | Same as staging tables | None | Overwritten |
| `data/curated/fact_complaints/received_year=YYYY/received_month=M/part-0.parquet` | One row per complaint (enriched view) | Year and month (hive style) | Replace-partition via temp directory, stale partitions removed on a full run |
| `data/curated/mart_complaints_monthly/received_year=YYYY/part-0.parquet` | Same as monthly mart | Year | Rebuilt |
| `data/curated/mart_institution_scorecard.{parquet,csv,json}` | Same as scorecard | None | Rebuilt |

## 5. Validation gate to table map

| Gate (report file in `outputs/validation/`) | Table checked |
| --- | --- |
| `validation_report.csv` | `raw.raw_cfpb_complaints` |
| `fdic_validation_report.csv`, `fdic_flagged_records.csv` | Latest FDIC raw JSON before staging |
| `census_validation_report.csv` | `raw.raw_census_state` |
| `curated_validation_report.csv` | `curated.fact_complaints`, `dim_geography`, bridge |
| `mart_validation_report.csv` | Both marts against the fact table |
