# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test Raster Ops Agent

Run: python -m tests.test_raster_agent
"""

import json
from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client
from agents.raster_ops_agent import create_raster_ops_agent


def test_create_agent():
    """Test creating the raster ops agent."""
    print("=" * 60)
    print("Testing create_raster_ops_agent()")
    print("=" * 60)
    
    config = get_config()
    model = config.get_agent_model("RASTER_AGENT")
    print(f"Using model: {model}")
    
    client = init_model_client(model=model)
    agent = create_raster_ops_agent(client)
    
    print(f"✓ Agent created: {agent.name}")
    print(f"✓ Tools: {[t.name for t in agent._tools]}")
    print(f"✓ Max tool iterations: {agent._max_tool_iterations}")
    print(f"✓ Description: {agent.description[:100]}...")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("RASTER OPS AGENT TESTS")
    print("=" * 60 + "\n")
    
    test_create_agent()
    
    # Note: Testing execute_custom_raster_code requires STAC items input
    # which needs a full pipeline test
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
