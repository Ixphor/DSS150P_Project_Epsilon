-- 1. Complaints per state, normalised by population (CFPB x Census)
SELECT g.state_name,
       COUNT(*)                                                    AS complaints,
       g.total_population,
       ROUND(100000.0 * COUNT(*) / g.total_population, 1)          AS complaints_per_100k
FROM curated.fact_complaints f
JOIN curated.dim_geography g ON g.state_fips = f.state_fips
GROUP BY g.state_name, g.total_population
ORDER BY complaints_per_100k DESC;

-- 2. Top 20 companies by complaint volume
SELECT c.company_name, COUNT(*) AS complaints
FROM curated.fact_complaints f
JOIN curated.dim_company c ON c.company_id = f.company_id
GROUP BY c.company_name
ORDER BY complaints DESC
LIMIT 20;

-- 3. Timely-response rate by product
SELECT p.product_name,
       COUNT(*)                                                         AS total_complaints,
       ROUND(100.0 * AVG((f.is_timely)::int), 1)                        AS timely_pct
FROM curated.fact_complaints f
JOIN curated.dim_product p ON p.product_id = f.product_id
GROUP BY p.product_name
ORDER BY total_complaints DESC;

-- 4. Complaints against FDIC-insured institutions, by asset tier (CFPB x FDIC)
SELECT i.asset_tier,
       COUNT(DISTINCT i.cert)            AS institutions,
       COUNT(*)                          AS complaints,
       ROUND(AVG(f.response_lag_days), 2) AS avg_response_lag_days
FROM curated.fact_complaints f
JOIN curated.dim_institution i ON i.cert = f.institution_cert
GROUP BY i.asset_tier
ORDER BY complaints DESC;

-- 5. Complaints per $1B of assets for the 15 most-complained-about matched institutions (CFPB x FDIC)
SELECT i.name, i.asset_tier, COUNT(*) AS complaints,
       ROUND(COUNT(*) / NULLIF(i.asset / 1000000.0, 0), 2) AS complaints_per_billion_assets
FROM curated.fact_complaints f
JOIN curated.dim_institution i ON i.cert = f.institution_cert
GROUP BY i.cert, i.name, i.asset_tier, i.asset
ORDER BY complaints DESC
LIMIT 15;

-- 6. Complaint volume vs. state poverty rate (CFPB x Census)
SELECT g.state_name, g.poverty_rate_pct, g.median_household_income, COUNT(*) AS complaints
FROM curated.fact_complaints f
JOIN curated.dim_geography g ON g.state_fips = f.state_fips
WHERE f.received_year = 2025
GROUP BY g.state_name, g.poverty_rate_pct, g.median_household_income
ORDER BY g.poverty_rate_pct DESC;

-- 7. Monthly trend (partition-friendly: filters on received_year)
SELECT received_year, received_month, COUNT(*) AS complaints
FROM curated.fact_complaints
WHERE received_year >= 2024
GROUP BY received_year, received_month
ORDER BY received_year, received_month;

-- 8. How well did the FDIC crosswalk match? (data-integration quality)
SELECT b.match_type, COUNT(DISTINCT b.company_id) AS companies, SUM(x.n) AS complaints
FROM curated.bridge_company_institution b
JOIN (SELECT company_id, COUNT(*) AS n FROM curated.fact_complaints GROUP BY company_id) x USING (company_id)
GROUP BY b.match_type;
