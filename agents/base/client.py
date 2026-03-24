# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Model Client Factory

Centralized creation of Azure OpenAI clients with consistent configuration.
Supports both API key and Azure AD token authentication.
"""

from typing import Optional, Union

from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from agents.core.config import AgentsConfig, get_config
from agents.core.logging import get_logger

logger = get_logger("base.client")


class ModelClientFactory:
    """
    Factory for creating Azure OpenAI clients.
    
    Centralizes client creation with consistent configuration.
    Uses API key if AZURE_OPENAI_KEY is set, otherwise falls back to Azure AD.
    """
    
    _token_provider = None
    
    @classmethod
    def get_token_provider(cls):
        """Get or create the Azure AD token provider (singleton, lazy load)."""
        if cls._token_provider is None:
            # Only import Azure auth when needed
            from autogen_ext.auth.azure import AzureTokenProvider
            from azure.identity import DefaultAzureCredential
            
            cls._token_provider = AzureTokenProvider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        return cls._token_provider
    
    @classmethod
    def create(
        cls,
        model: str = "gpt-4o",
        config: Optional[AgentsConfig] = None,
        temperature: Optional[float] = None,
    ) -> AzureOpenAIChatCompletionClient:
        """
        Create an Azure OpenAI client for the specified model.
        
        Auth priority:
        1. API key (if AZURE_OPENAI_KEY is set)
        2. Azure AD token (DefaultAzureCredential)
        
        Args:
            model: Model name ('gpt-4o' or 'gpt-5.1')
            config: Optional configuration override
            temperature: Optional temperature parameter
        
        Returns:
            Configured AzureOpenAIChatCompletionClient
        
        Raises:
            ValueError: If endpoint not configured
        """
        config = config or get_config()
        model_spec = config.get_model_spec(model)
        if not model_spec.endpoint:
            raise ValueError("Azure OpenAI endpoint not configured")
        
        # Build client kwargs
        kwargs = {
            "azure_endpoint": model_spec.endpoint,
            "azure_deployment": model_spec.deployment,
            "model": model_spec.model,
            "api_version": model_spec.api_version,
        }
        
        # Use API key if available, otherwise Azure AD token
        api_key = config.azure_openai.api_key
        if api_key:
            kwargs["api_key"] = api_key
            logger.debug(f"Using API key authentication for model={model}")
        else:
            kwargs["azure_ad_token_provider"] = cls.get_token_provider()
            logger.debug(f"Using Azure AD authentication for model={model}")
        
        # Add reasoning effort for GPT-5/o1 models
        if "gpt-5" in model.lower() or "o1" in model.lower():
            kwargs["reasoning_effort"] = model_spec.reasoning_effort
        
        if "gpt-5" in model.lower():
            kwargs["model_info"] = {
                "family": "gpt",
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "structured_output": True,
            }
        
        logger.debug(f"Creating client for model={model}, deployment={model_spec.deployment}")
        
        return AzureOpenAIChatCompletionClient(**kwargs)
    
    @classmethod
    def reset(cls) -> None:
        """Reset the cached token provider."""
        cls._token_provider = None


def init_model_client(
    model: str = "gpt-4o",
    temperature: Optional[float] = None,
    config: Optional[AgentsConfig] = None,
) -> AzureOpenAIChatCompletionClient:
    """
    Initialize an Azure OpenAI client.
    
    Args:
        model: Model name ('gpt-4o' or 'gpt-5.1')
        temperature: Optional temperature parameter
        config: Optional configuration override
    
    Returns:
        Configured AzureOpenAIChatCompletionClient
    """
    return ModelClientFactory.create(model=model, config=config, temperature=temperature)
