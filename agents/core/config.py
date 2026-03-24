# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Configuration Module

Centralized configuration management with dependency injection support.
All environment variables and configurable values are defined here.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.core.constants import (
    DEFAULT_API_VERSION,
    GPT5_API_VERSION,
    DB_POOL_MIN_CONNECTIONS,
    DB_POOL_MAX_CONNECTIONS,
    MAX_DATA_ROWS,
)


# =============================================================================
# CONFIGURATION DATACLASSES
# =============================================================================

@dataclass
class AzureOpenAIConfig:
    """Azure OpenAI service configuration."""
    
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_KEY")
    )
    endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
    )
    
    # GPT-4o configuration
    gpt4o_deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT4O_DEPLOYMENT", "gpt-4o")
    )
    gpt4o_model: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT4O_MODEL", "gpt-4o")
    )
    gpt4o_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv(
            "AZURE_OPENAI_GPT4O_ENDPOINT",
            os.getenv("AZURE_OPENAI_ENDPOINT")
        )
    )
    gpt4o_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT4O_API_VERSION", DEFAULT_API_VERSION)
    )
    
    # GPT-5 / o1 configuration (reasoning model)
    gpt5_deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT5_DEPLOYMENT", "gpt-5.1")
    )
    gpt5_model: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT5_MODEL", "gpt-5.1-2025-11-13")
    )
    gpt5_endpoint: Optional[str] = field(
        default_factory=lambda: os.getenv(
            "AZURE_OPENAI_GPT5_ENDPOINT",
            os.getenv("AZURE_OPENAI_ENDPOINT")
        )
    )
    gpt5_api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_GPT5_API_VERSION", GPT5_API_VERSION)
    )


@dataclass
class ModelSpec:
    """Complete specification for a model deployment."""
    name: str
    model: str
    deployment: str
    endpoint: str
    api_version: str
    reasoning_effort: str = "medium"


@dataclass
class DatabaseConfig:
    """PostgreSQL/PostGIS database configuration."""
    
    user: Optional[str] = field(
        default_factory=lambda: os.getenv("POSTGRES_USER")
    )
    password: Optional[str] = field(
        default_factory=lambda: os.getenv("POSTGRES_PASSWORD")
    )
    host: str = field(
        default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost")
    )
    port: str = field(
        default_factory=lambda: os.getenv("POSTGRES_PORT", "5432")
    )
    database: Optional[str] = field(
        default_factory=lambda: os.getenv("POSTGRES_DB")
    )
    
    # Connection pool settings
    pool_min_connections: int = DB_POOL_MIN_CONNECTIONS
    pool_max_connections: int = DB_POOL_MAX_CONNECTIONS


@dataclass
class OSMConfig:
    """OpenStreetMap services configuration."""
    
    nominatim_url: str = field(
        default_factory=lambda: os.getenv(
            "OSM_NOMINATIM_URL",
            "http://127.0.0.1:5050/nominatim/"
        )
    )
    overpass_url: str = field(
        default_factory=lambda: os.getenv(
            "OSM_OVERPASS_URL",
            "http://127.0.0.1:5050/overpass"
        )
    )
    cache_folder: str = field(
        default_factory=lambda: os.getenv(
            "OSM_CACHE_FOLDER",
            "/tmp/osmnx_cache"
        )
    )


@dataclass
class PathsConfig:
    """File system paths configuration."""
    
    # Runtime directory for generated artifacts
    base_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("GEOFAHAM_BASE_DIR", "./runtime")
        )
    )
    # Static data directory
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("GEOFAHAM_DATA_DIR", "./data")
        )
    )
    # Override for STAC band metadata path
    band_metadata_path: Optional[str] = field(
        default_factory=lambda: os.getenv("STAC_BAND_METADATA_PATH")
    )
    
    @property
    def stac_band_metadata(self) -> Path:
        """Path to STAC band metadata JSON."""
        if self.band_metadata_path:
            return Path(self.band_metadata_path)
        return self.data_dir / "stac" / "stac_output_mpc_clean.json"
    
    @property
    def export_dir(self) -> Path:
        """Directory for exported GeoJSON/COG files."""
        path = self.base_dir / "artifacts" / "query_jsons"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def state_dir(self) -> Path:
        """Directory for state files."""
        path = self.base_dir / "state"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def history_dir(self) -> Path:
        """Directory for conversation history."""
        path = self.base_dir / "history"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def user_data_dir(self) -> Path:
        """Directory for user uploaded data."""
        path = self.base_dir / "user_data"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def response_store_path(self) -> Path:
        """Path to response store file."""
        return self.state_dir / "response_store.jsonl"
    
    @property
    def team_state_path(self) -> Path:
        """Path to team state file."""
        return self.state_dir / "team_state.json"
    
    @property
    def conversation_history_path(self) -> Path:
        """Path to conversation history file."""
        return self.history_dir / "conversation_history.json"
    
    @property
    def user_artifacts_path(self) -> Path:
        """Path to user artifacts registry."""
        return self.user_data_dir / "user_artifacts.json"
    
    @property
    def schema_cache_path(self) -> Path:
        """Path to cached database schema file."""
        return self.data_dir / "db" / "schema.json"


@dataclass
class QueryConfig:
    """Query execution configuration."""
    
    max_data_rows: int = MAX_DATA_ROWS
    max_response_rows: int = 50
    max_tool_iterations: int = 4
    enable_tool_reflection: bool = True


