#!/usr/bin/env python3
"""
AWS Lambda Function: F1 Stint & Telemetry Processor
---------------------------------------------------
Triggered by S3 ObjectCreated events on the `raw/` prefix.
Reads partitioned Parquet lap files, filters accurate green-flag laps,
computes stint analytics (average lap time, fastest lap, stint length,
and tire degradation slope via linear regression), and batch-writes
structured items to Amazon DynamoDB.

Partition Key: `race_id`   (e.g., season#2023#round#1#session#R)
Sort Key:      `driver_lap` (e.g., STINT#VER#01 or LAP#VER#001)

AWS Free Tier Friendly:
- ARM64 Graviton2 Lambda execution (~200ms runtime per race).
- DynamoDB PAY_PER_REQUEST on-demand billing ($0 within free tier limits).
"""

import io
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote_plus

import boto3
import numpy as np
try:
    from logger import StructuredLogger
    structured_log = StructuredLogger()
except ImportError:
    structured_log = None
import pandas as pd

# Logger setup
logger = logging.getLogger("f1_stint_processor")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)


def float_to_decimal(obj: Any) -> Any:
    """
    Recursively converts float values to Decimal for DynamoDB serialization,
    avoiding boto3 Float types are not supported exceptions.
    """
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return Decimal(str(round(obj, 4)))
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items() if float_to_decimal(v) is not None}
    elif isinstance(obj, list):
        return [float_to_decimal(v) for v in obj if float_to_decimal(v) is not None]
    return obj


def calculate_tire_degradation_slope(
    tyre_life_series: pd.Series,
    lap_time_series: pd.Series,
) -> Tuple[float, float]:
    """
    Computes tire degradation slope (seconds per lap) and R-squared fit
    using ordinary least squares (OLS) linear regression: LapTime_sec = m * TyreLife + c.
    
    A positive slope indicates tire wear degradation (lap times slowing down).
    Returns (slope, r_squared).
    """
    if len(tyre_life_series) < 2:
        return 0.0, 0.0

    x = tyre_life_series.to_numpy(dtype=float)
    y = lap_time_series.to_numpy(dtype=float)

    # Filter any NaNs or infinities
    mask = ~np.isnan(x) & ~np.isnan(y) & ~np.isinf(x) & ~np.isinf(y)
    x = x[mask]
    y = y[mask]

    if len(x) < 2:
        return 0.0, 0.0

    x_var = np.var(x, ddof=1)
    if x_var == 0:
        return 0.0, 0.0

    # OLS Slope: cov(x, y) / var(x) with matching sample ddof=1
    slope = float(np.cov(x, y, ddof=1)[0, 1] / x_var)
    intercept = float(np.mean(y) - slope * np.mean(x))

    # Calculate R-squared
    y_pred = slope * x + intercept
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    ss_res = np.sum((y - y_pred) ** 2)
    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
    r_squared = max(0.0, min(1.0, r_squared))

    return round(slope, 4), round(r_squared, 4)


