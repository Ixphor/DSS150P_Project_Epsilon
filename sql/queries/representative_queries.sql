-- Complaints by state (post-Census enrichment)
SELECT g.name AS state_name, COUNT(*) AS complaint_count
FROM curated.fact_complaints fc
JOIN curated.dim_geography g ON fc.state_fips = g.state_fips
GROUP BY g.name
ORDER BY complaint_count DESC;

-- Top companies by complaint volume
SELECT c.company_name, COUNT(*) AS complaint_count
FROM curated.fact_complaints fc
JOIN curated.dim_company c ON fc.company_id = c.company_id
GROUP BY c.company_name
ORDER BY complaint_count DESC
LIMIT 20;

-- Timely response rate by product
SELECT
    p.product_name,
    COUNT(*) AS total_complaints,
    SUM(CASE WHEN fc.timely_response = 'Yes' THEN 1 ELSE 0 END) AS timely_count,
    ROUND(100.0 * SUM(CASE WHEN fc.timely_response = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 1) AS timely_pct
FROM curated.fact_complaints fc
JOIN curated.dim_product p ON fc.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_complaints DESC;