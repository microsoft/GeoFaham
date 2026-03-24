# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Test Vector Agent

Run: python -m tests.test_vector_agent
"""

import asyncio
import json
from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client
from agents.vector_agent import create_vector_agent, VectorQueryExecutor


def test_executor_schema():
    """Test that we can get database schema."""
    print("=" * 60)
    print("Testing VectorQueryExecutor.get_schema_info()")
    print("=" * 60)
    
    executor = VectorQueryExecutor()
    try:
        schema = executor.get_schema_info()
        schema_data = json.loads(schema)
        print(f"✓ Got schema with {len(schema_data)} columns")
        
        # Show sample
        tables = set(row['table_name'] for row in schema_data)
        print(f"✓ Tables: {tables}")
    finally:
        executor.close()


def test_executor_disasters():
    """Test that we can list disasters."""
    print("\n" + "=" * 60)
    print("Testing VectorQueryExecutor.get_list_of_disasters()")
    print("=" * 60)
    
    executor = VectorQueryExecutor()
    try:
        disasters = executor.get_list_of_disasters()
        disasters_data = json.loads(disasters)
        print(f"✓ Got {len(disasters_data)} disasters")
        
        if disasters_data:
            print(f"✓ Sample: {disasters_data[0].get('name', 'N/A')}")
    finally:
        executor.close()


async def test_executor_query():
    """Test executing a simple query."""
    print("\n" + "=" * 60)
    print("Testing VectorQueryExecutor.execute_query()")
    print("=" * 60)
    
    executor = VectorQueryExecutor()
    try:
        result = await executor.execute_query(
            query="SELECT id, name, disaster_type FROM disasters LIMIT 3",
            return_layer=False,
            results_description="Test query for disasters"
        )
        result_data = json.loads(result)
        print(f"✓ Query executed, type: {result_data.get('type')}")
        print(f"✓ Data rows: {len(result_data.get('data', []))}")
    finally:
        executor.close()


def test_create_agent():
    """Test creating the vector agent."""
    print("\n" + "=" * 60)
    print("Testing create_vector_agent()")
    print("=" * 60)
    
    config = get_config()
    model = config.get_agent_model("VECTOR_AGENT")
    print(f"Using model: {model}")
    
    client = init_model_client(model=model)
    agent = create_vector_agent(client, AGENT_NAMES["VECTOR_AGENT"])
    
    print(f"✓ Agent created: {agent.name}")
    print(f"✓ Tools: {[t.name for t in agent._tools]}")
    print(f"✓ Description: {agent.description[:100]}...")


async def test_agent_tool_call():
    """Test agent making a tool call."""
    print("\n" + "=" * 60)
    print("Testing agent tool call (execute_query)")
    print("=" * 60)
    
    config = get_config()
    client = init_model_client(model=config.get_agent_model("VECTOR_AGENT"))
    agent = create_vector_agent(client, AGENT_NAMES["VECTOR_AGENT"])
    
    # Find the execute_query tool
    execute_query_tool = None
    for tool in agent._tools:
        if tool.name == "execute_query":
            execute_query_tool = tool
            break
    
    if execute_query_tool:
        result = await execute_query_tool.run_json(
            {
                "query": "SELECT COUNT(*) as count FROM disasters",
                "return_layer": False,
                "results_description": "Count of disasters"
            },
            cancellation_token=None
        )
        result_data = json.loads(result)
        print(f"✓ Tool executed, type: {result_data.get('type')}")
        print(f"✓ Summary: {result_data.get('summary')}")
        if result_data.get('data'):
            print(f"✓ Result: {result_data['data']}")
    else:
        print("✗ execute_query tool not found")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("VECTOR AGENT TESTS")
    print("=" * 60 + "\n")
    
    # Sync tests
    test_executor_schema()
    test_executor_disasters()
    test_create_agent()
    
    # Async tests
    asyncio.run(test_executor_query())
    asyncio.run(test_agent_tool_call())
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
