# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Model Client Factory

Centralized creation of AutoGen model clients from component configs.
"""

from copy import deepcopy
from typing import Optional

from autogen_core.models import ChatCompletionClient

from agents.core.config import AgentsConfig, get_config
from agents.core.logging import get_logger

logger = get_logger("base.client")


class ModelClientFactory:
    """
    Factory for creating AutoGen chat completion clients.
    """

    @classmethod
    def create(
        cls,
        client_key: str = "DEFAULT",
        config: Optional[AgentsConfig] = None,
        temperature: Optional[float] = None,
    ) -> ChatCompletionClient:
        """
        Create a chat completion client for a role/profile key.
        
        Args:
            client_key: DEFAULT, REASONING, or an agent key like VECTOR_AGENT
            config: Optional configuration override
            temperature: Optional temperature parameter
        
        Returns:
            Configured AutoGen ChatCompletionClient
        """
        config = config or get_config()
        component = deepcopy(config.get_model_client_component(client_key))
        component_config = component.setdefault("config", {})

        if temperature is not None and "temperature" not in component_config:
            component_config["temperature"] = temperature

        logger.debug(f"Creating model client for {client_key}")
        return ChatCompletionClient.load_component(component)
    
    @classmethod
    def reset(cls) -> None:
        """Reset cached factory state."""
        return None


def init_model_client(
    client_key: str = "DEFAULT",
    temperature: Optional[float] = None,
    config: Optional[AgentsConfig] = None,
) -> ChatCompletionClient:
    """
    Initialize an AutoGen chat completion client.
    
    Args:
        client_key: DEFAULT, REASONING, or an agent key like VECTOR_AGENT
        temperature: Optional temperature parameter
        config: Optional configuration override
    
    Returns:
        Configured AutoGen ChatCompletionClient
    """
    return ModelClientFactory.create(client_key=client_key, config=config, temperature=temperature)
