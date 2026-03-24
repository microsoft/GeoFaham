# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Type Definitions

Pydantic models and type definitions for the multi-agent system.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


# =============================================================================
# ENUMS FOR TYPE SAFETY
# =============================================================================

class ResponseType(str, Enum):
    """Type of response from a tool."""
    LAYER = "layer"              # GeoJSON/raster layer for map visualization
    DATA = "data"                # Tabular data or structured results
    ERROR = "error"              # Error occurred
    EMPTY = "empty"              # Query succeeded but no results found


class DataType(str, Enum):
    """Type of data content in the response."""
    # Vector types
    VECTOR = "vector"            # GeoJSON vector layer
    
    # Raster types
    RASTER = "raster"            # Final raster output (GeoTIFF)
    RASTER_INTERMEDIATE = "raster_intermediate"  # Intermediate raster for chaining
    RASTER_MULTI = "raster_multi"  # Multiple raster layers
    
    # Data types
    STAC_ITEMS = "stac_items"    # STAC item references for raster processing
    TIMELINE = "timeline"        # Time-series data with dates
    TABULAR = "tabular"          # Table/row data
    JSON = "json"                # Generic JSON data
    STATS = "stats"              # Statistical results
    
    # Message types
    MESSAGE = "message"          # Text message (info/warning)


class ArtifactFormat(str, Enum):
    """File format of saved artifacts."""
    GEOJSON = "geojson"
    GEOTIFF = "geotiff"
    JSON = "json"
    COG = "cog"  # Cloud Optimized GeoTIFF


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class SavedArtifact(BaseModel):
    """Metadata for a saved GeoJSON or data artifact."""
    
    path: str
    content_type: str = "application/geo+json"
    format: ArtifactFormat = ArtifactFormat.GEOJSON
    bytes: Optional[int] = None
    features_count: Optional[int] = None
    stats: Optional[Dict[str, Any]] = None
    property_keys: Optional[Dict[str, Dict[str, Any]]] = None
    geom_types: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        use_enum_values = True


class GeoFahamToolResponse(BaseModel):
    """
    Standard response format for all GeoFaham agent tools.
    
    All tools MUST return this response format to ensure consistency
    across the orchestrator and downstream processing.
    
    Response Types:
        - LAYER: Contains artifact with path to saved file (GeoJSON/GeoTIFF)
        - DATA: Contains data array with structured results
        - ERROR: Contains error_message with details
        - EMPTY: Query succeeded but no results found
    
    Examples:
        # Layer response (map visualization)
        GeoFahamToolResponse(
            response_id="map_abc123",
            source="osm_map_agent",
            type=ResponseType.LAYER,
            data_type=DataType.VECTOR,
            artifact=SavedArtifact(path="/runtime/artifacts/roads.geojson"),
            summary="Fetched 245 roads"
        )
        
        # Data response (tabular)
        GeoFahamToolResponse(
            response_id="vec_def456",
            source="vector_agent",
            type=ResponseType.DATA,
            data_type=DataType.TABULAR,
            data=[{"id": 1, "name": "Disaster A"}],
            summary="Found 1 disaster"
        )
        
        # Error response
        GeoFahamToolResponse(
            response_id="stac_err789",
            source="stac_agent",
            type=ResponseType.ERROR,
            error_message="Invalid collection: xyz"
        )
    """
    
    response_id: str = Field(description="Unique ID for cross-agent referencing (e.g., 'vec_a1b2c3d4')")
    source: str = Field(description="Agent name that produced this response")
    type: ResponseType = Field(default=ResponseType.LAYER, description="Response type category")
    data_type: DataType = Field(default=DataType.VECTOR, description="Type of data content")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Array of result objects")
    summary: str = Field(default="", description="Human-readable description of results")
    error_message: Optional[str] = Field(default=None, description="Error details when type=ERROR")
    artifact: Optional[SavedArtifact] = Field(default=None, description="Saved file metadata when type=LAYER")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional context (CRS, bounds, etc.)")
    
    class Config:
        use_enum_values = True
    
    def is_success(self) -> bool:
        """Check if response indicates success (not error)."""
        return self.type != ResponseType.ERROR
    
    def has_artifact(self) -> bool:
        """Check if response has a saved artifact."""
        return self.artifact is not None
    
    def has_data(self) -> bool:
        """Check if response has data array."""
        return len(self.data) > 0


class ResponseStoreEntry(BaseModel):
    """A single entry in the response store with tracking metadata."""
    
    response: GeoFahamToolResponse
    timestamp: str
    step_number: Optional[int] = None


# =============================================================================
# GEOMETRY MODELS
# =============================================================================

class Geometry(BaseModel):
    """Base geometry model."""
    
    type: str
    path: str
    properties_keys: List[str] = Field(default_factory=list, description="List of property keys")
    properties_types: Dict[str, str] = Field(
        default_factory=dict, description="Mapping of property keys to types"
    )

    class Config:
        extra = "forbid"


class Polygon(Geometry):
    """Polygon geometry model."""
    type: Literal["Polygon", "MultiPolygon"] = "Polygon"


class Point(Geometry):
    """Point geometry model."""
    type: Literal["Point", "MultiPoint"] = "Point"


class LineString(Geometry):
    """LineString geometry model."""
    type: Literal["LineString", "MultiLineString"] = "LineString"


# =============================================================================
# TYPED DICTS FOR INTERNAL USE
# =============================================================================

class PropertySchema(TypedDict, total=False):
    """Schema for a single property."""
    type: str
    nullable: bool
    fill_pct: int


class FeatureCollection(TypedDict):
    """GeoJSON FeatureCollection structure."""
    type: Literal["FeatureCollection"]
    features: List[Dict[str, Any]]


class GeoJSONFeature(TypedDict, total=False):
    """GeoJSON Feature structure."""
    type: Literal["Feature"]
    geometry: Dict[str, Any]
    properties: Dict[str, Any]
    id: str | int


# =============================================================================
# CONFIGURATION TYPES
# =============================================================================

class ModelInfo(TypedDict, total=False):
    """Model info for Azure OpenAI client."""
    family: str
    vision: bool
    function_calling: bool
    json_output: bool
    structured_output: bool
