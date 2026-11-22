import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class PipelineConfig:
    """Strongly-typed configuration for AWS serverless CDK deployment."""
    aws_region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    s3_bucket_name: Optional[str] = os.getenv("F1_S3_BUCKET")
    dynamodb_table_name: str = os.getenv("F1_DYNAMODB_TABLE", "f1-telemetry-stints")
    lambda_memory_mb: int = 512
    lambda_timeout_sec: int = 60
    s3_expiration_days: int = 30
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def is_custom_bucket(self) -> bool:
        return self.s3_bucket_name is not None and len(self.s3_bucket_name.strip()) > 0
