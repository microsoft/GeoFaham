# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM Maps Agent Tools - OpenStreetMap-based geospatial data extraction.

This module re-exports all map tools for backward compatibility.
Tools are organized into submodules:
- categories: Enums for filtering features
- feature_tools: Roads, buildings, waterways, bridges, POIs, landuse, natural, infrastructure
- geocoding_tools: Address geocoding, bounding boxes, admin boundaries, neighborhoods
"""

# Re-export categories
from agents.maps_agent.categories import (
    RoadCategory,
    BuildingCategory,
    WaterwayCategory,
    POICategory,
    LanduseCategory,
    NaturalCategory,
    InfrastructureCategory,
)

# Re-export feature extraction tools
from agents.maps_agent.feature_tools import (
    get_roads,
    get_buildings,
    get_waterways,
    get_bridges,
    get_pois,
    get_landuse,
    get_natural_features,
    get_infrastructure,
    get_features_by_tags,
)

# Re-export geocoding and boundary tools
from agents.maps_agent.geocoding_tools import (
    get_admin_boundary,
    get_neighborhoods,
    get_address_coordinates,
    get_place_bounding_box,
    search_feature_by_name,
    reverse_geocode,
)

__all__ = [
    # Categories
    "RoadCategory",
    "BuildingCategory",
    "WaterwayCategory",
    "POICategory",
    "LanduseCategory",
    "NaturalCategory",
    "InfrastructureCategory",
    # Feature tools
    "get_roads",
    "get_buildings",
    "get_waterways",
    "get_bridges",
    "get_pois",
    "get_landuse",
    "get_natural_features",
    "get_infrastructure",
    "get_features_by_tags",
    # Geocoding tools
    "get_admin_boundary",
    "get_neighborhoods",
    "get_address_coordinates",
    "get_place_bounding_box",
    "search_feature_by_name",
    "reverse_geocode",
]
