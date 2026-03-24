# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Custom Exceptions

Structured exception hierarchy for better error handling and debugging.
"""

from typing import Any, Optional


class GeoFahamError(Exception):
    """Base exception for all GeoFaham errors."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(GeoFahamError):
    """Raised when configuration is invalid or missing."""
    pass


class DatabaseError(GeoFahamError):
    """Base exception for database-related errors."""
    pass


class ConnectionPoolError(DatabaseError):
    """Raised when connection pool operations fail."""
    pass


class QueryExecutionError(DatabaseError):
    """Raised when a database query fails."""
    
    def __init__(self, message: str, query: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.query = query
        if query:
            self.details["query"] = query[:500]  # Truncate for safety


class QueryValidationError(DatabaseError):
    """Raised when query validation fails (e.g., non-SELECT query)."""
    pass


class GeoJSONError(GeoFahamError):
    """Base exception for GeoJSON-related errors."""
    pass


class GeoJSONParseError(GeoJSONError):
    """Raised when GeoJSON parsing fails."""
    
    def __init__(self, message: str, file_path: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.file_path = file_path
        if file_path:
            self.details["file_path"] = file_path


class GeoJSONWriteError(GeoJSONError):
    """Raised when writing GeoJSON fails."""
    pass


class AgentError(GeoFahamError):
    """Base exception for agent-related errors."""
    
    def __init__(self, message: str, agent_name: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.agent_name = agent_name
        if agent_name:
            self.details["agent_name"] = agent_name


class ToolExecutionError(AgentError):
    """Raised when a tool execution fails."""
    
    def __init__(self, message: str, tool_name: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.tool_name = tool_name
        if tool_name:
            self.details["tool_name"] = tool_name


class ResponseStoreError(GeoFahamError):
    """Base exception for response store errors."""
    pass


class ResponseNotFoundError(ResponseStoreError):
    """Raised when a response ID is not found in the store."""
    
    def __init__(self, response_id: str):
        super().__init__(f"Response not found: {response_id}")
        self.response_id = response_id
        self.details["response_id"] = response_id


class ArtifactNotFoundError(ResponseStoreError):
    """Raised when a response has no artifact."""
    
    def __init__(self, response_id: str):
        super().__init__(f"Response has no artifact: {response_id}")
        self.response_id = response_id


class STACError(GeoFahamError):
    """Base exception for STAC-related errors."""
    pass


class CollectionNotFoundError(STACError):
    """Raised when a STAC collection is not found."""
    pass


class RasterError(GeoFahamError):
    """Base exception for raster processing errors."""
    pass


class CodeExecutionError(RasterError):
    """Raised when raster code execution fails."""
    pass


class OSMError(GeoFahamError):
    """Base exception for OpenStreetMap-related errors."""
    pass


class GeocodingError(OSMError):
    """Raised when geocoding fails."""
    pass


class OverpassQueryError(OSMError):
    """Raised when Overpass API query fails."""
    pass
