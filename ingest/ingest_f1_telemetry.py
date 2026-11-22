#!/usr/bin/env python3
"""
F1 Telemetry Ingestion Script
-----------------------------
Extracts lap-by-lap telemetry and timing data from FastF1,
transforms Timedeltas to float seconds, pit times to boolean flags,
filters columns, and exports partitioned Parquet files either locally (dry-run)
or directly to an AWS S3 bucket.

AWS Free Tier Friendly:
- Direct S3 PutObject avoids intermediate server runtime.
- Partitioned Parquet enables minimal Athena scan costs ($0 within 1 TB/mo free tier).
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
try:
    from models import SessionMetadataModel
except ImportError:
    SessionMetadataModel = None

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("f1_ingest")


def convert_timedelta_to_seconds(td_series: pd.Series) -> pd.Series:
    """Safely converts a pandas Timedelta Series to float seconds (rounded to 3 decimals)."""
    if td_series is None or td_series.empty:
        return pd.Series(dtype="float64")
    # Convert to timedelta if not already
    td = pd.to_timedelta(td_series)
    return td.dt.total_seconds().round(3)


def transform_laps(
    raw_laps_df: pd.DataFrame,
    year: int,
    round_id: str,
    session_id: str,
) -> pd.DataFrame:
    """
    Transforms raw FastF1 laps DataFrame according to pipeline specifications:
    1. Timedelta to float seconds: LapTime, Sector1Time, Sector2Time, Sector3Time
    2. PitInTime / PitOutTime to boolean flags: is_pit_in, is_pit_out
    3. Retain designated columns + partition metadata
    """
    df = raw_laps_df.copy()

    # 1. Convert timedeltas to float seconds
    df["LapTime_sec"] = convert_timedelta_to_seconds(df.get("LapTime"))
    df["Sector1Time_sec"] = convert_timedelta_to_seconds(df.get("Sector1Time"))
    df["Sector2Time_sec"] = convert_timedelta_to_seconds(df.get("Sector2Time"))
    df["Sector3Time_sec"] = convert_timedelta_to_seconds(df.get("Sector3Time"))

    # 2. Convert pit times to boolean flags
    if "PitInTime" in df.columns:
        df["is_pit_in"] = df["PitInTime"].notna() & (df["PitInTime"] != "")
    else:
        df["is_pit_in"] = False

    if "PitOutTime" in df.columns:
        df["is_pit_out"] = df["PitOutTime"].notna() & (df["PitOutTime"] != "")
    else:
        df["is_pit_out"] = False

    # 3. Add partition metadata
    df["season"] = str(year)
    df["round"] = str(round_id)
    df["session"] = str(session_id)

    # 4. Define required schema columns
    target_columns = [
        "season",
        "round",
        "session",
        "Driver",
        "DriverNumber",
        "Team",
        "LapNumber",
        "Stint",
        "Compound",
        "TyreLife",
        "FreshTyre",
        "Position",
        "TrackStatus",
        "IsAccurate",
        "LapTime_sec",
        "Sector1Time_sec",
        "Sector2Time_sec",
        "Sector3Time_sec",
        "is_pit_in",
        "is_pit_out",
    ]

    # Fill missing optional columns with defaults if necessary
    for col in target_columns:
        if col not in df.columns:
            if col in ["FreshTyre", "IsAccurate"]:
                df[col] = True
            elif col in ["Stint", "LapNumber", "TyreLife"]:
                df[col] = 1
            elif col == "TrackStatus":
                df[col] = "1"
            elif col == "Position":
                df[col] = np.nan
            else:
                df[col] = None

    # Cast types cleanly for Parquet schema stability
    df["Driver"] = df["Driver"].astype(str)
    df["DriverNumber"] = df["DriverNumber"].astype(str)
    df["Team"] = df["Team"].astype(str)
    df["LapNumber"] = pd.to_numeric(df["LapNumber"], errors="coerce").fillna(0).astype("int32")
    df["Stint"] = pd.to_numeric(df["Stint"], errors="coerce").fillna(1).astype("int32")
    df["Compound"] = df["Compound"].fillna("UNKNOWN").astype(str).str.upper()
    df["TyreLife"] = pd.to_numeric(df["TyreLife"], errors="coerce").fillna(0).astype("int32")
    df["FreshTyre"] = df["FreshTyre"].fillna(False).astype(bool)
    df["Position"] = pd.to_numeric(df["Position"], errors="coerce").astype("float32")
    df["TrackStatus"] = df["TrackStatus"].fillna("1").astype(str)
    df["IsAccurate"] = df["IsAccurate"].fillna(False).astype(bool)
    df["is_pit_in"] = df["is_pit_in"].astype(bool)
    df["is_pit_out"] = df["is_pit_out"].astype(bool)

    # Return filtered DataFrame with exact column order
    return df[target_columns].sort_values(by=["Driver", "LapNumber"]).reset_index(drop=True)


def generate_mock_f1_dataset(year: int = 2023, round_id: str = "1", session_id: str = "R") -> pd.DataFrame:
    """
    Generates a realistic F1 race dataset (e.g. 2023 Bahrain GP)
    for 100% offline testing, dry-runs, or when network is unavailable.
    """
    logger.info("Generating realistic offline mock F1 dataset (Season %s, Round %s, Session %s)...", year, round_id, session_id)
    np.random.seed(42)

    drivers_config = [
        ("VER", "1", "Red Bull Racing", 94.0, [("SOFT", 14), ("HARD", 22), ("HARD", 21)]),
        ("PER", "11", "Red Bull Racing", 94.3, [("SOFT", 15), ("HARD", 21), ("SOFT", 21)]),
        ("ALO", "14", "Aston Martin", 94.5, [("SOFT", 13), ("HARD", 22), ("HARD", 22)]),
        ("HAM", "44", "Mercedes", 94.7, [("SOFT", 12), ("HARD", 20), ("SOFT", 25)]),
        ("SAI", "55", "Ferrari", 94.8, [("SOFT", 13), ("HARD", 22), ("HARD", 22)]),
        ("LEC", "16", "Ferrari", 94.4, [("SOFT", 13), ("HARD", 26)]),  # DNF at lap 39
    ]

    all_laps = []

    for driver, num, team, base_pace, stints in drivers_config:
        current_lap = 1
        pos = 1
        for stint_idx, (compound, stint_length) in enumerate(stints, start=1):
            deg_factor = 0.08 if compound == "SOFT" else 0.04
            for tyre_age in range(1, stint_length + 1):
                # Fuel burn-off effect (-0.035s per lap)
                fuel_effect = -0.035 * current_lap
                # Tire wear effect
                wear_effect = deg_factor * tyre_age
                # Random noise
                noise = np.random.normal(0, 0.15)
                lap_time = base_pace + fuel_effect + wear_effect + noise

                # Pit in / out flags
                is_pit_out = (tyre_age == 1 and stint_idx > 1)
                is_pit_in = (tyre_age == stint_length)

                if is_pit_out:
                    lap_time += 18.0
                elif is_pit_in:
                    lap_time += 4.0

                s1 = lap_time * 0.31 + np.random.normal(0, 0.05)
                s2 = lap_time * 0.42 + np.random.normal(0, 0.05)
                s3 = lap_time - s1 - s2

                all_laps.append({
                    "Driver": driver,
                    "DriverNumber": num,
                    "Team": team,
                    "LapNumber": current_lap,
                    "Stint": stint_idx,
                    "Compound": compound,
                    "TyreLife": tyre_age,
                    "FreshTyre": (tyre_age == 1),
                    "Position": pos,
                    "TrackStatus": "1",
                    "IsAccurate": not (is_pit_in or is_pit_out),
                    "LapTime": pd.Timedelta(seconds=lap_time),
                    "Sector1Time": pd.Timedelta(seconds=s1),
                    "Sector2Time": pd.Timedelta(seconds=s2),
                    "Sector3Time": pd.Timedelta(seconds=s3),
                    "PitInTime": pd.Timedelta(seconds=lap_time) if is_pit_in else pd.NaT,
                    "PitOutTime": pd.Timedelta(seconds=0) if is_pit_out else pd.NaT,
                })
                current_lap += 1
            pos += 1

    raw_df = pd.DataFrame(all_laps)
    return transform_laps(raw_df, year, str(round_id), session_id)


def fetch_fastf1_data(
    year: int,
    round_id: str,
    session_id: str = "R",
    cache_dir: str = ".fastf1_cache",
) -> pd.DataFrame:
    """Loads session telemetry from FastF1 with caching."""
    import fastf1

    os.makedirs(cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)

    try:
        round_arg = int(round_id)
    except ValueError:
        round_arg = round_id

    logger.info("Loading FastF1 session: Year=%s, Round=%s, Session=%s", year, round_arg, session_id)
    session = fastf1.get_session(year, round_arg, session_id)
    session.load(telemetry=False, weather=False, messages=False)

    laps = session.laps
    if laps is None or laps.empty:
        raise ValueError(f"No laps returned by FastF1 for {year} Round {round_id} Session {session_id}")

    logger.info("FastF1 loaded %d laps successfully.", len(laps))
    return transform_laps(laps, year, str(round_id), session_id)


def save_parquet_file(df: pd.DataFrame, output_path: Path) -> Path:
    """Saves DataFrame as Parquet with snappy compression."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, output_path, compression="snappy")
    file_size_kb = output_path.stat().st_size / 1024
    logger.info("Saved Parquet file: %s (%.2f KB, %d rows)", output_path, file_size_kb, len(df))
    return output_path


