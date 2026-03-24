# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
RasterOps Agent Assistant
"""

from autogen_agentchat.agents import AssistantAgent
from autogen_core.models import ChatCompletionClient
from autogen_core.tools import FunctionTool

from agents.raster_ops_agent.tools import execute_custom_raster_code
from agents.raster_ops_agent._prompts import SYS_PROMPT
from agents.core.response_store import get_available_responses
from agents.core.constants import AGENT_NAMES

DESCRIPTION = """Performs raster analysis (indices, change detection, classification) on STAC items via Python code generation. Requires stac_agent output. Outputs COG rasters and GeoJSON."""

DESCRIPTION_V0 = """
Executes raster analysis on satellite imagery from STAC Agent using Python code generation.

**Inputs:**
    - STAC items (JSON whole output from STAC Agent containing satellite imagery metadata) including the bounding box.
    - Analysis type: NDVI, burn severity, flood extent, change detection, damage assessment, recovery analysis, temporal timeline analysis etc.
    - Temporal scope: Single date or dual-date (pre/post disaster change detection, post-disaster recovery analysis etc)
    - Optional: Vector boundaries, statistical aggregation regions
**Outputs:**
    - Raster results (COG format) for map visualization
    - Vector results (GeoJSON) for classified zones or extracted features
    - Statistics (summary metrics, zonal stats, change percentages)
**Capabilities:**
    - Change detection (pre/post disaster change detection)
    - Spectral indices (vegetation indices, burn severity indices, water indices)
    - Classification (burn severity, flood extent, damage levels)
    - Temporal aggregation (mean, median, max across time series)
    - Zonal statistics (aggregate raster values by vector boundaries)
    - Raster algebra (band math, masking, thresholding)
    - Temporal timeline analysis
**Key Features:**
    - Generates Python code (xarray, numpy, geopandas, scipy) for any raster analysis
    - Handles multi-temporal satellite imagery automatically
    - Supports dual-date analysis for disaster damage assessment
    - Outputs Cloud-Optimized GeoTIFFs for efficient map rendering

Note: While giving me the instructions, do not explicity tell what indices etc should I use, I am intellgent engouh to decide that. Unless I am making repeatedly mistakes.
"""


def create_raster_ops_agent(
    model_client: ChatCompletionClient,
    agent_name: str = AGENT_NAMES["RASTER_AGENT"]
) -> AssistantAgent:
    """
    Create the RasterOps Agent for raster data processing and analysis.
    
    Args:
        model_client: The LLM client for the agent
        agent_name: Name of the agent (default: "raster_ops_agent")
    
    Returns:
        AssistantAgent configured for raster operations
    """
    
    agent = AssistantAgent(
        name=agent_name,
        model_client=model_client,
        tools=[
            FunctionTool(
                name="execute_custom_raster_code",
                func=execute_custom_raster_code,
                description=execute_custom_raster_code.__doc__,
            ),
            FunctionTool(
                name="get_available_responses",
                func=get_available_responses,
                description=get_available_responses.__doc__,
            ),
        ],
        max_tool_iterations=6,
        system_message=SYS_PROMPT,
        description=DESCRIPTION,
        reflect_on_tool_use=True
    )
    
    return agent
