# 🏎️ Serverless F1 Telemetry & Strategy Pipeline

[![CodeQL](https://github.com/himeshsahoo/f1-telemetry-aws/actions/workflows/codeql.yml/badge.svg)]()
[![CI](https://github.com/himeshsahoo/f1-telemetry-aws/actions/workflows/ci.yml/badge.svg)]()
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![AWS CDK v2](https://img.shields.io/badge/AWS-CDK%20v2-orange.svg)](https://aws.amazon.com/cdk/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-red.svg)](https://streamlit.io/)
[![AWS Free Tier](https://img.shields.io/badge/AWS-Free%20Tier%20Friendly-green.svg)](https://aws.amazon.com/free/)
[![Tests](https://img.shields.io/badge/pytest-15%2F15%20passing-brightgreen.svg)]()

A production-ready, event-driven serverless telemetry and race-strategy pipeline built for Formula 1 data using **FastF1**, **Apache Parquet**, **AWS S3**, **AWS Lambda (ARM64)**, **Amazon DynamoDB**, **Amazon Athena**, and **Streamlit**.

The entire architecture is **100% AWS Free Tier friendly** and features a full **offline / dry-run mode** so anyone can run, test, and explore the analytics without an AWS account or cloud credentials.

---

## 🏛️ Architecture Overview

```
                                      ┌──────────────────────────────────────────────────────────┐
                                      │                      AWS CLOUD                           │
                                      │                                                          │
  ┌──────────────────────────────┐    │   ┌─────────────────────┐       ┌────────────────────┐   │
  │   Local FastF1 Ingestion     │    │   │      Amazon S3      │       │     AWS Lambda     │   │
  │ (ingest_f1_telemetry.py)     │───►│   │  (raw/season=.../   │──────►│ (process_stints.py)│   │
  │  - Timedelta to Float Secs   │ S3 │   │   laps.parquet)     │ S3    │ - Green-flag filter│   │
  │  - Pit in/out boolean flags  │ Put│   │                     │ Event │ - Stint stats      │   │
  │  - Partitioned Parquet write │    │   └──────────┬──────────┘       │ - Tire OLS Deg     │   │
  └──────────────────────────────┘    │              │                  └─────────┬──────────┘   │
                 │                    │              │                            │              │
                 │                    │              ▼ Athena                     ▼ BatchWrite   │
         Offline │ Parquet            │   ┌─────────────────────┐       ┌────────────────────┐   │
         Dry-Run │                    │   │    Amazon Athena    │       │  Amazon DynamoDB   │   │
                 │                    │   │ (create_table.sql)  │       │ (f1-telemetry-     │   │
                 ▼                    │   │ - Serverless SQL    │       │     stints)        │   │
  ┌──────────────────────────────┐    │   │ - Partitioned scans │       │ - PK: race_id      │   │
  │     Streamlit Dashboard      │◄───┼───┴─────────────────────┘       │ - SK: driver_lap   │   │
  │     (dashboard/app.py)       │    │                                 └─────────┬──────────┘   │
  │  - Driver Lap Times          │◄───┼───────────────────────────────────────────┘ Live Query   │
  │  - Stint Strategy Gantt      │    │                                                          │
  │  - Linear Regression Slopes  │    └──────────────────────────────────────────────────────────┘
  └──────────────────────────────┘
```

---

## 💰 AWS Free Tier & Cost Breakdown

| AWS Service | Free Tier Allowance | Project Consumption (1 Race) | Estimated Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Amazon S3** | 5 GB standard storage, 20,000 GET, 2,000 PUT | ~20 KB per race (Snappy Parquet) | **$0.00** |
| **AWS Lambda** | 1,000,000 invocations & 3.2M sec (ARM64) / mo | 1 execution (~200ms, 512MB RAM) | **$0.00** |
| **Amazon DynamoDB** | 25 GB storage, 25 WCU / 25 RCU free forever | `PAY_PER_REQUEST` on-demand (~350 items) | **$0.00** |
| **Amazon Athena** | 1 TB data scanned per month free | ~20 KB scanned per partition query | **$0.00** |
| **Total Cost** | — | — | **$0.00 / month** |

---


---

## 🐳 Docker Container Execution

You can run the full telemetry dashboard inside a container without installing Python or local dependencies:

```bash
# Build and run with Docker Compose
docker compose up dashboard

# Or build standalone
docker build -t f1-telemetry-dashboard .
docker run -p 8501:8501 f1-telemetry-dashboard
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📚 Technical Documentation
- [System Architecture & Data Flow](docs/architecture.md)
- [Athena Partition Pruning & Cost Optimization](docs/athena_queries.md)
- [Mathematical Formulation of Tire Degradation](docs/tire_degradation_model.md)

## 📁 Project Directory Structure

```
f1-telemetry-aws/
├── athena/
│   └── create_table.sql         # Athena External Table DDL & Analytical SQL Queries
├── dashboard/
│   └── app.py                   # Streamlit interactive race telemetry & strategy app
├── data/
│   ├── sample/
│   │   └── sample_laps.parquet  # Offline sample dataset (Bahrain GP 2023)
│   └── raw/                     # Generated partitioned Parquet data
├── infra/
│   ├── app.py                   # AWS CDK App entrypoint
│   └── pipeline_stack.py        # CDK Stack (S3, DynamoDB, Lambda, IAM, S3 Notifications)
├── ingest/
│   └── ingest_f1_telemetry.py   # FastF1 ingestion, data transformation & S3 exporter
├── lambda/
│   └── process_stints.py        # Lambda event processor: stint metrics & tire degradation
├── tests/
│   ├── test_dashboard.py        # Unit tests for dashboard data formatting & offline loading
│   ├── test_infra.py            # Unit tests for CDK infrastructure synthesis & assertions
│   ├── test_ingest.py           # Unit tests for timedelta conversion & S3 uploads (moto)
│   └── test_processor.py        # Unit tests for degradation slopes & DynamoDB (moto)
├── .env.example                 # Environment configuration template
├── .gitignore                   # Standard gitignore (excluding caches and large data)
├── cdk.json                     # AWS CDK configuration
├── requirements.txt             # Locked Python dependencies
└── README.md                    # Project documentation
```

---

## 🚀 Quickstart: Offline / Local Testing Mode

You can run and test the complete pipeline locally with **zero AWS credentials and zero cloud charges**:

### 1. Setup Environment
```bash
cd C:\Users\Himes\Desktop\f1-telemetry-aws
python -m venv .venv
source .venv/Scripts/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Ingest F1 Telemetry Locally (Dry-Run / Offline Mock)
Run ingestion with `--dry-run` and `--mock` to simulate Bahrain GP data without calling the internet or S3:
```bash
python ingest/ingest_f1_telemetry.py --year 2023 --round 1 --session R --dry-run --mock
```
*Output: Saves partitioned Parquet to `data/raw/season=2023/round=1/session=R/laps.parquet`.*

### 3. Run the Lambda Processor Locally
Execute the stint analytics and degradation slope calculator against the local Parquet file:
```bash
python lambda/process_stints.py --file data/raw/season=2023/round=1/session=R/laps.parquet --dry-run
```
*Output:*
```
--- Stint Analysis Summary (17 Stints Computed) ---
driver  stint compound  total_stint_laps  avg_lap_time_sec  fastest_lap_sec  degradation_slope_sec_per_lap  degradation_r2
   VER      1     SOFT                14           94.327           94.120                        +0.0263          48.5%
   HAM      1     SOFT                12           94.939           94.609                        +0.0642          61.5%
   LEC      1     SOFT                13           94.677           94.308                        +0.0763          84.1%
```

### 4. Launch the Streamlit Dashboard
```bash
streamlit run dashboard/app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser:
- Switch seamlessly between **Offline Parquet (Local)** and **AWS DynamoDB (Live)** modes.
- Explore interactive pace progression line charts.
- View tire-stint strategy Gantt bars colored with official Pirelli compound palettes.
- Analyze OLS tire degradation slopes ($m$ in seconds/lap).

---

## ☁️ AWS Cloud Deployment (AWS CDK)

### 1. Configure AWS Credentials
Copy `.env.example` to `.env` and set your preferred AWS Region and S3 bucket name:
```bash
cp .env.example .env
```
Ensure your AWS CLI is authenticated:
```bash
aws sts get-caller-identity
```

### 2. Deploy Infrastructure with AWS CDK
```bash
# Bootstrap CDK environment (if not already done in the target account/region)
cdk bootstrap

# Synthesize CloudFormation template
cdk synth

# Deploy Stack
cdk deploy
```
CDK will provision:
- An encrypted S3 bucket (`f1-telemetry-raw-...`) with auto-delete lifecycle.
- An on-demand DynamoDB table (`f1-telemetry-stints`).
- An ARM64 Python 3.11 Lambda function (`f1-telemetry-stint-processor`).
- An S3 bucket event notification triggering Lambda on `raw/*.parquet`.

### 3. Ingest Live Data to AWS S3
Fetch live timing data from the FIA via FastF1 and stream directly to your S3 bucket:
```bash
python ingest/ingest_f1_telemetry.py \
  --year 2023 \
  --round 1 \
  --session R \
  --bucket <YOUR_BUCKET_NAME> \
  --region ap-south-1
```
The S3 upload triggers the Lambda processor automatically via S3 ObjectCreated events, which parses the Parquet and writes stint summaries and lap items to DynamoDB within ~200ms.

---

## 📊 Amazon Athena Serverless Analytics

1. Open the **Amazon Athena** console in the AWS Management Console.
2. Ensure your query result location is configured in Athena settings (`s3://<YOUR_BUCKET_NAME>/athena-results/`).
3. Open `athena/create_table.sql` and execute **Step 1** and **Step 2** (substituting your bucket name).
4. Discover all partitions:
   ```sql
   MSCK REPAIR TABLE f1_telemetry_db.laps;
   ```
5. Run analytical queries:

### Fastest Clean Lap of the Grand Prix:
```sql
SELECT Driver, Team, LapNumber, Compound, TyreLife, LapTime_sec
FROM f1_telemetry_db.laps
WHERE season = '2023' AND round = '1' AND session = 'R'
  AND IsAccurate = true AND TrackStatus = '1' AND NOT is_pit_in AND NOT is_pit_out
ORDER BY LapTime_sec ASC
LIMIT 10;
```

### Theoretical Best Lap vs Actual Best Lap:
```sql
WITH BestSectors AS (
    SELECT Driver,
           MIN(Sector1Time_sec) AS BestS1,
           MIN(Sector2Time_sec) AS BestS2,
           MIN(Sector3Time_sec) AS BestS3,
           MIN(LapTime_sec) AS ActualBestLap
    FROM f1_telemetry_db.laps
    WHERE season = '2023' AND round = '1' AND session = 'R'
      AND IsAccurate = true AND TrackStatus = '1'
    GROUP BY Driver
)
SELECT Driver,
       ROUND(BestS1 + BestS2 + BestS3, 3) AS Theoretical_Best_Lap,
       ROUND(ActualBestLap, 3) AS Actual_Best_Lap,
       ROUND(ActualBestLap - (BestS1 + BestS2 + BestS3), 3) AS Potential_Improvement_Delta
FROM BestSectors
ORDER BY Theoretical_Best_Lap ASC;
```

---

## 🧪 Automated Test Suite

The project includes unit tests with mocked AWS services (`moto`) and CDK assertions:
```bash
pytest -v
```

### Test Coverage Highlights:
- `test_convert_timedelta_to_seconds`: Validates microsecond-accurate float conversions and null handling.
- `test_transform_laps_column_structure`: Validates schema integrity, boolean pit flags, and required columns.
- `test_generate_mock_f1_dataset`: Verifies offline dataset generation without network requests.
- `test_save_parquet_file`: Validates Snappy Parquet serialization and deserialization.
- `test_upload_to_s3`: Validates S3 uploads using `moto`.
- `test_float_to_decimal`: Validates recursive Decimal casting to prevent DynamoDB float serialization errors.
- `test_calculate_tire_degradation_slope_synthetic`: Validates OLS regression slope and $R^2$ fit on known slopes.
- `test_process_laps_dataframe_filtering`: Ensures yellow flag (`TrackStatus != 1`), inaccurate, and pit in/out laps are excluded from stint pace.
- `test_dynamodb_batch_write_and_query`: Tests batch writer and query key conditions with `moto`.
- `test_lambda_handler_s3_trigger`: Tests end-to-end S3 Event -> Lambda -> DynamoDB batch write.
- `test_cdk_stack_synthesis`: Verifies CloudFormation resources (ARM64 Lambda, On-Demand DynamoDB, S3 notifications).
- `test_dashboard_helpers`: Tests lap time string formatting (`M:SS.mmm`) and offline Parquet loaders.

---

## 📜 License
MIT License. Open source and free for educational and personal use.
