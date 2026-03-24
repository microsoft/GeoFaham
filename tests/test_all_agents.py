# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test All Agents

Run: python -m tests.test_all_agents
"""

import asyncio
from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client
from agents.vector_agent import create_vector_agent
from agents.maps_agent.assistant import create_map_search_agent
from agents.stac_agent.assistant import create_stac_agent
from agents.raster_ops_agent import create_raster_ops_agent


def test_all_agents_creation():
    """Test that all agents can be created."""
    print("=" * 60)
    print("Testing All Agent Creation")
    print("=" * 60)
    
    config = get_config()
    
    agents_to_test = [
        ("VECTOR_AGENT", create_vector_agent, AGENT_NAMES["VECTOR_AGENT"]),
        ("MAPS_AGENT", create_map_search_agent, None),
        ("STAC_AGENT", create_stac_agent, None),
        ("RASTER_AGENT", create_raster_ops_agent, None),
    ]
    
    for agent_key, factory, name_arg in agents_to_test:
        model = config.get_agent_model(agent_key)
        client = init_model_client(model=model)
        
        try:
            if name_arg:
                agent = factory(client, name_arg)
            else:
                agent = factory(client)
            
            print(f"✓ {agent_key}: {agent.name}")
            print(f"  Model: {model}")
            print(f"  Tools: {len(agent._tools)}")
        except Exception as e:
            print(f"✗ {agent_key}: {e}")


def test_config():
    """Test configuration."""
    print("\n" + "=" * 60)
    print("Testing Configuration")
    print("=" * 60)
    
    config = get_config()
    
    print(f"Default model: {config.default_model}")
    print(f"Reasoning model: {config.reasoning_model}")
    print()
    print("Agent models:")
    for key in ["VECTOR_AGENT", "MAPS_AGENT", "STAC_AGENT", "RASTER_AGENT", 
                "ORCHESTRATOR_PLANNER", "ORCHESTRATOR_PROGRESS"]:
        print(f"  {key}: {config.get_agent_model(key)}")


def test_imports():
    """Test all imports work."""
    print("\n" + "=" * 60)
    print("Testing Imports")
    print("=" * 60)
    
    try:
        from agents import (
            AGENT_NAMES,
            get_config,
            get_team,
            init_model_client,
            GeoFahamToolResponse,
            get_response_store,
        )
        print("✓ agents package imports")
        
        from agents.core.exceptions import (
            GeoFahamError,
            DatabaseError,
            QueryExecutionError,
        )
        print("✓ exceptions imports")
        
        from agents.shared.geojson import results_to_geojson, generate_response_id
        print("✓ shared imports")
        
        from agents.base.agent import AgentBuilder
        print("✓ base imports")
        
    except ImportError as e:
        print(f"✗ Import error: {e}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("ALL AGENTS TEST SUITE")
    print("=" * 60 + "\n")
    
    test_imports()
    test_config()
    test_all_agents_creation()
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
