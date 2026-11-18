"""
Unit Tests for Ingestion Pipeline (ingest/ingest_f1_telemetry.py)
"""

import sys
from pathlib import Path
import boto3
import numpy as np
import pandas as pd
import pytest
from moto import mock_aws

# Add parent directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingest.ingest_f1_telemetry import (
    convert_timedelta_to_seconds,
    generate_mock_f1_dataset,
    save_parquet_file,
    transform_laps,
    upload_to_s3,
)


def test_convert_timedelta_to_seconds():
    """Verifies that Timedeltas are properly converted to rounded float seconds."""
    td_series = pd.Series([
        pd.Timedelta(seconds=92.4567),
        pd.Timedelta(minutes=1, seconds=34.120),
        pd.NaT,
    ])
    result = convert_timedelta_to_seconds(td_series)
    assert result.iloc[0] == 92.457
    assert result.iloc[1] == 94.120
    assert np.isnan(result.iloc[2])


def test_transform_laps_column_structure():
    """Verifies that transform_laps creates all required columns and types."""
    raw_df = pd.DataFrame([
        {
            "Driver": "VER",
            "DriverNumber": "1",
            "Team": "Red Bull Racing",
            "LapNumber": 1,
            "Stint": 1,
            "Compound": "SOFT",
            "TyreLife": 1,
            "FreshTyre": True,
            "Position": 1.0,
            "TrackStatus": "1",
            "IsAccurate": True,
            "LapTime": pd.Timedelta(seconds=93.123),
            "Sector1Time": pd.Timedelta(seconds=28.100),
            "Sector2Time": pd.Timedelta(seconds=39.000),
            "Sector3Time": pd.Timedelta(seconds=26.023),
            "PitInTime": pd.NaT,
            "PitOutTime": pd.NaT,
        },
        {
            "Driver": "VER",
            "DriverNumber": "1",
            "Team": "Red Bull Racing",
            "LapNumber": 2,
            "Stint": 1,
            "Compound": "SOFT",
            "TyreLife": 2,
            "FreshTyre": False,
            "Position": 1.0,
            "TrackStatus": "1",
            "IsAccurate": True,
            "LapTime": pd.Timedelta(seconds=93.500),
            "Sector1Time": pd.Timedelta(seconds=28.200),
            "Sector2Time": pd.Timedelta(seconds=39.100),
            "Sector3Time": pd.Timedelta(seconds=26.200),
            "PitInTime": pd.Timedelta(seconds=93.500),
            "PitOutTime": pd.NaT,
        },
    ])

    transformed = transform_laps(raw_df, year=2023, round_id="1", session_id="R")

    # Assert columns exist
    required_cols = [
        "season", "round", "session", "Driver", "DriverNumber", "Team",
        "LapNumber", "Stint", "Compound", "TyreLife", "FreshTyre",
        "Position", "TrackStatus", "IsAccurate", "LapTime_sec",
        "Sector1Time_sec", "Sector2Time_sec", "Sector3Time_sec",
        "is_pit_in", "is_pit_out"
    ]
    for col in required_cols:
        assert col in transformed.columns, f"Missing expected column: {col}"

    # Assert pit flag logic
    assert transformed["is_pit_in"].iloc[0] is False or transformed["is_pit_in"].iloc[0] == False
    assert transformed["is_pit_in"].iloc[1] is True or transformed["is_pit_in"].iloc[1] == True
    assert transformed["LapTime_sec"].iloc[0] == 93.123


def test_generate_mock_f1_dataset():
    """Verifies that realistic mock dataset generation works offline."""
    df = generate_mock_f1_dataset(year=2023, round_id="1", session_id="R")
    assert not df.empty
    assert len(df) > 100
    assert "VER" in df["Driver"].values
    assert "ALO" in df["Driver"].values
    assert df["season"].iloc[0] == "2023"
    assert df["round"].iloc[0] == "1"


def test_save_parquet_file(tmp_path):
    """Verifies Parquet file saving and column fidelity."""
    df = generate_mock_f1_dataset(year=2023, round_id="1", session_id="R")
    output_file = tmp_path / "test_laps.parquet"
    saved_path = save_parquet_file(df, output_file)
    assert saved_path.exists()

    # Read back and compare
    read_df = pd.read_parquet(saved_path)
    assert len(read_df) == len(df)
    assert set(read_df.columns) == set(df.columns)


@mock_aws
def test_upload_to_s3(tmp_path):
    """Verifies S3 PutObject with moto."""
    bucket_name = "test-f1-bucket"
    s3_key = "raw/season=2023/round=1/session=R/laps.parquet"
    region = "ap-south-1"

    s3_client = boto3.client("s3", region_name=region)
    s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": region},
    )

    test_file = tmp_path / "laps.parquet"
    test_file.write_text("parquet-bytes-placeholder")

    uri = upload_to_s3(test_file, bucket_name, s3_key, region=region)
    assert uri == f"s3://{bucket_name}/{s3_key}"

    # Verify object in S3
    obj = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
    body = obj["Body"].read().decode("utf-8")
    assert body == "parquet-bytes-placeholder"
