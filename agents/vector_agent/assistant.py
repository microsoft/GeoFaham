# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Vector Agent Assistant

Single-agent approach for PostGIS spatial queries using AssistantAgent
with tool reflection for error recovery.
"""

from autogen_agentchat.agents import AssistantAgent
from autogen_core.models import ChatCompletionClient
from autogen_core.tools import FunctionTool

from agents.vector_agent.tools import VectorQueryExecutor
from agents.vector_agent._prompts import build_system_prompt, DESCRIPTION
from agents.core.response_store import get_available_responses
from agents.core.constants import AGENT_NAMES


def create_vector_agent(
    model_client: ChatCompletionClient,
    agent_name: str = AGENT_NAMES["VECTOR_AGENT"]
) -> AssistantAgent:
    """
    Create the Vector Agent for PostGIS spatial queries.
    
    Uses single-agent pattern with:
    - max_tool_iterations for retry on errors
    - reflect_on_tool_use for error analysis and correction
    
    Args:
        model_client: The LLM client for the agent
        agent_name: Name of the agent (default: "vector_agent")
    
    Returns:
        AssistantAgent configured for vector/PostGIS operations
    """
    # Initialize query executor and fetch context
    executor = VectorQueryExecutor()
    schema_info = executor.get_schema_info()
    disasters_list, disasters_dict = executor.get_list_of_disasters(return_dict=True)
    
    # Build system prompt with injected context
    system_message = build_system_prompt(
        schema_info=schema_info,
        disasters_list=disasters_list
    )
    
    # Append available disasters to description for orchestrator visibility
    import json
    refined_disasters = json.dumps([
        {k: v for k, v in d.items() if "id" not in k and k not in ['updated_at']} 
        for d in disasters_dict
    ])
    full_description = DESCRIPTION + "\n\n**Available Disasters:**\n" + refined_disasters
    
    agent = AssistantAgent(
        name=agent_name,
        model_client=model_client,
        tools=[
            FunctionTool(
                name="execute_query",
                func=executor.execute_query,
                description=(
                    "Execute a PostGIS SELECT query. Returns GeoJSON layer or tabular data. "
                    "Use for queries without external GeoJSON. "
                    "Parameters: query (str), return_layer (bool), results_description (str), "
                    "geojson_paths (list, default []), property_keys (dict, default {}), "
                    "return_aggregated_data (bool, default False - set True for GROUP BY queries to get both layer and data table). "
                    "NOTE: When return_aggregated_data=True, only first 50 rows are returned in response (full data saved to artifact file). "
                    "Use ORDER BY to ensure most relevant rows appear first (e.g., ORDER BY damage_count DESC)."
                ),
            ),
            FunctionTool(
                name="execute_query_with_geojson",
                func=executor.execute_query_with_geojson,
                description=(
                    "Execute a PostGIS SELECT that uses external GeoJSON files for spatial joins. "
                    "Required when query contains {{GEOJSON_*_CTE}} placeholders. "
                    "Parameters: query (str), return_layer (bool), results_description (str), "
                    "response_ids (List[str], required - IDs from Inputs section; backend resolves paths/properties), "
                    "return_aggregated_data (bool, default False - set True for GROUP BY queries). "
                    "NOTE: When return_aggregated_data=True, only first 50 rows are returned in response (full data saved to artifact file). "
                    "Use ORDER BY to ensure most relevant rows appear first (e.g., ORDER BY damage_count DESC)."
                ),
            ),
            FunctionTool(
                name="create_buffer",
                func=executor.create_buffer,
                description=(
                    "Create buffer polygon(s) around input geometries. Use for 'within X distance of' queries. "
                    "Parameters: response_ids (List[str], required - source geometries from previous steps), "
                    "distance (float, required - buffer distance), "
                    "distance_unit (str, default 'kilometers' - options: 'kilometers', 'meters', 'miles'), "
                    "merge_results (bool, default True - merge all buffers into single polygon), "
                    "results_description (str, default 'Buffer polygon'). "
                    "Returns GeoJSON polygon that can be used as AOI for other agents."
                ),
            ),
            FunctionTool(
                name="get_available_responses",
                func=get_available_responses,
                description=get_available_responses.__doc__,
            ),
        ],
        max_tool_iterations=4,  # Allow retries on SQL errors
        reflect_on_tool_use=True,  # LLM analyzes tool results for error correction
        system_message=system_message,
        description=full_description,
    )
    
    return agent
