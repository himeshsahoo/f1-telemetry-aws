"""
Unit Tests for AWS CDK Infrastructure (infra/pipeline_stack.py)
"""

import sys
from pathlib import Path
import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

# Add infra directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "infra"))

from pipeline_stack import F1TelemetryPipelineStack


def test_cdk_stack_synthesis():
    """Verifies that the CDK stack synthesizes with correct Free Tier resources."""
    app = cdk.App()
    stack = F1TelemetryPipelineStack(app, "TestF1PipelineStack")
    template = Template.from_stack(stack)

    # 1. Verify S3 Bucket exists with encryption and destruction policy
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            },
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )

    # 2. Verify DynamoDB Table exists with on-demand billing and proper keys
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": [
                {"AttributeName": "race_id", "KeyType": "HASH"},
                {"AttributeName": "driver_lap", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "race_id", "AttributeType": "S"},
                {"AttributeName": "driver_lap", "AttributeType": "S"},
            ],
        },
    )

    # 3. Verify Lambda Function configuration (Python 3.11, ARM_64)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "process_stints.lambda_handler",
            "Runtime": "python3.11",
            "Architectures": ["arm64"],
            "Timeout": 60,
            "MemorySize": 512,
        },
    )

    # 4. Verify CloudFormation Outputs
    template.has_output("RawTelemetryBucketName", {})
    template.has_output("DynamoDBTableName", {})
    template.has_output("ProcessorFunctionArn", {})
