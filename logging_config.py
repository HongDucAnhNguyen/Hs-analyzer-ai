"""
Centralized logging configuration for Unified API
Logs to both console and files in /app/logs directory
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Create logs directory if it doesn't exist
# Use /app/logs in Docker, otherwise use ./logs in local development
_base_dir = Path("/app/logs") if Path("/app").exists() else Path(__file__).parent / "logs"
LOGS_DIR = _base_dir
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log file paths
UNIFIED_LOG_FILE = LOGS_DIR / "unified_api.log"
RAG_LOG_FILE = LOGS_DIR / "rag_service.log"
CLASSIFIER_LOG_FILE = LOGS_DIR / "classifier_service.log"
ERROR_LOG_FILE = LOGS_DIR / "errors.log"
SECURITY_LOG_FILE = LOGS_DIR / "security.log"

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    """
    Setup centralized logging with file rotation
    - unified_api.log: All application logs
    - rag_service.log: RAG service specific logs
    - classifier_service.log: Classifier service specific logs
    - errors.log: Error level and above from all services
    - security.log: Suspicious request detections (RAG)
    """
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Unified API file handler (all logs)
    unified_handler = RotatingFileHandler(
        UNIFIED_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    unified_handler.setLevel(logging.INFO)
    unified_handler.setFormatter(console_formatter)
    root_logger.addHandler(unified_handler)
    
    # Error file handler (errors only)
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(console_formatter)
    root_logger.addHandler(error_handler)
    
    # RAG service specific logger
    rag_logger = logging.getLogger("rag_service")
    rag_handler = RotatingFileHandler(
        RAG_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    rag_handler.setLevel(logging.INFO)
    rag_handler.setFormatter(console_formatter)
    rag_logger.addHandler(rag_handler)
    rag_logger.setLevel(logging.INFO)
    
    # Classifier service specific logger
    classifier_logger = logging.getLogger("classifier_service")
    classifier_handler = RotatingFileHandler(
        CLASSIFIER_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    classifier_handler.setLevel(logging.INFO)
    classifier_handler.setFormatter(console_formatter)
    classifier_logger.addHandler(classifier_handler)
    classifier_logger.setLevel(logging.INFO)

    # Security logger for suspicious request detections
    security_logger = logging.getLogger("rag_service.security")
    security_handler = RotatingFileHandler(
        SECURITY_LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(console_formatter)
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
    
    logging.info("✓ Centralized logging configured")
    logging.info(f"  - Unified logs: {UNIFIED_LOG_FILE}")
    logging.info(f"  - RAG logs: {RAG_LOG_FILE}")
    logging.info(f"  - Classifier logs: {CLASSIFIER_LOG_FILE}")
    logging.info(f"  - Error logs: {ERROR_LOG_FILE}")
    logging.info(f"  - Security logs: {SECURITY_LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name
    
    Args:
        name: Logger name (e.g., 'rag_service.api', 'classifier_service.tasks')
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
