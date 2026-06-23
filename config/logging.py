# config/logging.py
# Structured logging configuration
# Uses loguru for enhanced logging capabilities
# Supports JSON formatting for log aggregation

from loguru import logger
import sys
import json
from datetime import datetime
from typing import Any, Dict


class LoggingConfig:
    """
    Configures structured logging for the microservice
    Supports multiple output formats and log levels
    """
    
    @staticmethod
    def setup_logging(log_level: str = "INFO"):
        """
        Initialize logging with specified level
        Removes default handler and adds custom configuration
        """
        # Remove default handler
        logger.remove()
        
        # Add console handler with colored output
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level>",
            level=log_level,
            colorize=True
        )
        
        # Add file handler with JSON format
        logger.add(
            "logs/app_{time:YYYY-MM-DD}.log",
            format=lambda record: json.dumps({
                "timestamp": record["time"].isoformat(),
                "level": record["level"].name,
                "module": record["name"],
                "function": record["function"],
                "line": record["line"],
                "message": record["message"],
                "extra": record["extra"]
            }),
            rotation="00:00",
            retention="30 days",
            compression="gz",
            level=log_level
        )
        
        # Add error file handler
        logger.add(
            "logs/error_{time:YYYY-MM-DD}.log",
            level="ERROR",
            rotation="00:00",
            retention="90 days",
            compression="gz"
        )
        
        logger.info("Logging configured successfully")
