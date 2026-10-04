# Source Data Profiling Summary (FDIC BankFind Institutions)

## Dataset Overview
The FDIC institutions dataset was retrieved from the BankFind API on October 1, 2026, filtered to active institutions only (ACTIVE:1). Each record is one FDIC-insured institution, identified by a unique certificate number (CERT).

| Metric | Value |
| --- | --- |
| Total Records | 4,230 |
| Unique CERT Values | 4,230 (0 Duplicates) |
| Distinct Institution Names | 3,727 |
| Names Shared by Multiple Records | 205 |
| Distinct States | 55 (includes territories) |
| Distinct Charter Classes | 8 |
| Active Institutions | 4,230 (100%, by filter) |
| Total Columns | 150 |

## Data Quality & Completeness
* CERT is fully unique, so it is the reliable primary key for this source.
* Institution name is not unique. 4,230 records share 3,727 distinct names, and 205 names appear in more than one record. Name-based matching to CFPB company names needs normalization and a tie-breaking rule.
* ASSET is missing for 5 records (0.12%). The same count of 5 appears in many financial columns such as NETINC, DEP, ROA, and ROE, so these are likely the same institutions with no financial report. They should be flagged during staging.
* CERT, NAME, STALP, CITY, ZIP, and ESTYMD have no missing values.
* LEI is missing in 46.36% of records, so it can support matching for only about 54% of institutions.
* NAMEHCR (holding company name) is missing in 16.17% of records.
* Several columns hold a single value in every record (for example ACTIVE, INACTIVE, RUNDATE, RISDATE, NEWCERT, ENDEFYMD, and OAKAR) and carry no information for analysis.
* Many columns are almost entirely empty. REGAGENT2 is 100% null (0 distinct values). INSAGNT2, CHANGEC6, and PRIORNAME9 are 99.98% null. The PRIORNAME, CHANGEC, and TE columns are above 98% null in the top 20 least complete columns. These columns carry very little information and are candidates for exclusion from the curated layer.

## Range Checks
* ASSET ranges from 3,489 to 4,091,315,000. The values appear to be in thousands of dollars, so the largest institution holds roughly 4.09 trillion dollars in assets and the smallest about 3.5 million dollars. The unit should be confirmed against the FDIC field documentation before use.
* Establishment dates (ESTYMD) range from 1792-01-01 to 2026-09-28. No date falls after the ingestion date.

## Categorical Distributions
* Geography: The top five states are TX (347), IL (325), IA (225), MN (221), and MO (192), which together hold about 31% of all institutions. Texas alone holds about 8.2%.
* Charter class: The top three codes are NM (2,389), SM (696), and N (659), covering about 88.5% of records. The codes should be decoded using the FDIC data dictionary before reporting.
* Specialization: Commercial Lending Specialization accounts for 2,386 institutions (about 56.4%), followed by Agricultural Specialization (913, about 21.6%). The top five groups cover about 97% of records.
* Holding company: Wintrust Financial Corp has the most institutions (16). The field is not uniform, since one of the top values is a trust name ("R DEAN PHILLIPS BK TR DATED 11-19-2004") rather than a company.

## Scope Note
Closed institutions are excluded by the ACTIVE:1 filter. Complaints against banks that have since closed may not match any record in this source unless the filter is removed.