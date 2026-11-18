"""
Unit Tests for Lambda Processor (lambda/process_stints.py)
"""

import io
import json
import sys
from decimal import Decimal
from pathlib import Path
import boto3
import numpy as np
import pandas as pd
import pytest
from moto import mock_aws

# Add directories to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAMBDA_DIR = PROJECT_ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from process_stints import (
    calculate_tire_degradation_slope,
    float_to_decimal,
    lambda_handler,
    process_laps_dataframe,
    process_s3_parquet,
    write_items_to_dynamodb,
)


def test_float_to_decimal():
    """Verifies that floats and nested structures are converted to Decimal."""
    data = {
        "float_val": 92.4567,
        "int_val": 10,
        "str_val": "VER",
        "nan_val": np.nan,
        "nested": {"nested_float": 1.23},
        "list_val": [4.56, 7.89],
    }
    result = float_to_decimal(data)
    assert isinstance(result["float_val"], Decimal)
    assert result["float_val"] == Decimal("92.4567")
    assert result["int_val"] == 10
    assert "nan_val" not in result
    assert isinstance(result["nested"]["nested_float"], Decimal)
    assert isinstance(result["list_val"][0], Decimal)


def test_calculate_tire_degradation_slope_synthetic():
    """Verifies OLS linear regression slope with known synthetic degradation."""
    # Deg slope = +0.05 seconds per lap
    tyre_life = pd.Series(range(1, 16))
    lap_times = pd.Series([90.0 + 0.05 * t for t in tyre_life])

    slope, r2 = calculate_tire_degradation_slope(tyre_life, lap_times)
    assert pytest.approx(slope, abs=1e-3) == 0.05
    assert pytest.approx(r2, abs=1e-3) == 1.0


def test_calculate_tire_degradation_slope_edge_cases():
    """Verifies slope calculation handles single-lap or zero variance safely."""
    # 1 lap
    slope, r2 = calculate_tire_degradation_slope(pd.Series([1]), pd.Series([92.0]))
    assert slope == 0.0 and r2 == 0.0

    # Constant lap times
    slope, r2 = calculate_tire_degradation_slope(pd.Series([1, 2, 3]), pd.Series([90.0, 90.0, 90.0]))
    assert slope == 0.0


def test_process_laps_dataframe_filtering():
    """Verifies that inaccurate, yellow-flag, and pit laps are excluded from stint average pace and slope."""
    records = [
        # Clean green lap 1
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "VER", "DriverNumber": "1", "Team": "Red Bull",
            "LapNumber": 1, "Stint": 1, "Compound": "SOFT", "TyreLife": 1, "Position": 1.0,
            "TrackStatus": "1", "IsAccurate": True, "LapTime_sec": 92.0, "Sector1Time_sec": 28.0,
            "Sector2Time_sec": 38.0, "Sector3Time_sec": 26.0, "is_pit_in": False, "is_pit_out": False
        },
        # Clean green lap 2
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "VER", "DriverNumber": "1", "Team": "Red Bull",
            "LapNumber": 2, "Stint": 1, "Compound": "SOFT", "TyreLife": 2, "Position": 1.0,
            "TrackStatus": "1", "IsAccurate": True, "LapTime_sec": 92.1, "Sector1Time_sec": 28.0,
            "Sector2Time_sec": 38.1, "Sector3Time_sec": 26.0, "is_pit_in": False, "is_pit_out": False
        },
        # Safety Car / Yellow Flag lap (TrackStatus = '4') -> should be ignored in stint pace
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "VER", "DriverNumber": "1", "Team": "Red Bull",
            "LapNumber": 3, "Stint": 1, "Compound": "SOFT", "TyreLife": 3, "Position": 1.0,
            "TrackStatus": "4", "IsAccurate": True, "LapTime_sec": 120.0, "Sector1Time_sec": 40.0,
            "Sector2Time_sec": 45.0, "Sector3Time_sec": 35.0, "is_pit_in": False, "is_pit_out": False
        },
        # Pit In lap -> should be ignored in stint pace
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "VER", "DriverNumber": "1", "Team": "Red Bull",
            "LapNumber": 4, "Stint": 1, "Compound": "SOFT", "TyreLife": 4, "Position": 1.0,
            "TrackStatus": "1", "IsAccurate": True, "LapTime_sec": 96.0, "Sector1Time_sec": 28.0,
            "Sector2Time_sec": 38.0, "Sector3Time_sec": 30.0, "is_pit_in": True, "is_pit_out": False
        },
    ]
    df = pd.DataFrame(records)

    stints, laps = process_laps_dataframe(df)

    assert len(stints) == 1
    stint = stints[0]
    assert stint["driver"] == "VER"
    assert stint["stint"] == 1
    assert stint["total_stint_laps"] == 4
    assert stint["green_flag_laps"] == 2  # Only Laps 1 and 2 are accurate green-flag non-pit laps

    # Avg lap time must be mean of 92.0 and 92.1 = 92.05, NOT affected by lap 3 (120s) or lap 4 (96s)
    assert pytest.approx(float(stint["avg_lap_time_sec"]), abs=1e-2) == 92.05
    assert stint["fastest_lap_sec"] == Decimal("92") or stint["fastest_lap_sec"] == Decimal("92.0")

    # Check partition and sort keys
    assert stint["race_id"] == "season#2023#round#1#session#R"
    assert stint["driver_lap"] == "STINT#VER#01"
    assert len(laps) == 4
    assert laps[0]["driver_lap"] == "LAP#VER#001"


