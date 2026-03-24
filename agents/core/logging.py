# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Logging Configuration

Consistent logging setup for the multi-agent system.
"""

import logging
import sys
from typing import Optional

# Default format for all GeoFaham loggers
DEFAULT_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Logger names
ROOT_LOGGER_NAME = "geofaham"
AGENT_LOGGER_PREFIX = "geofaham.agents"

# Noisy loggers to suppress by default
NOISY_LOGGERS = [
    "azure.identity",
    "azure.core.pipeline.policies.http_logging_policy",
    "httpx",
    "httpcore",
]


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    date_format: Optional[str] = None,
    stream: Optional[object] = None,
    suppress_noisy: bool = True,
) -> logging.Logger:
    """
    Setup logging for GeoFaham.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string (default: DEFAULT_FORMAT)
        date_format: Custom date format (default: DEFAULT_DATE_FORMAT)
        stream: Output stream (default: sys.stderr)
        suppress_noisy: Suppress verbose Azure/HTTP loggers (default: True)
    
    Returns:
        The root GeoFaham logger
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    
    # Avoid adding multiple handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(level)
    
    formatter = logging.Formatter(
        fmt=format_string or DEFAULT_FORMAT,
        datefmt=date_format or DEFAULT_DATE_FORMAT,
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Suppress noisy Azure/HTTP loggers
    if suppress_noisy:
        for noisy_logger in NOISY_LOGGERS:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        name: Module name (will be prefixed with geofaham.)
    
    Returns:
        Logger instance
    
    Example:
        logger = get_logger("vector.executor")
        # Returns logger named "geofaham.vector.executor"
    """
    if name.startswith(ROOT_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    Get a logger for a specific agent.
    
    Args:
        agent_name: Agent name (e.g., "postgis_agent")
    
    Returns:
        Logger instance for the agent
    """
    return logging.getLogger(f"{AGENT_LOGGER_PREFIX}.{agent_name}")


class LoggerMixin:
    """Mixin class that provides a logger property."""
    
    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return get_logger(self.__class__.__module__)


# Initialize root logger on import
_root_logger = setup_logging()
