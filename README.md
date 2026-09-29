# CFPB Complaint Resolution Data Engineering Pipeline

## Project Overview
A reproducible, automated data engineering pipeline that ingests, validates, integrates, and curates CFPB consumer complaint data enriched with financial institution (FDIC) and geographic/demographic (Census ACS) context.

## Problem Statement
See ``docs/problem_statement.md``.

## Team Members / Roles
| Name | Role / Pipeline Stage Owned |
|---|---|
| TBD | TBD |

## Data Source Inventory
See ``docs/source_inventory.md``.

## Architecture
See ``docs/architecture.md`` and ``docs/erd.md``.

## Repository Structure

```
project/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── config/
├── dags/
├── data/
│   ├── raw/
│   ├── staging/ 
│   └── curated/
├── docs/
├── notebooks/
├── src/
│   ├── extract/
│   ├── transform/
│   ├── load/
│   ├── validation/
│   └── utils/
├── sql/
├── tests/
└── outputs/
```

## Installation and Prerequisites
- Docker / Docker Compose
- Python 3.11+

## Configuration
Copy ``.env.example`` to ``.env`` and fill in local values. Never commit ``.env``.

## Running the Pipeline
_To be documented once ingestion/orchestration are implemented._

## Data Quality and Validation
_To be documented — see ``src/validation/``._

## Known Limitations and Assumptions
_To be completed._

## Future Improvements
_To be completed._