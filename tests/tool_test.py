# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Interactive Tool Call Tester for GeoFaham Agents

Test individual agent tools with custom parameters.
Useful for debugging tool behavior and validating configurations.

Usage:
    python -m tests.tool_test                         # Interactive mode
    python -m tests.tool_test --agent vector          # List tools for an agent
    python -m tests.tool_test --agent vector --tool execute_query  # Test specific tool
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Auto-load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on shell environment

from autogen_core import CancellationToken

from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client


# Tool definitions with sample inputs for testing
AGENT_TOOLS = {
    "vector": {
        "module": "agents.vector_agent",
        "factory": "create_vector_agent",
        "agent_key": "VECTOR_AGENT",
        "samples": {
            "execute_query": {
                "query": "SELECT id, name, disaster_type FROM disasters LIMIT 3",
                "return_layer": False,
                "results_description": "Sample disasters query"
            },
            "get_available_responses": {}
        }
    },
    "maps": {
        "module": "agents.maps_agent",
        "factory": "create_map_search_agent",
        "agent_key": "MAPS_AGENT",
        "samples": {
            "get_address_coordinates": {
                "address": "Seattle, WA"
            },
            "get_place_bounding_box": {
                "place_name": "Seattle"
            },
            "get_available_responses": {}
        }
    },
    "stac": {
        "module": "agents.stac_agent",
        "factory": "create_stac_agent",
        "agent_key": "STAC_AGENT",
        "samples": {
            "get_collection_details": {
                "collection_id": "sentinel-2-l2a"
            },
            "get_available_responses": {}
        }
    },
    "raster": {
        "module": "agents.raster_ops_agent",
        "factory": "create_raster_ops_agent",
        "agent_key": "RASTER_AGENT",
        "samples": {
            "get_available_responses": {}
        }
    },
}


def create_agent_for_tools(agent_type: str):
    """Create an agent to access its tools."""
    config = get_config()
    agent_info = AGENT_TOOLS[agent_type]
    
    model = config.get_agent_model(agent_info["agent_key"])
    client = init_model_client(model=model)
    
    module = __import__(agent_info["module"], fromlist=[agent_info["factory"]])
    factory = getattr(module, agent_info["factory"])
    
    return factory(client), model


def list_tools(agent) -> List[Dict[str, Any]]:
    """List all tools for an agent with their signatures."""
    tools = []
    for tool in agent._tools:
        tool_info = {
            "name": tool.name,
            "description": (tool.description or "")[:100] + "..." if tool.description and len(tool.description) > 100 else tool.description,
        }
        
        # Try to get schema
        if hasattr(tool, 'schema'):
            schema = tool.schema
            if 'parameters' in schema:
                params = schema['parameters'].get('properties', {})
                required = schema['parameters'].get('required', [])
                tool_info['parameters'] = {
                    k: {"type": v.get("type", "any"), "required": k in required}
                    for k, v in params.items()
                }
        
        tools.append(tool_info)
    
    return tools


def print_tools(agent_type: str, agent):
    """Print available tools for an agent."""
    print(f"\n{agent_type.upper()} Agent Tools:")
    print("-" * 60)
    
    tools = list_tools(agent)
    for i, tool in enumerate(tools, 1):
        print(f"\n{i}. {tool['name']}")
        if tool.get('description'):
            print(f"   {tool['description']}")
        if tool.get('parameters'):
            print(f"   Parameters:")
            for param, info in tool['parameters'].items():
                req = "*" if info["required"] else ""
                print(f"     - {param}{req}: {info['type']}")


async def run_tool(agent, tool_name: str, params: Dict[str, Any]) -> Any:
    """Execute a tool with given parameters."""
    # Find the tool
    tool = None
    for t in agent._tools:
        if t.name == tool_name:
            tool = t
            break
    
    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found")
    
    # Run the tool
    result = await tool.run_json(params, cancellation_token=CancellationToken())
    return result


