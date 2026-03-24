# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Interactive Console Test for GeoFaham Agents

Allows testing individual agents interactively using AutoGen's Console UI.
Accepts user input from console and streams agent responses.

Usage:
    python -m tests.console_test                    # Interactive agent selection
    python -m tests.console_test --agent vector     # Test specific agent
    python -m tests.console_test --agent maps       # Test maps agent
    python -m tests.console_test --agent stac       # Test STAC agent
    python -m tests.console_test --agent raster     # Test raster agent
    python -m tests.console_test --agent team       # Test full team
"""

import asyncio
import argparse
import sys
from pathlib import Path
from typing import Optional

# Auto-load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on shell environment

from autogen_agentchat.ui import Console
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken

from agents.core.config import get_config
from agents.core.constants import AGENT_NAMES
from agents.base.client import init_model_client


# Agent registry
AVAILABLE_AGENTS = {
    "vector": {
        "key": "VECTOR_AGENT",
        "description": "PostGIS spatial queries - test SQL generation and database queries",
        "factory": "agents.vector_agent:create_vector_agent",
    },
    "maps": {
        "key": "MAPS_AGENT", 
        "description": "OpenStreetMap features extraction - test geocoding and OSM queries",
        "factory": "agents.maps_agent:create_map_search_agent",
    },
    "stac": {
        "key": "STAC_AGENT",
        "description": "Satellite imagery search - test STAC catalog queries",
        "factory": "agents.stac_agent:create_stac_agent",
    },
    "raster": {
        "key": "RASTER_AGENT",
        "description": "Raster analysis - test code generation for imagery processing",
        "factory": "agents.raster_ops_agent:create_raster_ops_agent",
    },
    "team": {
        "key": "TEAM",
        "description": "Full multi-agent team - test orchestrated workflows",
        "factory": None,  # Special case
    },
}


def print_banner():
    """Print welcome banner."""
    print("\n" + "=" * 60)
    print("  GeoFaham Agent Console Tester")
    print("  Type your query and press Enter. Type 'quit' to exit.")
    print("=" * 60 + "\n")


def print_agent_info(agent_name: str, model: str, agent):
    """Print agent information."""
    print(f"Agent: {agent.name}")
    print(f"Model: {model}")
    if hasattr(agent, '_tools'):
        tools = [t.name for t in agent._tools]
        print(f"Tools: {', '.join(tools)}")
    print("-" * 60)


def select_agent_interactive() -> str:
    """Interactive agent selection menu."""
    print("\nAvailable agents:")
    print("-" * 40)
    
    agents_list = list(AVAILABLE_AGENTS.keys())
    for i, (name, info) in enumerate(AVAILABLE_AGENTS.items(), 1):
        print(f"  {i}. {name:8} - {info['description']}")
    
    print()
    
    while True:
        try:
            choice = input("Select agent (number or name): ").strip().lower()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(agents_list):
                    return agents_list[idx]
            elif choice in AVAILABLE_AGENTS:
                return choice
            
            print("Invalid choice. Try again.")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            sys.exit(0)

async def user_input_func(prompt: str, cancellation_token: Optional[CancellationToken] = None) -> str:
    return input(prompt)

async def create_agent(agent_type: str):
    """Create an agent instance by type."""
    config = get_config()
    agent_info = AVAILABLE_AGENTS[agent_type]
    
    if agent_type == "team":
        # Import and create full team
        from agents.team import get_team
        team = await get_team(user_input_func)
        return team, "gpt-5.1 (orchestrator)", None
    
    # Get model for this agent
    agent_key = agent_info["key"]
    model = config.get_agent_model(agent_key)
    # Import factory function
    module_path, func_name = agent_info["factory"].rsplit(":", 1)
    module = __import__(module_path, fromlist=[func_name])
    factory_func = getattr(module, func_name)
    
    # Create model client and agent
    client = init_model_client(model=model)
    agent = factory_func(client)
    
    return agent, model, agent_info


async def run_single_agent_console(agent, model: str, agent_info: dict):
    """Run interactive console for a single agent."""
    print_agent_info(agent.name, model, agent)
    
    # Wrap single agent in a simple team for Console compatibility
    team = RoundRobinGroupChat(
        participants=[agent],
        max_turns=1,  # Single turn per query
    )
    
    while True:
        try:
            query = input("\n[You]: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break
            
            print(f"\n[{agent.name}]:")
            
            # Run with Console UI for streaming
            stream = team.run_stream(task=query)
            await Console(stream)
            
            # Reset for next query
            await team.reset()
            
        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'quit' to exit or continue with another query.")
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()


async def run_team_console(team):
    """Run interactive console for the full team."""
    print(f"Team: GeoFaham Multi-Agent System")
    print(f"Agents: vector, maps, stac, raster (orchestrated)")
    print("-" * 60)
    
    while True:
        try:
            query = input("\n[You]: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ('quit', 'exit', 'q'):
                print("Goodbye!")
                break
            
            print("\n[Team]:")
            
            # Run with Console UI for streaming
            stream = team.run_stream(task=query)
            await Console(stream)
            
            # Reset for next query
            await team.reset()
            
        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'quit' to exit or continue with another query.")
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive console tester for GeoFaham agents"
    )
    parser.add_argument(
        "--agent", "-a",
        choices=list(AVAILABLE_AGENTS.keys()),
        help="Agent to test (if not specified, shows interactive menu)",
    )
    parser.add_argument(
        "--query", "-q",
        help="Single query to run (non-interactive mode)"
    )
    
    args = parser.parse_args()
    
    print_banner()
    
    # Select agent
    if args.agent:
        agent_type = args.agent
    else:
        agent_type = select_agent_interactive()
    
    print(f"\nLoading {agent_type} agent...")
    
    # Create agent
    agent, model, agent_info = await create_agent(agent_type)
    
    print(f"Agent loaded successfully!\n")
    
    # Single query mode
    if args.query:
        if agent_type == "team":
            stream = agent.run_stream(task=args.query)
        else:
            team = RoundRobinGroupChat(participants=[agent], max_turns=1)
            stream = team.run_stream(task=args.query)
        await Console(stream)
        return
    
    # Interactive mode
    if agent_type == "team":
        await run_team_console(agent)
    else:
        await run_single_agent_console(agent, model, agent_info)


if __name__ == "__main__":
    asyncio.run(main())
