"""Logging configuration using Loguru."""

import sys
from pathlib import Path
from loguru import logger
from src.config.settings import LoggingSettings


def setup_logging(settings: LoggingSettings) -> None:
    """Configure Loguru logger with settings.
    
    Args:
        settings: Logging configuration settings.
    """
    # Remove default handler
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stderr,
        level=settings.level,
        format=settings.format,
        colorize=True,
        backtrace=True,
        diagnose=False,
    )
    
    # Add file handler
    log_file = settings.file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        log_file,
        level=settings.level,
        format=settings.format,
        rotation=settings.rotation,
        retention=settings.retention,
        compression="zip",
        backtrace=True,
        diagnose=False,
    )
    
    logger.info("Logging configured", level=settings.level, file=str(log_file))


def get_logger(name: str):
    """Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__).
    
    Returns:
        Configured logger instance.
    """
    return logger.bind(name=name)