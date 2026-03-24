# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Response Store: File-backed storage for GeoFahamToolResponse objects.

This module provides a centralized, file-backed store for agent responses that can be
accessed by any sub-agent via a shared tool function.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.core.config import get_config
from agents.core.exceptions import ResponseNotFoundError, ArtifactNotFoundError
from agents.core.types import GeoFahamToolResponse, ResponseStoreEntry
from agents.core.logging import get_logger

logger = get_logger("core.response_store")


class ResponseStore:
    """
    File-backed store for GeoFahamToolResponse objects.
    
    Features:
    - Stores full GeoFahamToolResponse objects (no metadata loss)
    - File-backed persistence (JSONL format)
    - Accessible by all agents via shared tool
    - Thread-safe append operations
    
    Usage:
        store = ResponseStore()
        response_id = store.store(response)
        response = store.get(response_id)
    """
    
    def __init__(self, store_path: Optional[str] = None):
        """
        Initialize the response store.
        
        Args:
            store_path: Path to JSONL file for persisting responses.
                        Uses config default if not specified.
        """
        config = get_config()
        self._store_path = store_path or str(config.paths.response_store_path)
        self._responses: Dict[str, ResponseStoreEntry] = {}
        self._ordered_ids: List[str] = []
        
        # Ensure directory exists
        store_dir = os.path.dirname(self._store_path)
        if store_dir:
            os.makedirs(store_dir, exist_ok=True)
        
        # Load existing entries
        self._load_from_file()
    
    def _load_from_file(self) -> None:
        """Load response entries from the JSONL file."""
        if not os.path.exists(self._store_path):
            return
        
        try:
            with open(self._store_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry_data = json.loads(line)
                        entry = ResponseStoreEntry.model_validate(entry_data)
                        response_id = entry.response.response_id
                        
                        self._responses[response_id] = entry
                        if response_id not in self._ordered_ids:
                            self._ordered_ids.append(response_id)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON on line {line_num}: {e}")
                    except Exception as e:
                        logger.warning(f"Failed to parse entry on line {line_num}: {e}")
                        
        except Exception as e:
            logger.error(f"Error loading response store from {self._store_path}: {e}")
    
    def store(
        self,
        response: GeoFahamToolResponse,
        step_number: Optional[int] = None
    ) -> str:
        """
        Store a GeoFahamToolResponse in the store and persist to file.
        
        Args:
            response: The GeoFahamToolResponse object to store
            step_number: Optional step number in the orchestration plan
        
        Returns:
            The response_id that was stored
        """
        response_id = response.response_id
        
        entry = ResponseStoreEntry(
            response=response,
            timestamp=datetime.now().isoformat(),
            step_number=step_number
        )
        
        self._responses[response_id] = entry
        if response_id not in self._ordered_ids:
            self._ordered_ids.append(response_id)
        
        # Append to file
        self._append_to_file(entry)
        
        return response_id
    
    def _append_to_file(self, entry: ResponseStoreEntry) -> None:
        """Append a new entry to the store file (JSONL format)."""
        try:
            with open(self._store_path, 'a') as f:
                f.write(json.dumps(entry.model_dump()) + '\n')
        except Exception as e:
            logger.error(f"Error appending to response store {self._store_path}: {e}")
    
    def _persist_all(self) -> None:
        """Write all entries to the store file (overwrites existing)."""
        try:
            with open(self._store_path, 'w') as f:
                for rid in self._ordered_ids:
                    entry = self._responses.get(rid)
                    if entry:
                        f.write(json.dumps(entry.model_dump()) + '\n')
        except Exception as e:
            logger.error(f"Error persisting response store to {self._store_path}: {e}")
    
    def get(self, response_id: str) -> GeoFahamToolResponse:
        """
        Get a response by its ID.
        
        Args:
            response_id: The response ID to look up
        
        Returns:
            The GeoFahamToolResponse
        
        Raises:
            ResponseNotFoundError: If response_id not found
        """
        entry = self._responses.get(response_id)
        if entry is None:
            raise ResponseNotFoundError(response_id)
        return entry.response
    
    def get_or_none(self, response_id: str) -> Optional[GeoFahamToolResponse]:
        """Get a response by ID, returning None if not found."""
        entry = self._responses.get(response_id)
        return entry.response if entry else None
    
    def get_all(self) -> List[GeoFahamToolResponse]:
        """Get all responses in chronological order."""
        return [self._responses[rid].response for rid in self._ordered_ids]
    
    def get_by_source(self, source_agent: str) -> List[GeoFahamToolResponse]:
        """Get all responses from a specific agent."""
        return [
            entry.response for entry in self._responses.values()
            if entry.response.source == source_agent
        ]
    
    def get_by_data_type(self, data_type: str) -> List[GeoFahamToolResponse]:
        """Get all responses of a specific data type (raster, vector, etc.)."""
        return [
            entry.response for entry in self._responses.values()
            if entry.response.data_type == data_type
        ]
    
    def clear(self) -> None:
        """Clear all entries and the backing file."""
        self._responses.clear()
        self._ordered_ids.clear()
        if os.path.exists(self._store_path):
            os.remove(self._store_path)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the store to a dictionary for state persistence."""
        return {
            "responses": {
                rid: entry.model_dump() for rid, entry in self._responses.items()
            },
            "ordered_ids": self._ordered_ids
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Restore the store from a serialized dictionary and persist to file."""
        self.clear()
        
        if "responses" in data:
            for rid, entry_data in data["responses"].items():
                self._responses[rid] = ResponseStoreEntry.model_validate(entry_data)
        
        if "ordered_ids" in data:
            self._ordered_ids = data["ordered_ids"]
        
        # Re-persist restored data to file
        self._persist_all()
    
    def __len__(self) -> int:
        """Return the number of responses in the store."""
        return len(self._responses)
    
    def __contains__(self, response_id: str) -> bool:
        """Check if a response ID exists in the store."""
        return response_id in self._responses


# =============================================================================
# GLOBAL STORE MANAGEMENT
# =============================================================================

class ResponseStoreProvider:
    """
    Provider for the global ResponseStore instance with DI support.
    
    Similar to ConfigProvider, allows override for testing.
    """
    
    _instance: Optional[ResponseStore] = None
    _override: Optional[ResponseStore] = None
    
    @classmethod
    def get(cls) -> ResponseStore:
        """Get the current response store."""
        if cls._override is not None:
            return cls._override
        if cls._instance is None:
            cls._instance = ResponseStore()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset the global store (clears data and creates new instance)."""
        if cls._instance is not None:
            cls._instance.clear()
        else:
            # Clear file even if instance wasn't created yet
            config = get_config()
            store_path = config.paths.response_store_path
            if store_path.exists():
                store_path.unlink()
        cls._instance = ResponseStore()
        cls._override = None
    
    @classmethod
    def override(cls, store: ResponseStore):
        """Context manager for temporary store override."""
        return _StoreOverrideContext(store)


class _StoreOverrideContext:
    """Context manager for store overrides."""
    
    def __init__(self, store: ResponseStore):
        self._store = store
        self._previous: Optional[ResponseStore] = None
    
    def __enter__(self) -> ResponseStore:
        self._previous = ResponseStoreProvider._override
        ResponseStoreProvider._override = self._store
        return self._store
    
    def __exit__(self, *args):
        ResponseStoreProvider._override = self._previous


def get_response_store() -> ResponseStore:
    """Get or create the global ResponseStore instance."""
    return ResponseStoreProvider.get()


def reset_response_store() -> None:
    """Reset the global store (useful for new sessions)."""
    ResponseStoreProvider.reset()


# =============================================================================
# TOOL FUNCTION FOR SUB-AGENTS
# =============================================================================

async def get_available_responses(filter_errors: bool = True) -> str:
    """
    Get all available responses from other agents in the current session.
    
    Use this tool when you need data or artifacts from previous agent responses
    that were not explicitly passed in your instruction. This returns the full
    response objects including metadata, file paths, temporal/spatial coverage,
    and any other data returned by agents.
    
    Error messages are filtered out by default.

    Parameters:
        filter_errors (bool): If True, exclude responses with error messages.

    Returns:
        JSON string containing list of all available GeoFahamToolResponse objects with:
        - response_id: Unique identifier for referencing
        - source: Which agent produced this response
        - type: Response type (layer, data, error, layer_with_data)
        - data_type: Data format (raster, vector, stac_items, timeline, json)
        - artifact: File metadata if applicable (path, property_keys, features_count)
        - metadata: Additional metadata (temporal coverage, spatial bounds, etc.)
        - summary: Human-readable description of the response
        - data: Any structured data returned by the agent
    """
    store = get_response_store()
    responses = store.get_all()
    result = []
    
    for resp in responses:
        if resp.type == "error" and filter_errors:
            continue
        result.append({
            "response_id": resp.response_id,
            "source": resp.source,
            "type": resp.type,
            "data_type": resp.data_type,
            "summary": resp.summary,
            "artifact": resp.artifact.model_dump() if resp.artifact else None,
            "metadata": resp.metadata,
            "data": resp.data,
            "error_message": resp.error_message
        })
    
    if not result:
        return json.dumps({
            "message": "No responses available yet from other agents.",
            "responses": []
        })
    
    return json.dumps({
        "message": f"Found {len(result)} available responses from other agents.",
        "responses": result
    }, indent=2)


def resolve_response_ids(response_ids: List[str]) -> tuple[List[str], Dict[str, Dict[str, str]]]:
    """
    Resolve response_ids to geojson_paths and property_keys.
    
    Args:
        response_ids: List of response IDs from previous agent outputs
        
    Returns:
        Tuple of (geojson_paths, merged_property_keys)
    
    Raises:
        ResponseNotFoundError: If response ID not found
        ArtifactNotFoundError: If response has no artifact
    """
    store = get_response_store()
    geojson_paths = []
    merged_property_keys: Dict[str, Dict[str, str]] = {"points": {}, "lines": {}, "polygons": {}}
    
    for rid in response_ids:
        response = store.get(rid)  # Raises ResponseNotFoundError if not found
        
        artifact = response.artifact
        if artifact is None:
            raise ArtifactNotFoundError(rid)
        
        geojson_paths.append(artifact.path)
        
        # Merge property_keys from artifact
        if artifact.property_keys:
            for geom_type in ["points", "lines", "polygons"]:
                if geom_type in artifact.property_keys:
                    for prop_name, prop_info in artifact.property_keys[geom_type].items():
                        # Extract just the type string from nested dicts if needed
                        if isinstance(prop_info, dict):
                            merged_property_keys[geom_type][prop_name] = prop_info.get("type", "str")
                        else:
                            merged_property_keys[geom_type][prop_name] = str(prop_info)
    
    return geojson_paths, merged_property_keys
