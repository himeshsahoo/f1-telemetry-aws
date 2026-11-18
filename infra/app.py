#!/usr/bin/env python3
"""
AWS CDK App Entrypoint
----------------------
Synthesizes the F1TelemetryPipelineStack for deployment.
"""

import os
import aws_cdk as cdk
from pipeline_stack import F1TelemetryPipelineStack

app = cdk.App()

# Read target environment from standard AWS env vars or default to current account/region
account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

env = cdk.Environment(account=account, region=region) if account else None

F1TelemetryPipelineStack(
    app,
    "F1TelemetryPipelineStack",
    env=env,
    description="Serverless F1 Telemetry Ingestion & Stint Analysis Pipeline (AWS Free Tier Optimized)",
)

app.synth()
