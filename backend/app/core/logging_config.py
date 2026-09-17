"""Structured logging configuration for Qingtu."""
import logging
import sys
from pythonjsonlogger import jsonlogger
from app.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['environment'] = settings.ENVIRONMENT
        log_record['service'] = 'qingtu-backend'
        if not log_record.get('timestamp'):
            log_record['timestamp'] = record.created


def setup_logging():
    """Configure structured JSON logging."""
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler with JSON formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # JSON formatter
    formatter = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        rename_fields={
            'levelname': 'level',
            'name': 'logger',
            'created': 'timestamp'
        }
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set specific logger levels
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    return root_logger


# Create logger instance
logger = logging.getLogger(__name__)
