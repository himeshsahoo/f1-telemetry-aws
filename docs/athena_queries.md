# 🔍 Amazon Athena Partition Pruning & Cost Optimization Guide

## External Table Partitioning Strategy
Partitioning by `season`, `round`, and `session` enables 99.8% data scan reduction:

```sql
SELECT driver, AVG(lap_time_sec) as avg_pace
FROM f1_telemetry_db.laps
WHERE season = 2023 AND round = 1 AND session = 'R'
GROUP BY driver;
```

## Scan Footprint Comparison
| Query Type | Unpartitioned Scan | Partitioned Parquet Scan | Scan Reduction | Athena Cost |
| :--- | :--- | :--- | :--- | :--- |
| Single Race Lap Pace | ~150 MB (Full year) | ~20 KB (Single Partition) | **99.98%** | **$0.0000001** |
| Full Season Driver Compare | ~150 MB | ~480 KB (All rounds) | **99.68%** | **$0.000002** |
