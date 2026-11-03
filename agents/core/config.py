# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Configuration Module

Centralized configuration management with dependency injection support.
All environment variables and configurable values are defined here.
"""

import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agents.core.constants import (
    DB_POOL_MIN_CONNECTIONS,
    DB_POOL_MAX_CONNECTIONS,
    MAX_DATA_ROWS,
)

DEFAULT_OPENAI_MODEL_INFO: dict[str, Any] = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": True,
    "family": "unknown",
}


# =============================================================================
# CONFIGURATION DATACLASSES
# =============================================================================

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
        default_factory=lambda: os.getenv("OSM_NOMINATIM_URL", "")
    )
    overpass_url: str = field(
        default_factory=lambda: os.getenv("OSM_OVERPASS_URL", "")
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
    sql_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("GEOFAHAM_SQL_TIMEOUT_SECONDS", "60")))
    raster_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("GEOFAHAM_RASTER_TIMEOUT_SECONDS", "300")))

    def __post_init__(self):
        if self.sql_timeout_seconds <= 0 or self.raster_timeout_seconds <= 0:
            raise ValueError("SQL and raster execution timeouts must be positive")


@dataclass
class AgentsConfig:
    """Main configuration class for GeoFaham agents."""
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    osm: OSMConfig = field(default_factory=OSMConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    
    # AutoGen ChatCompletionClient component configs
    default_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_DEFAULT_MODEL_CLIENT", "")
    )
    reasoning_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_REASONING_MODEL_CLIENT", "")
    )
    
    # Per-agent model client overrides (use reasoning/default client if not set)
    vector_agent_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_VECTOR_AGENT_MODEL_CLIENT", "")
    )
    maps_agent_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_MAPS_AGENT_MODEL_CLIENT", "")
    )
    stac_agent_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_STAC_AGENT_MODEL_CLIENT", "")
    )
    raster_agent_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_RASTER_AGENT_MODEL_CLIENT", "")
    )
    
    # Orchestrator has two model clients: planner and progress
    orchestrator_planner_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_ORCHESTRATOR_PLANNER_MODEL_CLIENT", "")
    )
    orchestrator_progress_model_client: str = field(
        default_factory=lambda: os.getenv("GEOFAHAM_ORCHESTRATOR_PROGRESS_MODEL_CLIENT", "")
    )
    
    def __post_init__(self):
        """Ensure directories exist."""
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
    
    def get_model_client_component(self, client_key: str) -> dict[str, Any]:
        """
        Get an AutoGen ChatCompletionClient component config.

        client_key may be DEFAULT, REASONING, or an agent key such as
        VECTOR_AGENT. Complex agents fall back to REASONING; simple agents fall
        back to DEFAULT.
        """
        overrides = {
            "DEFAULT": self.default_model_client,
            "REASONING": self.reasoning_model_client,
            "VECTOR_AGENT": self.vector_agent_model_client,
            "MAPS_AGENT": self.maps_agent_model_client,
            "STAC_AGENT": self.stac_agent_model_client,
            "RASTER_AGENT": self.raster_agent_model_client,
            "ORCHESTRATOR_PLANNER": self.orchestrator_planner_model_client,
            "ORCHESTRATOR_PROGRESS": self.orchestrator_progress_model_client,
        }

        key = client_key.upper()
        raw_config = overrides.get(key)
        if not raw_config:
            if key in ("VECTOR_AGENT", "RASTER_AGENT", "ORCHESTRATOR_PLANNER", "ORCHESTRATOR_PROGRESS"):
                raw_config = self.reasoning_model_client
            else:
                raw_config = self.default_model_client

        return self.parse_model_client_config(raw_config, key)

    @classmethod
    def parse_model_client_config(cls, raw_config: str, config_name: str = "model client") -> dict[str, Any]:
        """Parse and validate an AutoGen ChatCompletionClient component config."""
        if not raw_config:
            raise ValueError(
                f"Missing {config_name} config. Set GEOFAHAM_DEFAULT_MODEL_CLIENT "
                "and GEOFAHAM_REASONING_MODEL_CLIENT, or the agent-specific *_MODEL_CLIENT override."
            )
        try:
            component = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{config_name} config must be valid JSON") from exc

        if not isinstance(component, dict):
            raise ValueError(f"{config_name} config must be a JSON object")
        if "provider" not in component or "config" not in component:
            raise ValueError(f"{config_name} config must include 'provider' and 'config'")

        component = cls._expand_env_vars(component)
        cls._ensure_openai_model_info(component)

        return component

    @classmethod
    def _ensure_openai_model_info(cls, component: dict[str, Any]) -> None:
        """
        Add default model_info for OpenAI-compatible AutoGen clients.

        AutoGen requires model_info when the model name is not in its built-in
        OpenAI model catalog. This is common for Azure deployments, OpenRouter,
        local OpenAI-compatible servers, and newly released model names.
        """
        provider = str(component.get("provider", ""))
        if not provider.endswith("OpenAIChatCompletionClient"):
            return

        config = component.get("config")
        if not isinstance(config, dict):
            return

        model_info = config.get("model_info")
        if isinstance(model_info, dict):
            merged_model_info = DEFAULT_OPENAI_MODEL_INFO.copy()
            merged_model_info.update(model_info)
            config["model_info"] = merged_model_info
            return

        config["model_info"] = DEFAULT_OPENAI_MODEL_INFO.copy()

    @classmethod
    def _expand_env_vars(cls, value: Any) -> Any:
        """Expand exact $VAR or ${VAR} strings inside model component configs."""
        if isinstance(value, dict):
            return {key: cls._expand_env_vars(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._expand_env_vars(item) for item in value]
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                return os.getenv(value[2:-1], value)
            if value.startswith("$") and value.count("$") == 1:
                return os.getenv(value[1:], value)
        return value
    
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