def upload_to_s3(
    file_path: Path,
    bucket: str,
    s3_key: str,
    region: str = "ap-south-1",
) -> str:
    """Uploads Parquet file to S3 bucket."""
    logger.info("Uploading %s to s3://%s/%s (region: %s)...", file_path, bucket, s3_key, region)
    s3_client = boto3.client("s3", region_name=region)
    try:
        s3_client.upload_file(str(file_path), bucket, s3_key)
        uri = f"s3://{bucket}/{s3_key}"
        logger.info("Upload successful: %s", uri)
        return uri
    except NoCredentialsError:
        logger.error("AWS credentials not found. Provide AWS_ACCESS_KEY_ID or use --dry-run.")
        raise
    except ClientError as e:
        logger.error("Failed to upload to S3: %s", e)
        raise


def run_pipeline(
    year: int = 2023,
    round_id: str = "1",
    session_id: str = "R",
    bucket: Optional[str] = None,
    region: str = "ap-south-1",
    dry_run: bool = False,
    use_mock: bool = False,
    output_dir: str = "data",
    cache_dir: str = ".fastf1_cache",
) -> Tuple[Path, Optional[str]]:
    """Executes the end-to-end ingestion pipeline."""
    # 1. Fetch data
    df = None
    if use_mock:
        df = generate_mock_f1_dataset(year, round_id, session_id)
    else:
        try:
            df = fetch_fastf1_data(year, round_id, session_id, cache_dir)
        except Exception as e:
            logger.warning("FastF1 live fetch failed (%s). Falling back to offline mock dataset.", e)
            df = generate_mock_f1_dataset(year, round_id, session_id)

    # 2. Partition Path
    partition_rel = f"season={year}/round={round_id}/session={session_id}"
    local_output_path = Path(output_dir) / "raw" / partition_rel / "laps.parquet"

    # 3. Save Parquet
    save_parquet_file(df, local_output_path)

    # 4. Upload or Dry-run
    s3_uri = None
    s3_key = f"raw/{partition_rel}/laps.parquet"

    if dry_run or not bucket:
        logger.info("Dry-run mode enabled (or no bucket provided). Skipping S3 upload.")
        logger.info("Output ready locally at: %s", local_output_path.resolve())
    else:
        s3_uri = upload_to_s3(local_output_path, bucket, s3_key, region)

    return local_output_path, s3_uri


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="F1 Telemetry Ingestion: FastF1 -> Parquet -> S3",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--year", type=int, default=2023, help="Championship season year")
    parser.add_argument("--round", type=str, default="1", help="Round number or Grand Prix name (e.g. 1 or Bahrain)")
    parser.add_argument("--session", type=str, default="R", choices=["FP1", "FP2", "FP3", "Q", "SQ", "S", "R"], help="Session identifier")
    parser.add_argument("--bucket", type=str, default=os.getenv("F1_S3_BUCKET"), help="Target S3 Bucket")
    parser.add_argument("--region", type=str, default=os.getenv("AWS_DEFAULT_REGION", "ap-south-1"), help="AWS Region")
    parser.add_argument("--dry-run", action="store_true", help="Save Parquet locally without uploading to AWS")
    parser.add_argument("--mock", action="store_true", help="Generate simulated offline dataset without calling FastF1 API")
    parser.add_argument("--output-dir", type=str, default="data", help="Local directory for Parquet storage")
    parser.add_argument("--cache-dir", type=str, default=".fastf1_cache", help="FastF1 HTTP response cache directory")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    try:
        local_path, s3_uri = run_pipeline(
            year=args.year,
            round_id=args.round,
            session_id=args.session,
            bucket=args.bucket,
            region=args.region,
            dry_run=args.dry_run,
            use_mock=args.mock,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
        )
        print("\n=== Ingestion Completed Successfully ===")
        print(f"Local Parquet: {local_path.resolve()}")
        if s3_uri:
            print(f"S3 Destination: {s3_uri}")
        else:
            print("S3 Upload: Skipped (dry-run)")
    except Exception as e:
        logger.error("Ingestion failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
