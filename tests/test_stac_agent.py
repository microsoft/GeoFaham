# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test STAC Agent

Run: python -m tests.test_stac_agent
"""

import asyncio
import json
from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client
from agents.stac_agent.assistant import create_stac_agent
from agents.stac_agent.tools import get_collection_details


async def test_collection_details():
    """Test getting collection details."""
    print("=" * 60)
    print("Testing get_collection_details()")
    print("=" * 60)
    
    result = await get_collection_details("sentinel-2-l2a")
    result_data = json.loads(result)
    
    print(f"Type: {result_data.get('type')}")
    if result_data.get('type') == 'error':
        print(f"✗ Error: {result_data.get('error_message')}")
    else:
        print(f"✓ Summary: {result_data.get('summary', '')[:200]}...")


def test_create_agent():
    """Test creating the STAC agent."""
    print("\n" + "=" * 60)
    print("Testing create_stac_agent()")
    print("=" * 60)
    
    config = get_config()
    model = config.get_agent_model("STAC_AGENT")
    print(f"Using model: {model}")
    
    client = init_model_client(model=model)
    agent = create_stac_agent(client)
    
    print(f"✓ Agent created: {agent.name}")
    print(f"✓ Tools: {[t.name for t in agent._tools]}")
    print(f"✓ Description: {agent.description[:100]}...")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("STAC AGENT TESTS")
    print("=" * 60 + "\n")
    
    # Sync tests
    test_create_agent()
    
    # Async tests
    asyncio.run(test_collection_details())
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
