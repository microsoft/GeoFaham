# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM Maps Agent Assistant - Factory function for creating the OSM-based geospatial agent.

This agent provides OpenStreetMap-based tools for extracting geographic features
that are not available through Azure Maps, making it especially useful for
disaster damage assessment.
"""

from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool

from agents.maps_agent.tools import (
    get_roads,
    get_buildings,
    get_waterways,
    get_bridges,
    get_pois,
    get_admin_boundary,
    get_neighborhoods,
    get_landuse,
    get_natural_features,
    get_infrastructure,
    get_features_by_tags,
    get_address_coordinates,
    get_place_bounding_box,
    search_feature_by_name,
    reverse_geocode,
)
from agents.maps_agent._prompts import SYS_PROMPT
from agents.core.response_store import get_available_responses
from agents.core.constants import AGENT_NAMES


_DESCRIPTION = """Extracts OpenStreetMap features (POIs, roads, buildings, waterways, boundaries) as GeoJSON. One feature type per call. Accepts place names or GeoJSON AOI."""

# Use consistent agent name from constants
_AGENT_NAME = AGENT_NAMES["MAPS_AGENT"]


def create_map_search_agent(client):
    """
    Create an OSM Maps Agent with OpenStreetMap-based geospatial tools.
    
    Args:
        client: The model client (e.g., Azure OpenAI client)
        
    Returns:
        AssistantAgent configured with OSM map tools
    """
    
    osm_map_agent = AssistantAgent(
        name=_AGENT_NAME,
        model_client=client,
        description=_DESCRIPTION,
        tools=[
            FunctionTool(
                name="get_roads",
                func=get_roads,
                description=get_roads.__doc__,
            ),
            FunctionTool(
                name="get_buildings",
                func=get_buildings,
                description=get_buildings.__doc__,
            ),
            FunctionTool(
                name="get_waterways",
                func=get_waterways,
                description=get_waterways.__doc__,
            ),
            FunctionTool(
                name="get_bridges",
                func=get_bridges,
                description=get_bridges.__doc__,
            ),
            FunctionTool(
                name="get_pois",
                func=get_pois,
                description=get_pois.__doc__,
            ),
            FunctionTool(
                name="get_admin_boundary",
                func=get_admin_boundary,
                description=get_admin_boundary.__doc__,
            ),
            FunctionTool(
                name="get_neighborhoods",
                func=get_neighborhoods,
                description=get_neighborhoods.__doc__,
            ),
            FunctionTool(
                name="get_landuse",
                func=get_landuse,
                description=get_landuse.__doc__,
            ),
            FunctionTool(
                name="get_natural_features",
                func=get_natural_features,
                description=get_natural_features.__doc__,
            ),
            FunctionTool(
                name="get_infrastructure",
                func=get_infrastructure,
                description=get_infrastructure.__doc__,
            ),
            FunctionTool(
                name="get_features_by_tags",
                func=get_features_by_tags,
                description=get_features_by_tags.__doc__,
            ),
            FunctionTool(
                name="get_address_coordinates",
                func=get_address_coordinates,
                description=get_address_coordinates.__doc__,
            ),
            FunctionTool(
                name="get_place_bounding_box",
                func=get_place_bounding_box,
                description=get_place_bounding_box.__doc__,
            ),
            FunctionTool(
                name="search_feature_by_name",
                func=search_feature_by_name,
                description=search_feature_by_name.__doc__,
            ),
            FunctionTool(
                name="reverse_geocode",
                func=reverse_geocode,
                description=reverse_geocode.__doc__,
            ),
            FunctionTool(
                name="get_available_responses",
                func=get_available_responses,
                description=get_available_responses.__doc__,
            ),
        ],
        system_message=SYS_PROMPT,
        max_tool_iterations=3,
        reflect_on_tool_use=True,
    )
    
    return osm_map_agent
