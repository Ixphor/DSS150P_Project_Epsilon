CREATE SCHEMA IF NOT EXISTS staging;

-- Canonical key for matching organisation names across sources, e.g.
--   "JPMORGAN CHASE BANK, N.A."  -> "JPMORGAN CHASE BANK"
--   "JPMorgan Chase & Co."       -> "JPMORGAN CHASE AND"
-- Used to join CFPB companies to FDIC institutions and FDIC holding companies.
CREATE OR REPLACE FUNCTION staging.normalize_name(raw TEXT) RETURNS TEXT AS $$
    SELECT NULLIF(
        TRIM(regexp_replace(
            regexp_replace(
                regexp_replace(
                    regexp_replace(UPPER(COALESCE(raw, '')), '&', ' AND ', 'g'),
                    '[^A-Z0-9 ]', ' ', 'g'
                ),
                '\m(THE|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LLC|LTD|NA|N A|NATIONAL ASSOCIATION|SSB|FSB)\M', ' ', 'g'
            ),
            '\s+', ' ', 'g'
        )),
        ''
    );
$$ LANGUAGE SQL IMMUTABLE;
