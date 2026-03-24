# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Team Module

Team creation and initialization utilities for the multi-agent system.
"""

import os
import json
import aiofiles
from typing import Awaitable, Callable, Optional

from autogen_agentchat.agents import UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core import CancellationToken

from agents.base.client import init_model_client
from agents.core.config import get_config, get_team_state_path
from agents.core.constants import AGENT_NAMES
from agents.core.logging import get_logger

logger = get_logger("team")


async def get_team(
    user_input_func: Callable[[str, Optional[CancellationToken]], Awaitable[str]],
):
    """
    Create and initialize the GeoFaham multi-agent team.
    
    Args:
        user_input_func: Async function for getting user input
        
    Returns:
        Configured GeoFahamGroupChat team instance
    """
    # Import here to avoid circular imports
    from agents.orchestrator_agent.group_chat import GeoFahamGroupChat
    from agents.vector_agent import create_vector_agent
    from agents.maps_agent.assistant import create_map_search_agent
    from agents.stac_agent.assistant import create_stac_agent
    from agents.raster_ops_agent import create_raster_ops_agent
    
    config = get_config()
    
    # Create sub-agents with models from config
    postgis_agent = create_vector_agent(
        init_model_client(model=config.get_agent_model("VECTOR_AGENT")), 
        AGENT_NAMES["VECTOR_AGENT"]
    )
    map_search_agent = create_map_search_agent(
        init_model_client(model=config.get_agent_model("MAPS_AGENT"))
    )
    stac_agent = create_stac_agent(
        init_model_client(model=config.get_agent_model("STAC_AGENT"))
    )
    raster_ops_agent = create_raster_ops_agent(
        init_model_client(model=config.get_agent_model("RASTER_AGENT"))
    )
    
    user_proxy = UserProxyAgent(
        name=AGENT_NAMES["USER_PROXY"],
        input_func=user_input_func,
    )
    
    termination = TextMentionTermination("bye")
    
    planner_model = config.get_agent_model("ORCHESTRATOR_PLANNER")
    progress_model = config.get_agent_model("ORCHESTRATOR_PROGRESS")
    
    team = GeoFahamGroupChat(
        [
            postgis_agent,
            map_search_agent,
            stac_agent,
            raster_ops_agent,
            user_proxy
        ],
        model_client=init_model_client(model=planner_model),
        model_client2=init_model_client(model=progress_model),
        termination_condition=termination,
    )
    
    # Load state from file if exists
    state_path = get_team_state_path()
    if not os.path.exists(state_path):
        return team
        
    try:
        async with aiofiles.open(state_path, "r") as file:
            state = json.loads(await file.read())
        await team.load_state(state)
        logger.info("Team state loaded successfully.")
        return team
    except Exception as e:
        logger.error(f"Error loading team state: {e}")
        return team


def create_single_agent(agent_name: str):
    """
    Create a single agent by name.
    
    Args:
        agent_name: One of 'postgis', 'map_search', 'stac', 'raster_ops'
        
    Returns:
        The requested agent instance
    """
    from agents.vector_agent import create_vector_agent
    from agents.maps_agent.assistant import create_map_search_agent
    from agents.stac_agent.assistant import create_stac_agent
    from agents.raster_ops_agent import create_raster_ops_agent
    
    config = get_config()
    
    agent_configs = {
        "postgis": ("VECTOR_AGENT", create_vector_agent),
        "map_search": ("MAPS_AGENT", create_map_search_agent),
        "stac": ("STAC_AGENT", create_stac_agent),
        "raster_ops": ("RASTER_AGENT", create_raster_ops_agent),
    }
    
    if agent_name not in agent_configs:
        raise ValueError(f"Unknown agent name: {agent_name}. Available: {list(agent_configs.keys())}")
    
    agent_key, factory = agent_configs[agent_name]
    client = init_model_client(model=config.get_agent_model(agent_key))
    
    return factory(client)
