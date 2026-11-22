"""
AWS CDK Stack: Serverless F1 Telemetry Pipeline
-----------------------------------------------
Provisions free-tier-optimized AWS serverless infrastructure:
1. Amazon S3: Raw partitioned Parquet storage with event notifications
2. Amazon DynamoDB: On-demand (PAY_PER_REQUEST) table for stints & laps
3. AWS Lambda: Python 3.11 (ARM64 Graviton2) telemetry processor
4. Least-Privilege IAM Roles & Bucket Policies
"""

import os
from constructs import Construct
try:
    from infra.config import PipelineConfig
except ImportError:
    try:
        from config import PipelineConfig
    except ImportError:
        PipelineConfig = None
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_iam as iam,
)


class F1TelemetryPipelineStack(Stack):
    """Provisions S3, DynamoDB, and Lambda event-driven processing."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # -------------------------------------------------------------
        # 1. Amazon S3 Bucket: Partitioned Parquet Storage
        # -------------------------------------------------------------
        # Configured with SSL enforcement, block public access, and auto-cleanup for free-tier dev.
        raw_bucket = s3.Bucket(
            self,
            "F1RawTelemetryBucket",
            bucket_name=os.getenv("F1_S3_BUCKET"),  # Generates unique name if None
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=False,  # Avoids duplicate version storage charges
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldParquetData",
                    enabled=True,
                    expiration=Duration.days(90),  # Auto-clean data older than 90 days
                )
            ],
        )

        # -------------------------------------------------------------
        # 2. Amazon DynamoDB Table: Stints & Laps Datastore
        # -------------------------------------------------------------
        # Free Tier: 25 GB storage and 25 RCU/WCU free permanently.
        # PAY_PER_REQUEST charges $0 when idle.
        stint_table = dynamodb.Table(
            self,
            "F1StintTelemetryTable",
            table_name=os.getenv("F1_DYNAMODB_TABLE", "f1-telemetry-stints"),
            partition_key=dynamodb.Attribute(
                name="race_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="driver_lap",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=False,  # Keeps within free tier limits
            removal_policy=RemovalPolicy.DESTROY,
        )

        # -------------------------------------------------------------
        # 3. AWS Lambda Function: Stint & Degradation Processor
        # -------------------------------------------------------------
        # Uses ARM64 (Graviton2) for 20% lower cost and higher performance.
        lambda_dir = os.path.join(os.path.dirname(__file__), "..", "lambda")

        processor_fn = lambda_.Function(
            self,
            "F1StintProcessorFunction",
            function_name="f1-telemetry-stint-processor",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="process_stints.lambda_handler",
            code=lambda_.Code.from_asset(lambda_dir),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=512,
            timeout=Duration.seconds(60),
            environment={
                "TABLE_NAME": stint_table.table_name,
                "LOG_LEVEL": "INFO",
            },
        )

        # -------------------------------------------------------------
        # 4. Least-Privilege IAM Permissions
        # -------------------------------------------------------------
        # Grant read access specifically to the raw/ prefix
        raw_bucket.grant_read(processor_fn, "raw/*")
        # Grant batch write access to the DynamoDB table
        stint_table.grant_write_data(processor_fn)

        # -------------------------------------------------------------
        # 5. S3 ObjectCreated Notification -> Lambda Trigger
        # -------------------------------------------------------------
        raw_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(processor_fn),
            s3.NotificationKeyFilter(prefix="raw/", suffix=".parquet"),
        )

        # -------------------------------------------------------------
        # 6. CloudFormation Outputs
        # -------------------------------------------------------------
        CfnOutput(
            self,
            "RawTelemetryBucketName",
            value=raw_bucket.bucket_name,
            description="S3 bucket for partitioned F1 telemetry Parquet files",
            export_name="F1RawBucketName",
        )

        CfnOutput(
            self,
            "DynamoDBTableName",
            value=stint_table.table_name,
            description="DynamoDB table for F1 stint summaries and lap records",
            export_name="F1DynamoTableName",
        )

        CfnOutput(
            self,
            "ProcessorFunctionArn",
            value=processor_fn.function_arn,
            description="Lambda processor function ARN",
            export_name="F1ProcessorArn",
        )
