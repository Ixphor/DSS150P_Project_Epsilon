# Source Data Profiling Summary (CFPB Database)

## Dataset Overview
The raw CFPB Consumer Complaint database contains over a decade of historical records, characterized by high overall uniqueness but heavily skewed categorical distributions.

| Metric | Value |
| --- | --- |
| Total Records | 18,040,765 |
| Unique Complaint IDs | 18,040,765 (0 Duplicates) |
| Date Range | December 1, 2011-September 27, 2026 |
| Distinct Companies | 8,130 |
| Distinct Products | 21 |
| Distinct States | 63 (Includes US territories/minor islands)|

## Data Quality & Completeness
Core operational fields exhibit near-perfect completeness, while optional consumer demographic tags and public responses are heavily null.
* 100% Complete (0 Null): `complain_id`, `product`, `company`, `date_received`, `date_sent_to_company`, `submitted_via`, `timely_response`.
* High Completeness (<1% Null): `issue` (6 nulls), `company_response_to_consumer` (21 nulls), `zip code` (2758 nulls), `state` (62942 nulls)
* Moderate Missingness: `sub_product` (1.30% null pct), `sub_issue` (5.21% null pct)
* High Missingness: company_public_response: `company_public_response` (44.99% nulls), `tags` (95.50% nulls)

## Temporal Anomalies
* Negative SLA Lag: 7050 records exhibit a chronological anomaly where 'date_sent_to_company' occurs before 'date_received'. These represent 0.03% of the dataset and must be quarantined or flagged during the staging phase to prevent negative response-time SLA calculations.

## Categorical Distributions
* Dominant Issues: The dataset is heavily skewed toward credit reporting. The top two issues, "Incorrect information on your report" (8.17M) and "Improper use of your report" (3.44M), account for over 64% of all complaints.
* Identity Concerns: The most frequent sub-issue is "Information belongs to someone else," appearing 5.34 million times.
* Demographic Tags: Only 4.5% of complaintes include demographic tags. Of those, "Servicemember" (516k), followed by "Older American" (236k), and overlapping combinations (59k).
* Standardization Response: When companies provide a public response, it is overwhelmingly boilerplate. Over 9.5 million records utilize the exact phrase: "Company has responded to the consumer and the CFPB and chooses not to provide a public response."