def process_laps_dataframe(
    df: pd.DataFrame,
    race_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Processes raw laps DataFrame to extract:
    1. Stint summaries (average pace, degradation slope, fastest lap)
    2. Accurate lap records for fine-grained querying
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to process_laps_dataframe.")
        return [], []

    # Infer or construct race_id
    if not race_id:
        season = str(df["season"].iloc[0]) if "season" in df.columns else "2023"
        round_num = str(df["round"].iloc[0]) if "round" in df.columns else "1"
        session = str(df["session"].iloc[0]) if "session" in df.columns else "R"
        race_id = f"season#{season}#round#{round_num}#session#{session}"

    stint_items = []
    lap_items = []

    # Ensure required columns exist
    df["LapTime_sec"] = pd.to_numeric(df.get("LapTime_sec"), errors="coerce")
    df["TyreLife"] = pd.to_numeric(df.get("TyreLife"), errors="coerce").fillna(0).astype(int)
    df["LapNumber"] = pd.to_numeric(df.get("LapNumber"), errors="coerce").fillna(0).astype(int)
    df["Stint"] = pd.to_numeric(df.get("Stint"), errors="coerce").fillna(1).astype(int)
    df["IsAccurate"] = df.get("IsAccurate", False).astype(bool)
    df["TrackStatus"] = df.get("TrackStatus", "1").astype(str)
    df["is_pit_in"] = df.get("is_pit_in", False).astype(bool)
    df["is_pit_out"] = df.get("is_pit_out", False).astype(bool)

    # Green flag condition: TrackStatus == '1', IsAccurate == True, no pit in/out, valid lap time
    green_flag_mask = (
        (df["TrackStatus"].str.strip() == "1")
        & (df["IsAccurate"] == True)
        & (~df["is_pit_in"])
        & (~df["is_pit_out"])
        & (df["LapTime_sec"].notna())
        & (df["LapTime_sec"] > 50.0)  # Filter unrealistic lap times
    )

    clean_laps_df = df[green_flag_mask].copy()

    # 1. Generate Stint Summaries
    grouped = df.groupby(["Driver", "Stint"])
    for (driver, stint_num), driver_stint_all in grouped:
        stint_clean = clean_laps_df[
            (clean_laps_df["Driver"] == driver) & (clean_laps_df["Stint"] == stint_num)
        ]

        total_stint_laps = len(driver_stint_all)
        green_laps_count = len(stint_clean)

        driver_num = str(driver_stint_all["DriverNumber"].iloc[0]) if "DriverNumber" in driver_stint_all.columns else ""
        team = str(driver_stint_all["Team"].iloc[0]) if "Team" in driver_stint_all.columns else ""
        compound = str(driver_stint_all["Compound"].iloc[0]).upper() if "Compound" in driver_stint_all.columns else "UNKNOWN"
        start_lap = int(driver_stint_all["LapNumber"].min())
        end_lap = int(driver_stint_all["LapNumber"].max())

        if green_laps_count > 0:
            avg_lap_time = float(stint_clean["LapTime_sec"].mean())
            fastest_lap = float(stint_clean["LapTime_sec"].min())
            std_lap_time = float(stint_clean["LapTime_sec"].std()) if green_laps_count > 1 else 0.0
            deg_slope, r2 = calculate_tire_degradation_slope(
                stint_clean["TyreLife"],
                stint_clean["LapTime_sec"],
            )
        else:
            avg_lap_time = None
            fastest_lap = None
            std_lap_time = None
            deg_slope, r2 = 0.0, 0.0

        stint_summary = {
            "race_id": race_id,
            "driver_lap": f"STINT#{driver}#{int(stint_num):02d}",
            "entity_type": "STINT_SUMMARY",
            "driver": str(driver),
            "driver_number": driver_num,
            "team": team,
            "stint": int(stint_num),
            "compound": compound,
            "start_lap": start_lap,
            "end_lap": end_lap,
            "total_stint_laps": total_stint_laps,
            "green_flag_laps": green_laps_count,
            "avg_lap_time_sec": avg_lap_time,
            "fastest_lap_sec": fastest_lap,
            "std_lap_time_sec": std_lap_time,
            "degradation_slope_sec_per_lap": deg_slope,
            "degradation_r2": r2,
        }
        stint_items.append(float_to_decimal(stint_summary))

    # 2. Generate Lap Records
    for _, row in df.iterrows():
        driver = str(row["Driver"])
        lap_num = int(row["LapNumber"])
        lap_time = float(row["LapTime_sec"]) if pd.notna(row["LapTime_sec"]) else None

        lap_item = {
            "race_id": race_id,
            "driver_lap": f"LAP#{driver}#{lap_num:03d}",
            "entity_type": "LAP_RECORD",
            "driver": driver,
            "driver_number": str(row.get("DriverNumber", "")),
            "team": str(row.get("Team", "")),
            "lap_number": lap_num,
            "stint": int(row.get("Stint", 1)),
            "compound": str(row.get("Compound", "")).upper(),
            "tyre_life": int(row.get("TyreLife", 0)),
            "position": float(row["Position"]) if pd.notna(row.get("Position")) else None,
            "lap_time_sec": lap_time,
            "sector1_time_sec": float(row["Sector1Time_sec"]) if pd.notna(row.get("Sector1Time_sec")) else None,
            "sector2_time_sec": float(row["Sector2Time_sec"]) if pd.notna(row.get("Sector2Time_sec")) else None,
            "sector3_time_sec": float(row["Sector3Time_sec"]) if pd.notna(row.get("Sector3Time_sec")) else None,
            "is_accurate": bool(row.get("IsAccurate", False)),
            "is_pit_in": bool(row.get("is_pit_in", False)),
            "is_pit_out": bool(row.get("is_pit_out", False)),
            "track_status": str(row.get("TrackStatus", "1")),
        }
        lap_items.append(float_to_decimal(lap_item))

    return stint_items, lap_items


def write_items_to_dynamodb(
    table_name: str,
    items: List[Dict[str, Any]],
    region: str = "ap-south-1",
) -> int:
    """Batch writes items to DynamoDB using boto3 batch_writer."""
    if not items:
        return 0

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    written_count = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
            written_count += 1

    logger.info("Successfully wrote %d items to DynamoDB table '%s'.", written_count, table_name)
    return written_count


def process_s3_parquet(
    bucket: str,
    key: str,
    table_name: Optional[str] = None,
    region: str = "ap-south-1",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Reads Parquet from S3 and executes pipeline processing."""
    logger.info("Processing S3 object s3://%s/%s", bucket, key)
    s3_client = boto3.client("s3", region_name=region)

    response = s3_client.get_object(Bucket=bucket, Key=key)
    parquet_bytes = response["Body"].read()

    df = pd.read_parquet(io.BytesIO(parquet_bytes))
    logger.info("Loaded Parquet DataFrame with %d rows, %d columns.", len(df), len(df.columns))

    # Parse race_id from key or dataframe: raw/season=2023/round=1/session=R/laps.parquet
    race_id = None
    parts = key.split("/")
    season, round_id, session = "2023", "1", "R"
    for part in parts:
        if part.startswith("season="):
            season = part.split("=")[1]
        elif part.startswith("round="):
            round_id = part.split("=")[1]
        elif part.startswith("session="):
            session = part.split("=")[1]
    race_id = f"season#{season}#round#{round_id}#session#{session}"

    stint_summaries, lap_records = process_laps_dataframe(df, race_id=race_id)
    all_items = stint_summaries + lap_records

    logger.info("Extracted %d stint summaries and %d lap records (Total: %d).", len(stint_summaries), len(lap_records), len(all_items))

    written_count = 0
    if not dry_run and table_name:
        written_count = write_items_to_dynamodb(table_name, all_items, region=region)
    else:
        logger.info("Dry-run mode: skipped DynamoDB write.")

    return {
        "race_id": race_id,
        "stint_count": len(stint_summaries),
        "lap_count": len(lap_records),
        "items_written": written_count,
        "sample_stints": stint_summaries[:3] if stint_summaries else [],
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entrypoint triggered by S3 ObjectCreated events.
    """
    logger.info("Received event: %s", json.dumps(event))
    table_name = os.getenv("TABLE_NAME") or os.getenv("F1_DYNAMODB_TABLE")
    region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

    results = []

    # 1. Standard S3 Event Records
    if "Records" in event:
        for record in event["Records"]:
            s3_data = record.get("s3", {})
            bucket = s3_data.get("bucket", {}).get("name")
            key = unquote_plus(s3_data.get("object", {}).get("key", ""))

            if not bucket or not key:
                logger.warning("Record missing bucket or key: %s", record)
                continue

            if not key.endswith(".parquet"):
                logger.info("Skipping non-parquet object: %s", key)
                continue

            result = process_s3_parquet(bucket, key, table_name=table_name, region=region)
            results.append(result)

    # 2. Direct Invocation (Testing / Manual Replay)
    elif "bucket" in event and "key" in event:
        result = process_s3_parquet(event["bucket"], event["key"], table_name=table_name, region=region)
        results.append(result)

    # 3. Local File Invocation
    elif "file_path" in event:
        file_path = event["file_path"]
        df = pd.read_parquet(file_path)
        stints, laps = process_laps_dataframe(df)
        results.append({
            "stints": len(stints),
            "laps": len(laps),
            "sample_stints": stints[:2],
        })

    return {
        "statusCode": 200,
        "body": json.dumps({"processed_count": len(results), "results": results}, default=str),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Lambda Stint Processor Locally")
    parser.add_argument("--file", type=str, required=True, help="Local Parquet file path to process")
    parser.add_argument("--table", type=str, default=os.getenv("F1_DYNAMODB_TABLE"), help="DynamoDB Table Name")
    parser.add_argument("--region", type=str, default="ap-south-1", help="AWS Region")
    parser.add_argument("--dry-run", action="store_true", help="Calculate metrics without writing to DynamoDB")
    args = parser.parse_args()

    local_file = Path(args.file)
    if not local_file.exists():
        print(f"File not found: {local_file}")
        sys.exit(1)

    print(f"Reading {local_file}...")
    df_local = pd.read_parquet(local_file)
    stints, laps = process_laps_dataframe(df_local)
    print(f"\n--- Stint Analysis Summary ({len(stints)} Stints Computed) ---")
    stints_df = pd.DataFrame([{k: (float(v) if isinstance(v, Decimal) else v) for k, v in s.items()} for s in stints])
    cols_to_show = ["driver", "stint", "compound", "total_stint_laps", "avg_lap_time_sec", "fastest_lap_sec", "degradation_slope_sec_per_lap", "degradation_r2"]
    available_cols = [c for c in cols_to_show if c in stints_df.columns]
    print(stints_df[available_cols].to_string(index=False))

    if not args.dry_run and args.table:
        print(f"\nWriting {len(stints) + len(laps)} items to DynamoDB table '{args.table}'...")
        count = write_items_to_dynamodb(args.table, stints + laps, region=args.region)
        print(f"Successfully wrote {count} items.")
    else:
        print("\nDry-run complete. No DynamoDB writes executed.")