@mock_aws
def test_dynamodb_batch_write_and_query():
    """Verifies DynamoDB batch writer with moto."""
    table_name = "f1-telemetry-test"
    region = "ap-south-1"

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "race_id", "KeyType": "HASH"},
            {"AttributeName": "driver_lap", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "race_id", "AttributeType": "S"},
            {"AttributeName": "driver_lap", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    items = [
        {"race_id": "season#2023#round#1#session#R", "driver_lap": "STINT#VER#01", "driver": "VER", "avg_lap_time_sec": Decimal("92.5")},
        {"race_id": "season#2023#round#1#session#R", "driver_lap": "LAP#VER#001", "driver": "VER", "lap_number": 1},
    ]

    count = write_items_to_dynamodb(table_name, items, region=region)
    assert count == 2

    # Query back
    from boto3.dynamodb.conditions import Key
    res = table.query(KeyConditionExpression=Key("race_id").eq("season#2023#round#1#session#R"))
    assert len(res["Items"]) == 2


@mock_aws
def test_lambda_handler_s3_trigger():
    """Verifies end-to-end S3 Event -> Lambda -> DynamoDB batch write."""
    bucket_name = "f1-raw-test-bucket"
    table_name = "f1-telemetry-stints"
    region = "ap-south-1"
    key = "raw/season=2023/round=1/session=R/laps.parquet"

    # 1. Setup S3
    s3_client = boto3.client("s3", region_name=region)
    s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": region},
    )

    # 2. Setup DynamoDB
    dynamodb = boto3.resource("dynamodb", region_name=region)
    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "race_id", "KeyType": "HASH"},
            {"AttributeName": "driver_lap", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "race_id", "AttributeType": "S"},
            {"AttributeName": "driver_lap", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # 3. Create Sample Parquet and Put in S3
    import pyarrow as pa
    import pyarrow.parquet as pq

    sample_df = pd.DataFrame([
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "ALO", "DriverNumber": "14", "Team": "Aston Martin",
            "LapNumber": 1, "Stint": 1, "Compound": "SOFT", "TyreLife": 1, "Position": 3.0,
            "TrackStatus": "1", "IsAccurate": True, "LapTime_sec": 94.2, "Sector1Time_sec": 28.5,
            "Sector2Time_sec": 39.2, "Sector3Time_sec": 26.5, "is_pit_in": False, "is_pit_out": False
        },
        {
            "season": "2023", "round": "1", "session": "R", "Driver": "ALO", "DriverNumber": "14", "Team": "Aston Martin",
            "LapNumber": 2, "Stint": 1, "Compound": "SOFT", "TyreLife": 2, "Position": 3.0,
            "TrackStatus": "1", "IsAccurate": True, "LapTime_sec": 94.3, "Sector1Time_sec": 28.5,
            "Sector2Time_sec": 39.3, "Sector3Time_sec": 26.5, "is_pit_in": False, "is_pit_out": False
        },
    ])
    table = pa.Table.from_pandas(sample_df)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    s3_client.put_object(Bucket=bucket_name, Key=key, Body=buf.getvalue())

    # 4. Trigger Lambda with S3 Event
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket_name},
                    "object": {"key": key},
                }
            }
        ]
    }

    import os
    os.environ["TABLE_NAME"] = table_name
    os.environ["AWS_DEFAULT_REGION"] = region

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200

    body = json.loads(response["body"])
    assert body["processed_count"] == 1
    result = body["results"][0]
    assert result["stint_count"] == 1
    assert result["lap_count"] == 2
    assert result["items_written"] == 3  # 1 stint summary + 2 laps
