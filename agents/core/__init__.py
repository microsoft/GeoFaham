# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Core Module

Foundation components for the multi-agent system:
- Configuration management
- Constants and type definitions
- Custom exceptions
- Logging setup
- Response storage
"""

from agents.core.constants import AGENT_NAMES
from agents.core.exceptions import (
    GeoFahamError,
    ConfigurationError,
    DatabaseError,
    QueryExecutionError,
    GeoJSONError,
    GeoJSONParseError,
    AgentError,
    ResponseStoreError,
    ResponseNotFoundError,
    ArtifactNotFoundError,
)
from agents.core.types import (
    SavedArtifact,
    GeoFahamToolResponse,
    ResponseStoreEntry,
    ResponseType,
    DataType,
    ArtifactFormat,
)
from agents.core.config import (
    AgentsConfig,
    AzureOpenAIConfig,
    DatabaseConfig,
    OSMConfig,
    PathsConfig,
    ModelSpec,
    QueryConfig,
    get_config,
    reset_config,
    get_export_dir,
    get_response_store_path,
    get_team_state_path,
)
from agents.core.response_store import (
    ResponseStore,
    get_response_store,
    reset_response_store,
    get_available_responses,
    resolve_response_ids,
)
from agents.core.logging import get_logger, setup_logging

__all__ = [
    # Constants
    "AGENT_NAMES",
    # Exceptions
    "GeoFahamError",
    "ConfigurationError", 
    "DatabaseError",
    "QueryExecutionError",
    "GeoJSONError",
    "GeoJSONParseError",
    "AgentError",
    "ResponseStoreError",
    "ResponseNotFoundError",
    "ArtifactNotFoundError",
    # Types
    "SavedArtifact",
    "GeoFahamToolResponse",
    "ResponseStoreEntry",
    "ResponseType",
    "DataType",
    "ArtifactFormat",
    # Config
    "AgentsConfig",
    "AzureOpenAIConfig",
    "DatabaseConfig",
    "OSMConfig",
    "PathsConfig",
    "ModelConfig",
    "QueryConfig",
    "get_config",
    "reset_config",
    "get_export_dir",
    "get_response_store_path",
    "get_team_state_path",
    # Response Store
    "ResponseStore",
    "get_response_store",
    "reset_response_store",
    "get_available_responses",
    "resolve_response_ids",
    # Logging
    "get_logger",
    "setup_logging",
]
