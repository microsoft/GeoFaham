# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM Maps Agent - OpenStreetMap-based geospatial data extraction tools.

This agent provides tools for extracting various geographic features from OpenStreetMap,
including roads, rivers, bridges, buildings, and other infrastructure critical for 
disaster damage assessment. Unlike Azure Maps, OSM provides comprehensive access to:

- Roads (highways, primary, secondary, tertiary, residential, etc.)
- Waterways (rivers, streams, canals, drainage)
- Bridges and tunnels
- Buildings (residential, commercial, industrial, etc.)
- Land use areas (forests, parks, farmland, etc.)
- Points of Interest (hospitals, schools, emergency services, etc.)
- Administrative boundaries at various levels
- Natural features (coastlines, forests, wetlands, etc.)
"""

from agents.maps_agent.tools import (
    get_roads,
    get_buildings,
    get_waterways,
    get_bridges,
    get_pois,
    get_admin_boundary,
    get_landuse,
    get_natural_features,
    get_infrastructure,
    get_features_by_tags,
    get_address_coordinates,
    get_place_bounding_box,
)

from agents.maps_agent._prompts import SYS_PROMPT
from agents.maps_agent.assistant import create_map_search_agent

__all__ = [
    # Agent factory
    "create_map_search_agent",
    # Tools
    "get_roads",
    "get_buildings", 
    "get_waterways",
    "get_bridges",
    "get_pois",
    "get_admin_boundary",
    "get_landuse",
    "get_natural_features",
    "get_infrastructure",
    "get_features_by_tags",
    "get_address_coordinates",
    "get_place_bounding_box",
    # Prompts
    "SYS_PROMPT",
]
