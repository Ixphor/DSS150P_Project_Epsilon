# Census ACS Source Profile

- Source file: `data\raw\census\census_state_20261006T144137Z.json`
- Retrieved at: 2026-10-06T14:41:37.061715+00:00
- Source URL: https://api.census.gov/data/2022/acs/acs5
- ACS year: 2022

## Row / Column Counts
- Rows: 52
- Columns: 7

## Fields and Raw Dtypes
All fields arrive as strings from the Census API, regardless of logical type — this must be handled in staging.

- `NAME`: dtype=object
- `B01003_001E`: dtype=object
- `B19013_001E`: dtype=object
- `B17001_002E`: dtype=object
- `B02001_002E`: dtype=object
- `B02001_003E`: dtype=object
- `state`: dtype=object

## Missingness (true nulls/blank strings)
- `NAME`: 0 missing (0.0%)
- `B01003_001E`: 0 missing (0.0%)
- `B19013_001E`: 0 missing (0.0%)
- `B17001_002E`: 0 missing (0.0%)
- `B02001_002E`: 0 missing (0.0%)
- `B02001_003E`: 0 missing (0.0%)
- `state`: 0 missing (0.0%)

## Duplicate Check
- Duplicate `state` FIPS codes: 0
- Fully duplicate rows: 0

## Jam Value Check (Census-specific data quality issue)
Census returns sentinel codes like -666666666 when an estimate can't be computed due to insufficient sample size — these are NOT valid numeric values and must be treated as nulls in staging, not averaged/summed.

- `B01003_001E`: 0 jam-value rows
- `B19013_001E`: 0 jam-value rows
- `B17001_002E`: 0 jam-value rows
- `B02001_002E`: 0 jam-value rows
- `B02001_003E`: 0 jam-value rows

## Descriptive Statistics (numeric fields, jam values excluded)
- `B01003_001E`: min=577929, max=39356104, mean=6430191.8, median=4366154
- `B19013_001E`: min=24002, max=101722, mean=73828.1, median=72090
- `B17001_002E`: min=60134, max=4685272, mean=805575.8, median=553686
- `B02001_002E`: min=265633, max=18943660, mean=4222093.4, median=2961933
- `B02001_003E`: min=4891, max=3552579, mean=799518.5, median=343630

## Known Limitations
- Geography is state-level only (52 rows: 50 states + DC + Puerto Rico) — CFPB complaints only expose ZIP-3, so state is the safest reliable join key; ZCTA-level Census data was considered but rejected for join reliability.
- ACS 5-year estimates are rolling averages, not single-year snapshots — a documented trade-off vs. ACS 1-year data, which has more volatility but fewer small-sample suppressions.
- As of May 2026 the Census API requires a registered key; this is an external dependency documented in `.env.example`.