import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

class StructuredLogger:
    """CloudWatch-friendly structured JSON logger for AWS Lambda."""

    def __init__(self, service_name: str = "f1-telemetry-processor", level: Optional[str] = None):
        self.service_name = service_name
        self.level_str = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(getattr(logging, self.level_str, logging.INFO))
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            self.logger.addHandler(handler)
        self.context: Dict[str, Any] = {}

    def set_context(self, **kwargs):
        self.context.update(kwargs)

    def _format_event(self, level: str, message: str, **kwargs) -> str:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "level": level,
            "message": message,
            **self.context,
            **kwargs,
        }
        return json.dumps(record, default=str)

    def info(self, msg: str, **kwargs):
        self.logger.info(self._format_event("INFO", msg, **kwargs))

    def warning(self, msg: str, **kwargs):
        self.logger.warning(self._format_event("WARNING", msg, **kwargs))

    def error(self, msg: str, **kwargs):
        self.logger.error(self._format_event("ERROR", msg, **kwargs))

    def debug(self, msg: str, **kwargs):
        self.logger.debug(self._format_event("DEBUG", msg, **kwargs))
