# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Constants

Centralized constants for the multi-agent system.
All agent names, magic values, and shared constants are defined here.
"""

from typing import Final

# =============================================================================
# AGENT NAME DEFINITIONS
# =============================================================================

AGENT_NAMES: Final[dict[str, str]] = {
    "VECTOR_AGENT": "postgis_agent",
    "MAPS_AGENT": "osm_map_agent",  # Consistent with actual agent name
    "STAC_AGENT": "stac_agent",
    "RASTER_AGENT": "raster_ops_agent",
    "USER_PROXY": "user",
}

# Reverse mapping for lookups
AGENT_NAME_TO_KEY: Final[dict[str, str]] = {v: k for k, v in AGENT_NAMES.items()}

# =============================================================================
# DATA PROCESSING LIMITS
# =============================================================================

MAX_DATA_ROWS: Final[int] = 100
MAX_RESPONSE_ROWS: Final[int] = 50
DEFAULT_PAGE_SIZE: Final[int] = 50
MAX_RESPONSE_SIZE_BYTES: Final[int] = 500_000  # 500KB max for response data content

# =============================================================================
# DATABASE CONNECTION DEFAULTS
# =============================================================================

DB_POOL_MIN_CONNECTIONS: Final[int] = 1
DB_POOL_MAX_CONNECTIONS: Final[int] = 20

# =============================================================================
# GEOMETRY CONSTANTS
# =============================================================================

POINT_TYPES: Final[frozenset[str]] = frozenset({"Point", "MultiPoint"})
LINE_TYPES: Final[frozenset[str]] = frozenset({"LineString", "MultiLineString"})
POLYGON_TYPES: Final[frozenset[str]] = frozenset({"Polygon", "MultiPolygon"})
ALL_GEOMETRY_TYPES: Final[frozenset[str]] = POINT_TYPES | LINE_TYPES | POLYGON_TYPES

# Geometry type to category mapping
GEOMETRY_CATEGORIES: Final[dict[str, str]] = {
    "Point": "points",
    "MultiPoint": "points",
    "LineString": "lines",
    "MultiLineString": "lines",
    "Polygon": "polygons",
    "MultiPolygon": "polygons",
}

# =============================================================================
# FILE FORMATS
# =============================================================================

GEOJSON_CONTENT_TYPE: Final[str] = "application/geo+json"
COG_CONTENT_TYPE: Final[str] = "image/tiff; application=geotiff; profile=cloud-optimized"

# =============================================================================
# CRS CONSTANTS
# =============================================================================

DEFAULT_CRS: Final[str] = "EPSG:4326"
WEB_MERCATOR_CRS: Final[str] = "EPSG:3857"

# =============================================================================
# API VERSIONS (Azure OpenAI)
# =============================================================================

DEFAULT_API_VERSION: Final[str] = "2024-08-01-preview"
GPT5_API_VERSION: Final[str] = "2025-04-01-preview"
