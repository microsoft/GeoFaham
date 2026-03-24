# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test Maps Agent

Run: python -m tests.test_maps_agent
"""

import asyncio
import json
from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client
from agents.maps_agent.assistant import create_map_search_agent
from agents.maps_agent.tools import (
    get_address_coordinates,
    get_place_bounding_box,
    get_pois,
    get_admin_boundary,
)


async def test_geocoding():
    """Test geocoding an address."""
    print("=" * 60)
    print("Testing get_address_coordinates()")
    print("=" * 60)
    
    result = await get_address_coordinates("St. Louis, Missouri, USA")
    result_data = json.loads(result)
    
    print(f"Type: {result_data.get('type')}")
    if result_data.get('type') == 'error':
        print(f"✗ Error: {result_data.get('error_message')}")
    else:
        print(f"✓ Summary: {result_data.get('summary')}")
        if result_data.get('data'):
            print(f"✓ Data: {result_data['data'][:2]}...")


async def test_bounding_box():
    """Test getting place bounding box."""
    print("\n" + "=" * 60)
    print("Testing get_place_bounding_box()")
    print("=" * 60)
    
    result = await get_place_bounding_box("Central West End, St. Louis, Missouri, USA")
    result_data = json.loads(result)
    
    print(f"Type: {result_data.get('type')}")
    if result_data.get('type') == 'error':
        print(f"✗ Error: {result_data.get('error_message')}")
    else:
        print(f"✓ Summary: {result_data.get('summary')}")


async def test_pois():
    """Test getting POIs."""
    print("\n" + "=" * 60)
    print("Testing get_pois()")
    print("=" * 60)
    
    result = await get_pois(
        place_name="Central West End, St. Louis, Missouri, USA",
        category="healthcare"
    )
    result_data = json.loads(result)
    
    print(f"Type: {result_data.get('type')}")
    if result_data.get('type') == 'error':
        print(f"✗ Error: {result_data.get('error_message')}")
    else:
        print(f"✓ Summary: {result_data.get('summary')}")
        if result_data.get('artifact'):
            print(f"✓ Features: {result_data['artifact'].get('features_count')}")


async def test_admin_boundary():
    """Test getting admin boundary."""
    print("\n" + "=" * 60)
    print("Testing get_admin_boundary()")
    print("=" * 60)
    
    result = await get_admin_boundary(
        place_name="St. Louis, Missouri, USA",
        admin_level=8  # City level
    )
    result_data = json.loads(result)
    
    print(f"Type: {result_data.get('type')}")
    if result_data.get('type') == 'error':
        print(f"✗ Error: {result_data.get('error_message')}")
    else:
        print(f"✓ Summary: {result_data.get('summary')}")
        if result_data.get('artifact'):
            print(f"✓ Path: {result_data['artifact'].get('path')}")


def test_create_agent():
    """Test creating the maps agent."""
    print("\n" + "=" * 60)
    print("Testing create_map_search_agent()")
    print("=" * 60)
    
    config = get_config()
    model = config.get_agent_model("MAPS_AGENT")
    print(f"Using model: {model}")
    
    client = init_model_client(model=model)
    agent = create_map_search_agent(client)
    
    print(f"✓ Agent created: {agent.name}")
    print(f"✓ Tools ({len(agent._tools)}): {[t.name for t in agent._tools]}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MAPS AGENT TESTS")
    print("=" * 60 + "\n")
    
    # Sync tests
    test_create_agent()
    
    # Async tests
    asyncio.run(test_geocoding())
    asyncio.run(test_bounding_box())
    # These may take longer as they fetch from OSM
    # asyncio.run(test_pois())
    # asyncio.run(test_admin_boundary())
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
