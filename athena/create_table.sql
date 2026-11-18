-- ============================================================================
-- Amazon Athena DDL & Analytical Queries for Serverless F1 Telemetry Pipeline
-- ============================================================================
-- AWS Free Tier Friendly:
-- 1. Athena charges $5.00 per TB scanned; AWS Free Tier includes 1 TB/month.
-- 2. Because data is partitioned by season, round, and session and stored as
--    columnar Parquet, typical queries scan only ~15-50 KB per race ($0.0000002).
-- ============================================================================

-- Step 1: Create Database
CREATE DATABASE IF NOT EXISTS f1_telemetry_db
COMMENT 'Formula 1 Lap Telemetry and Stint Analytics Database'
LOCATION 's3://<YOUR_BUCKET_NAME>/athena-metadata/';

-- Step 2: Create Partitioned External Table pointing to S3 Parquet Data
-- Replace <YOUR_BUCKET_NAME> with your actual S3 bucket name (e.g., f1-telemetry-raw-free-tier)
CREATE EXTERNAL TABLE IF NOT EXISTS f1_telemetry_db.laps (
    Driver STRING COMMENT '3-letter driver code (e.g. VER, HAM, ALO)',
    DriverNumber STRING COMMENT 'Driver permanent racing number',
    Team STRING COMMENT 'Constructor team name',
    LapNumber INT COMMENT 'Lap number in session',
    Stint INT COMMENT 'Stint count on current tire set',
    Compound STRING COMMENT 'Tire compound name (SOFT, MEDIUM, HARD, INTERMEDIATE, WET)',
    TyreLife INT COMMENT 'Number of laps run on this specific tire set',
    FreshTyre BOOLEAN COMMENT 'Whether tire was new at start of stint',
    Position DOUBLE COMMENT 'Track running position on this lap',
    TrackStatus STRING COMMENT 'F1 track status flag (1=Green, 2=Yellow, 4=SC, 5=Red, 6=VSC)',
    IsAccurate BOOLEAN COMMENT 'Whether timing telemetry is marked accurate by FIA/FastF1',
    LapTime_sec DOUBLE COMMENT 'Total lap time in seconds',
    Sector1Time_sec DOUBLE COMMENT 'Sector 1 time in seconds',
    Sector2Time_sec DOUBLE COMMENT 'Sector 2 time in seconds',
    Sector3Time_sec DOUBLE COMMENT 'Sector 3 time in seconds',
    is_pit_in BOOLEAN COMMENT 'True if driver pitted at end of this lap',
    is_pit_out BOOLEAN COMMENT 'True if lap started from pit exit'
)
COMMENT 'F1 Lap-by-lap telemetry data partitioned by season, round, session'
PARTITIONED BY (
    season STRING,
    round STRING,
    session STRING
)
STORED AS PARQUET
LOCATION 's3://<YOUR_BUCKET_NAME>/raw/'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY'
);

-- Step 3: Automatically Discover Partitions
-- Run this once after uploading new race data to S3:
MSCK REPAIR TABLE f1_telemetry_db.laps;

-- Or add explicit partition manually (instant, no metadata scan):
-- ALTER TABLE f1_telemetry_db.laps ADD IF NOT EXISTS
--   PARTITION (season='2023', round='1', session='R')
--   LOCATION 's3://<YOUR_BUCKET_NAME>/raw/season=2023/round=1/session=R/';


-- ============================================================================
-- ANALYTICAL QUERIES FOR FORMULA 1 RACE STRATEGY
-- ============================================================================

-- Query 1: Fastest Accurate Lap of the Grand Prix (Official Lap Record in Session)
SELECT
    Driver,
    Team,
    LapNumber,
    Compound,
    TyreLife,
    LapTime_sec,
    Sector1Time_sec,
    Sector2Time_sec,
    Sector3Time_sec
FROM f1_telemetry_db.laps
WHERE season = '2023'
  AND round = '1'
  AND session = 'R'
  AND IsAccurate = true
  AND TrackStatus = '1'
  AND NOT is_pit_in
  AND NOT is_pit_out
ORDER BY LapTime_sec ASC
LIMIT 10;


-- Query 2: Stint-by-Stint Average Pace and Tire Wear per Driver
SELECT
    Driver,
    Team,
    Stint,
    Compound,
    MIN(LapNumber) AS StintStartLap,
    MAX(LapNumber) AS StintEndLap,
    COUNT(*) AS TotalLapsInStint,
    ROUND(AVG(CASE WHEN IsAccurate AND TrackStatus = '1' AND NOT is_pit_in AND NOT is_pit_out THEN LapTime_sec END), 3) AS AvgGreenLapTime_sec,
    ROUND(MIN(CASE WHEN IsAccurate AND TrackStatus = '1' AND NOT is_pit_in AND NOT is_pit_out THEN LapTime_sec END), 3) AS FastestLapInStint_sec,
    ROUND(STDDEV(CASE WHEN IsAccurate AND TrackStatus = '1' AND NOT is_pit_in AND NOT is_pit_out THEN LapTime_sec END), 3) AS PaceConsistency_StdDev
FROM f1_telemetry_db.laps
WHERE season = '2023'
  AND round = '1'
  AND session = 'R'
GROUP BY Driver, Team, Stint, Compound
ORDER BY Driver, Stint;


-- Query 3: Compound Performance Delta (Average Lap Time per Compound across all Drivers)
SELECT
    Compound,
    COUNT(*) AS CleanLapCount,
    ROUND(AVG(LapTime_sec), 3) AS AvgLapTime_sec,
    ROUND(MIN(LapTime_sec), 3) AS AbsoluteFastest_sec,
    ROUND(AVG(TyreLife), 1) AS AvgTyreLifeOnLaps
FROM f1_telemetry_db.laps
WHERE season = '2023'
  AND round = '1'
  AND session = 'R'
  AND IsAccurate = true
  AND TrackStatus = '1'
  AND NOT is_pit_in
  AND NOT is_pit_out
GROUP BY Compound
ORDER BY AvgLapTime_sec ASC;


-- Query 4: Theoretical Best Lap (Sum of Best Sectors) vs Actual Best Lap
WITH BestSectors AS (
    SELECT
        Driver,
        MIN(Sector1Time_sec) AS BestS1,
        MIN(Sector2Time_sec) AS BestS2,
        MIN(Sector3Time_sec) AS BestS3,
        MIN(LapTime_sec) AS ActualBestLap
    FROM f1_telemetry_db.laps
    WHERE season = '2023'
      AND round = '1'
      AND session = 'R'
      AND IsAccurate = true
      AND TrackStatus = '1'
    GROUP BY Driver
)
SELECT
    Driver,
    ROUND(BestS1, 3) AS Best_S1,
    ROUND(BestS2, 3) AS Best_S2,
    ROUND(BestS3, 3) AS Best_S3,
    ROUND(BestS1 + BestS2 + BestS3, 3) AS Theoretical_Best_Lap,
    ROUND(ActualBestLap, 3) AS Actual_Best_Lap,
    ROUND(ActualBestLap - (BestS1 + BestS2 + BestS3), 3) AS Potential_Improvement_Delta
FROM BestSectors
ORDER BY Theoretical_Best_Lap ASC;
