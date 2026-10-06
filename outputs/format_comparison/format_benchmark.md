Benchmark sample: 200,000 rows x 29 columns (most recent complaints from curated.v_complaints_enriched)

| format | size_mb | write_s | read_all_columns_s | read_3_columns_s | schema_preserved_pct | size_vs_csv_pct |
|---|---|---|---|---|---|---|
| csv | 65.58 | 4.15 | 0.47 | 0.25 | 86.2 | 100.0 |
| json_lines | 179.5 | 1.59 | 2.89 | 2.95 | 86.2 | 273.7 |
| parquet_snappy | 2.74 | 0.38 | 0.11 | 0.01 | 100.0 | 4.2 |
| parquet_zstd | 2.13 | 0.4 | 0.11 | 0.0 | 100.0 | 3.2 |