def get_params_interactive(agent_type: str, tool_name: str) -> Dict[str, Any]:
    """Get tool parameters interactively."""
    # Check for sample inputs
    samples = AGENT_TOOLS.get(agent_type, {}).get("samples", {})
    
    if tool_name in samples:
        sample = samples[tool_name]
        if sample:
            print(f"\nSample input available: {json.dumps(sample, indent=2)}")
            use_sample = input("Use sample input? [Y/n]: ").strip().lower()
            if use_sample != 'n':
                return sample
    
    # Manual input
    print(f"\nEnter parameters as JSON (or empty for no params):")
    try:
        params_str = input("Parameters: ").strip()
        if not params_str:
            return {}
        return json.loads(params_str)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return {}


async def interactive_tool_test():
    """Run interactive tool testing session."""
    print("\n" + "=" * 60)
    print("  GeoFaham Tool Tester")
    print("=" * 60)
    
    # Select agent
    print("\nAvailable agents:")
    agents_list = list(AGENT_TOOLS.keys())
    for i, name in enumerate(agents_list, 1):
        print(f"  {i}. {name}")
    
    while True:
        choice = input("\nSelect agent (number or name, 'q' to quit): ").strip().lower()
        
        if choice in ('q', 'quit'):
            return
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(agents_list):
                agent_type = agents_list[idx]
                break
        elif choice in agents_list:
            agent_type = choice
            break
        
        print("Invalid choice.")
    
    # Create agent
    print(f"\nLoading {agent_type} agent...")
    agent, model = create_agent_for_tools(agent_type)
    print(f"Loaded! Model: {model}")
    
    # Show tools
    print_tools(agent_type, agent)
    
    # Tool testing loop
    while True:
        tool_choice = input("\nEnter tool name to test (or 'back'/'quit'): ").strip()
        
        if tool_choice.lower() in ('back', 'b'):
            # Go back to agent selection
            await interactive_tool_test()
            return
        
        if tool_choice.lower() in ('quit', 'q'):
            return
        
        # Find tool
        tool_names = [t.name for t in agent._tools]
        if tool_choice not in tool_names:
            print(f"Tool not found. Available: {', '.join(tool_names)}")
            continue
        
        # Get parameters
        params = get_params_interactive(agent_type, tool_choice)
        
        # Execute
        print(f"\nExecuting {tool_choice}...")
        print("-" * 40)
        
        try:
            result = await run_tool(agent, tool_choice, params)
            
            # Format output
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    print(json.dumps(parsed, indent=2)[:2000])
                    if len(result) > 2000:
                        print(f"\n... (truncated, full length: {len(result)} chars)")
                except json.JSONDecodeError:
                    print(result[:2000])
            else:
                print(result)
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test individual agent tools"
    )
    parser.add_argument(
        "--agent", "-a",
        choices=list(AGENT_TOOLS.keys()),
        help="Agent to test"
    )
    parser.add_argument(
        "--tool", "-t",
        help="Tool name to test"
    )
    parser.add_argument(
        "--params", "-p",
        help="Tool parameters as JSON string"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List tools for the specified agent"
    )
    
    args = parser.parse_args()
    
    if args.agent:
        # Create agent
        agent, model = create_agent_for_tools(args.agent)
        
        if args.list:
            # Just list tools
            print_tools(args.agent, agent)
            return
        
        if args.tool:
            # Run specific tool
            params = json.loads(args.params) if args.params else {}
            
            # Use sample if no params provided
            if not params:
                samples = AGENT_TOOLS.get(args.agent, {}).get("samples", {})
                params = samples.get(args.tool, {})
            
            print(f"Running {args.tool} with params: {params}")
            result = await run_tool(agent, args.tool, params)
            print("\nResult:")
            if isinstance(result, str):
                try:
                    print(json.dumps(json.loads(result), indent=2))
                except:
                    print(result)
            else:
                print(result)
            return
        
        # Show tools for this agent
        print_tools(args.agent, agent)
        return
    
    # Interactive mode
    await interactive_tool_test()


if __name__ == "__main__":
    asyncio.run(main())
