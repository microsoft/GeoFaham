# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Agents Package

Multi-agent system for geospatial data analysis and disaster assessment.

Package Structure:
- core/: Foundation (config, types, exceptions, logging, response_store)
- shared/: Common utilities (geojson, serialization, analysis)
- base/: Agent factory protocol and model client factory
- vector_agent/: PostGIS queries
- maps_agent/: OSM feature extraction
- stac_agent/: Satellite imagery
- raster_ops_agent/: Raster processing
- orchestrator_agent/: Multi-agent coordination
"""

# Core exports
from agents.core.constants import AGENT_NAMES
from agents.core.config import (
    AgentsConfig,
    get_config,
    reset_config,
    get_export_dir,
    get_response_store_path,
    get_team_state_path,
)
from agents.core.types import (
    SavedArtifact,
    GeoFahamToolResponse,
    ResponseType,
    DataType,
    ArtifactFormat,
)
from agents.core.exceptions import GeoFahamError
from agents.core.response_store import (
    ResponseStore,
    get_response_store,
    reset_response_store,
    get_available_responses,
)
from agents.core.logging import get_logger

# Base exports
from agents.base.client import init_model_client

# Team exports
from agents.team import get_team, create_single_agent

# Shared utilities
from agents.shared.geojson import results_to_geojson, generate_response_id
from agents.shared.serialization import serialize_value

__all__ = [
    # Constants
    "AGENT_NAMES",
    # Config
    "AgentsConfig",
    "get_config",
    "reset_config",
    "get_export_dir",
    "get_response_store_path",
    "get_team_state_path",
    # Types
    "SavedArtifact",
    "GeoFahamToolResponse",
    "ResponseType",
    "DataType",
    "ArtifactFormat",
    # Exceptions
    "GeoFahamError",
    # Response Store
    "ResponseStore",
    "get_response_store",
    "reset_response_store",
    "get_available_responses",
    # Logging
    "get_logger",
    # Client
    "init_model_client",
    # Team
    "get_team",
    "create_single_agent",
    # Utilities
    "results_to_geojson",
    "generate_response_id",
    "serialize_value",
]