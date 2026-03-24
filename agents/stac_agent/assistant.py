# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
STAC Agent Assistant - Satellite imagery retrieval from Microsoft Planetary Computer
"""

import os
from datetime import datetime
from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool
from agents.stac_agent.tools import execute_stac_search, get_collection_details, AGENT_NAME
from agents.stac_agent._prompts import STAC_SYSTEM_PROMPT
from agents.core.response_store import get_available_responses


_DESCRIPTION = """Retrieves satellite imagery, population data (WorldPop), and land cover from Microsoft Planetary Computer. Requires AOI GeoJSON file. Outputs STAC items for raster_ops_agent or map mosaics."""

_DESCRIPTION_V0 = """
Retrieves satellite imagery from Microsoft Planetary Computer (113+ collections, global coverage).

**Inputs:**
- Location GeoJSON file from other agents or uploaded by user
- Datetime/date range of the event
- Analysis type: Desired GIS indices or analysis (e.g., NDVI, burn severity, flood extent)
- Damage assessment requirements: e.g., cropland analysis, population exposure
- Optional: Disaster type for context-aware collection selection

**Important:** If the analysis purpose is unclear or conflicting (e.g., "wildfire + NDVI" without specifying vegetation health vs burn severity), I will ask for clarification before proceeding—unless the user only wants visualization.

**Outputs:**
- "fetch" mode: Raw STAC items as JSON for raster analysis (supports dual-date pre/post comparison)
- "show" mode: Mosaic for map visualization (single date only)

**Key Features:**
- Automatic collection fallback (2-3 options in priority order) if the primary collection lacks data
- Multi-fetch capability: Retrieve multiple imagery types in a single call (e.g., pre/post disaster imagery for flood extent, landslide extent, and croplands)
- Smart filtering: Cloud cover for optical imagery, confidence thresholds for fire detection
- Historical (1982+) and near real-time (daily) coverage
- Band selection based on user query (true color, SWIR, NDVI, thermal) in show mode
- Automatic date inference for pre-disaster, during-disaster, and post-disaster imagery when disaster start/end dates are provided
- Population data from WorldPop 2020 (static, not temporal): Returns population count with statistics and raster file for the area of interest
- LULC maps for land use and land cover classification
"""

def create_stac_agent(client):
    """
    Create STAC agent for satellite imagery retrieval.
    
    Args:
        client: LLM client for agent reasoning
        
    Returns:
        AssistantAgent configured for STAC queries
    """
    
    stac_agent = AssistantAgent(
        name=AGENT_NAME,
        model_client=client,
        description=_DESCRIPTION,
        tools=[
            FunctionTool(
                name="get_collection_details",
                func=get_collection_details,
                description=get_collection_details.__doc__
            ),
            FunctionTool(
                name="execute_stac_search",
                func=execute_stac_search,
                description=execute_stac_search.__doc__
            ),
            FunctionTool(
                name="get_available_responses",
                func=get_available_responses,
                description=get_available_responses.__doc__
            )
        ],
        system_message=STAC_SYSTEM_PROMPT,
        max_tool_iterations=3,  # get_collection_details, execute_stac_search, optionally retry
        reflect_on_tool_use=False,
    )
    
    return stac_agent