@dataclass
class AgentsConfig:
    """Main configuration class for GeoFaham agents."""
    
    azure_openai: AzureOpenAIConfig = field(default_factory=AzureOpenAIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    osm: OSMConfig = field(default_factory=OSMConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    
    # Model settings
    default_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_DEFAULT_MODEL", "gpt-4o")
    )
    reasoning_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_REASONING_MODEL", "gpt-5.1")
    )
    
    # Per-agent model overrides (use reasoning_model or default_model if not set)
    vector_agent_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_VECTOR_AGENT_MODEL", "")
    )
    maps_agent_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_MAPS_AGENT_MODEL", "")
    )
    stac_agent_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_STAC_AGENT_MODEL", "")
    )
    raster_agent_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_RASTER_AGENT_MODEL", "")
    )
    
    # Orchestrator has two models: planner and progress
    orchestrator_planner_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_ORCHESTRATOR_PLANNER_MODEL", "")
    )
    orchestrator_progress_model: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_ORCHESTRATOR_PROGRESS_MODEL", "")
    )
    
    def __post_init__(self):
        """Ensure directories exist."""
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_agent_model(self, agent_key: str) -> str:
        """Get model name for a specific agent, falling back to defaults."""
        overrides = {
            "VECTOR_AGENT": self.vector_agent_model,
            "MAPS_AGENT": self.maps_agent_model,
            "STAC_AGENT": self.stac_agent_model,
            "RASTER_AGENT": self.raster_agent_model,
            "ORCHESTRATOR_PLANNER": self.orchestrator_planner_model,
            "ORCHESTRATOR_PROGRESS": self.orchestrator_progress_model,
        }
        
        # Use override if set
        override = overrides.get(agent_key, "")
        if override:
            return override
        
        # Complex reasoning agents default to reasoning_model
        if agent_key in ("VECTOR_AGENT", "RASTER_AGENT", "ORCHESTRATOR_PLANNER", "ORCHESTRATOR_PROGRESS"):
            return self.reasoning_model
        
        return self.default_model
    
    def get_model_spec(self, model_name: str) -> ModelSpec:
        """
        Get full model specification (deployment, endpoint, api_version) for a model name.
        
        Args:
            model_name: Model name like "gpt-4o" or "gpt-5.1"
            
        Returns:
            ModelSpec with deployment, endpoint, and api_version
        """
        # Check if it's a GPT-5/reasoning model
        if "gpt-5" in model_name.lower() or "o1" in model_name.lower():
            return ModelSpec(
                name=model_name,
                model=self.azure_openai.gpt5_model,
                deployment=self.azure_openai.gpt5_deployment,
                endpoint=self.azure_openai.gpt5_endpoint or self.azure_openai.endpoint,
                api_version=self.azure_openai.gpt5_api_version,
                reasoning_effort="medium"
            )
        
        # Default to GPT-4o
        return ModelSpec(
            name=model_name,
            model=self.azure_openai.gpt4o_model,
            deployment=self.azure_openai.gpt4o_deployment,
            endpoint=self.azure_openai.gpt4o_endpoint or self.azure_openai.endpoint,
            api_version=self.azure_openai.gpt4o_api_version,
        )
    
    def get_agent_model_spec(self, agent_key: str) -> ModelSpec:
        """
        Get full model specification for a specific agent.
        
        Args:
            agent_key: Agent key like "VECTOR_AGENT", "MAPS_AGENT", etc.
            
        Returns:
            ModelSpec with deployment, endpoint, and api_version
        """
        model_name = self.get_agent_model(agent_key)
        return self.get_model_spec(model_name)
    
    @classmethod
    def from_env(cls, **overrides) -> "AgentsConfig":
        """
        Create config from environment with optional overrides.
        
        Useful for testing:
            config = AgentsConfig.from_env(
                database=DatabaseConfig(host="test-db")
            )
        """
        config = cls()
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


# =============================================================================
# GLOBAL CONFIG MANAGEMENT (with DI support)
# =============================================================================

class ConfigProvider:
    """
    Configuration provider with dependency injection support.
    
    Usage:
        # Default usage (singleton)
        config = get_config()
        
        # Override for testing
        test_config = AgentsConfig.from_env(database=DatabaseConfig(host="test"))
        with ConfigProvider.override(test_config):
            # All get_config() calls return test_config
            ...
    """
    
    _instance: Optional[AgentsConfig] = None
    _override: Optional[AgentsConfig] = None
    
    @classmethod
    def get(cls) -> AgentsConfig:
        """Get the current configuration."""
        if cls._override is not None:
            return cls._override
        if cls._instance is None:
            cls._instance = AgentsConfig()
        return cls._instance
    
    @classmethod
    def reset(cls) -> AgentsConfig:
        """Reset and return a new configuration instance."""
        cls._instance = AgentsConfig()
        cls._override = None
        return cls._instance
    
    @classmethod
    def override(cls, config: AgentsConfig):
        """Context manager for temporary config override."""
        return _ConfigOverrideContext(config)


class _ConfigOverrideContext:
    """Context manager for config overrides."""
    
    def __init__(self, config: AgentsConfig):
        self._config = config
        self._previous: Optional[AgentsConfig] = None
    
    def __enter__(self) -> AgentsConfig:
        self._previous = ConfigProvider._override
        ConfigProvider._override = self._config
        return self._config
    
    def __exit__(self, *args):
        ConfigProvider._override = self._previous


# =============================================================================
# CONVENIENCE FUNCTIONS (backward compatible)
# =============================================================================

def get_config() -> AgentsConfig:
    """Get or create the global configuration instance."""
    return ConfigProvider.get()


def reset_config() -> AgentsConfig:
    """Reset and return a new configuration instance."""
    return ConfigProvider.reset()


def get_export_dir() -> str:
    """Get the export directory path as string."""
    return str(get_config().paths.export_dir)


def get_response_store_path() -> str:
    """Get the response store path as string."""
    return str(get_config().paths.response_store_path)


def get_team_state_path() -> str:
    """Get the team state path as string."""
    return str(get_config().paths.team_state_path)
