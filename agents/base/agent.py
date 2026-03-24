# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Agent Factory Protocol and Base Configuration

Defines the interface for creating agents with consistent signatures.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol, TypeVar

from autogen_agentchat.agents import AssistantAgent
from autogen_core.models import ChatCompletionClient
from autogen_core.tools import FunctionTool

from agents.core.config import AgentsConfig, get_config


@dataclass
class BaseAgentConfig:
    """Base configuration for all agents."""
    
    name: str
    description: str
    max_tool_iterations: int = 4
    reflect_on_tool_use: bool = True
    
    # Optional overrides
    model_name: Optional[str] = None
    tools: List[FunctionTool] = field(default_factory=list)


class AgentFactory(Protocol):
    """
    Protocol defining the interface for agent factory functions.
    
    All agent factories should follow this signature for consistency.
    """
    
    def __call__(
        self,
        model_client: ChatCompletionClient,
        agent_name: Optional[str] = None,
        config: Optional[AgentsConfig] = None,
    ) -> AssistantAgent:
        """
        Create an agent instance.
        
        Args:
            model_client: The LLM client for the agent
            agent_name: Optional name override for the agent
            config: Optional configuration override
        
        Returns:
            Configured AssistantAgent instance
        """
        ...


T = TypeVar('T', bound=AssistantAgent)


def create_agent(
    name: str,
    model_client: ChatCompletionClient,
    tools: List[FunctionTool],
    system_message: str,
    description: str,
    max_tool_iterations: int = 4,
    reflect_on_tool_use: bool = True,
) -> AssistantAgent:
    """
    Create an AssistantAgent with standard configuration.
    
    This is a helper function to ensure consistent agent creation.
    
    Args:
        name: Agent name
        model_client: LLM client
        tools: List of tools available to the agent
        system_message: System prompt
        description: Agent description for orchestrator
        max_tool_iterations: Max retries for tool calls
        reflect_on_tool_use: Whether to reflect on tool results
    
    Returns:
        Configured AssistantAgent
    """
    return AssistantAgent(
        name=name,
        model_client=model_client,
        tools=tools,
        system_message=system_message,
        description=description,
        max_tool_iterations=max_tool_iterations,
        reflect_on_tool_use=reflect_on_tool_use,
    )


class AgentBuilder:
    """
    Builder class for creating agents with fluent interface.
    
    Example:
        agent = (AgentBuilder("my_agent", client)
            .with_tools([tool1, tool2])
            .with_system_message(prompt)
            .with_description(desc)
            .build())
    """
    
    def __init__(self, name: str, model_client: ChatCompletionClient):
        self._name = name
        self._client = model_client
        self._tools: List[FunctionTool] = []
        self._system_message: Optional[str] = None
        self._description: str = ""
        self._max_tool_iterations: int = 4
        self._reflect_on_tool_use: bool = True
    
    def with_tools(self, tools: List[FunctionTool]) -> "AgentBuilder":
        """Add tools to the agent."""
        self._tools = tools
        return self
    
    def add_tool(self, tool: FunctionTool) -> "AgentBuilder":
        """Add a single tool to the agent."""
        self._tools.append(tool)
        return self
    
    def with_system_message(self, message: str) -> "AgentBuilder":
        """Set the system message."""
        self._system_message = message
        return self
    
    def with_description(self, description: str) -> "AgentBuilder":
        """Set the agent description."""
        self._description = description
        return self
    
    def with_max_iterations(self, iterations: int) -> "AgentBuilder":
        """Set max tool iterations."""
        self._max_tool_iterations = iterations
        return self
    
    def with_reflection(self, enabled: bool = True) -> "AgentBuilder":
        """Enable/disable tool reflection."""
        self._reflect_on_tool_use = enabled
        return self
    
    def build(self) -> AssistantAgent:
        """Build the agent."""
        if self._system_message is None:
            raise ValueError("System message is required")
        
        return create_agent(
            name=self._name,
            model_client=self._client,
            tools=self._tools,
            system_message=self._system_message,
            description=self._description,
            max_tool_iterations=self._max_tool_iterations,
            reflect_on_tool_use=self._reflect_on_tool_use,
        )
