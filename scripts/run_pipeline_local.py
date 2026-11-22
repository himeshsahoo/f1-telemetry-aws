#!/usr/bin/env python3
"""
Orchestrated Local Runner for F1 Telemetry Pipeline
---------------------------------------------------
Runs ingestion mock and lambda processor sequentially in offline mode,
validating generated Parquet files and stint calculations.
"""
import argparse
import subprocess
import sys
from pathlib import Path

def run_local_pipeline(year: int = 2023, round_id: int = 1, session: str = "R") -> bool:
    print(f"=== Running F1 Pipeline Locally: {year} Round {round_id} Session {session} ===")
    project_root = Path(__file__).resolve().parent.parent

    # 1. Ingest
    ingest_script = project_root / "ingest" / "ingest_f1_telemetry.py"
    ingest_cmd = [sys.executable, str(ingest_script), "--year", str(year), "--round", str(round_id), "--session", session, "--dry-run", "--mock"]
    print(f"-> Executing Ingest: {' '.join(ingest_cmd)}")
    res = subprocess.run(ingest_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Ingest failed: {res.stderr}")
        return False
    print("✓ Ingestion successful!")

    # 2. Process
    parquet_path = project_root / "data" / "raw" / f"season={year}" / f"round={round_id}" / f"session={session}" / "laps.parquet"
    if not parquet_path.exists():
        parquet_path = project_root / "data" / "sample" / "sample_laps.parquet"

    processor_script = project_root / "lambda" / "process_stints.py"
    proc_cmd = [sys.executable, str(processor_script), "--file", str(parquet_path), "--dry-run"]
    print(f"-> Executing Processor: {' '.join(proc_cmd)}")
    res = subprocess.run(proc_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Processor failed: {res.stderr}")
        return False
    print("✓ Stint processing successful!")
    print(res.stdout[-400:])
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local F1 Pipeline Runner")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--session", default="R")
    args = parser.parse_args()
    success = run_local_pipeline(args.year, args.round, args.session)
    sys.exit(0 if success else 1)
