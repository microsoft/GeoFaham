# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Response Builder Utilities

Factory functions for creating consistent GeoFahamToolResponse objects.
All agent tools should use these builders to ensure response uniformity.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.core.types import (
    ArtifactFormat,
    DataType,
    GeoFahamToolResponse,
    ResponseType,
    SavedArtifact,
)


def validate_response_artifacts(response: GeoFahamToolResponse) -> None:
    """Reject unusable local outputs before they become workflow dependencies."""
    if response.type in (ResponseType.ERROR, ResponseType.EMPTY):
        raise ValueError(f"{response.response_id}: {response.error_message or response.summary or response.type}")
    if response.type == ResponseType.LAYER and response.artifact is None:
        raise ValueError(f"{response.response_id}: layer has no artifact")
    if response.artifact is not None:
        artifact = response.artifact
        formats = {
            DataType.VECTOR: (ArtifactFormat.GEOJSON,),
            DataType.RASTER: (ArtifactFormat.GEOTIFF, ArtifactFormat.COG),
            DataType.STAC_ITEMS: (ArtifactFormat.JSON, ArtifactFormat.GEOJSON),
        }
        if response.data_type in formats and artifact.format not in formats[response.data_type]:
            raise ValueError(f"{response.response_id}: artifact format does not match {response.data_type}")
        if not artifact.path or not Path(artifact.path).is_file():
            raise ValueError(f"{response.response_id}: artifact file is missing: {artifact.path!r}")
        try:
            if artifact.format in (ArtifactFormat.GEOTIFF, ArtifactFormat.COG):
                import rasterio
                with rasterio.open(artifact.path) as raster:
                    if raster.crs is None or not raster.count:
                        raise ValueError("raster has no CRS or bands")
                    declared_crs = (artifact.metadata or {}).get("crs")
                    if declared_crs and raster.crs != rasterio.crs.CRS.from_user_input(declared_crs):
                        raise ValueError("raster CRS does not match its metadata")
                    metadata = artifact.metadata or {}
                    band_count = metadata.get("band_count")
                    if band_count is not None and band_count != raster.count:
                        raise ValueError("raster band count does not match its metadata")
                    bands = metadata.get("bands")
                    if bands and (not isinstance(bands, list) or len(bands) != raster.count):
                        raise ValueError("raster band list does not match the file's band count")
            elif artifact.format in (ArtifactFormat.JSON, ArtifactFormat.GEOJSON):
                with open(artifact.path) as stream:
                    payload = json.load(stream)
                if artifact.format == ArtifactFormat.GEOJSON and (
                    not isinstance(payload, dict) or payload.get("type") != "FeatureCollection"
                    or not isinstance(payload.get("features"), list) or not payload["features"]
                ):
                    raise ValueError("expected a nonempty GeoJSON FeatureCollection")
                if artifact.format == ArtifactFormat.GEOJSON:
                    features = payload["features"]
                    if artifact.features_count is not None and artifact.features_count != len(features):
                        raise ValueError("GeoJSON feature count does not match its metadata")
                    if artifact.geom_types is not None:
                        actual_types = set()
                        for feature in features:
                            geometry = feature.get("geometry") if isinstance(feature, dict) else None
                            if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str):
                                raise ValueError("GeoJSON contains a missing or malformed geometry")
                            actual_types.add(geometry["type"])
                        if actual_types != set(artifact.geom_types):
                            raise ValueError("GeoJSON geometry types do not match its metadata")
        except (OSError, ValueError) as error:
            raise ValueError(f"{response.response_id}: unreadable or invalid artifact: {error}") from error
    elif not response.data:
        raise ValueError(f"{response.response_id}: response has no data or artifact")

    def check_nested(value):
        if isinstance(value, list):
            for item in value:
                check_nested(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in ("path", "url", "items_json_path", "saved_intermediate_path") and isinstance(item, str):
                    suffix = Path(item).suffix.lower()
                    format_ = {".tif": ArtifactFormat.GEOTIFF, ".tiff": ArtifactFormat.GEOTIFF,
                               ".geojson": ArtifactFormat.GEOJSON, ".json": ArtifactFormat.JSON}.get(suffix)
                    if not item or format_:
                        validate_response_artifacts(GeoFahamToolResponse(
                            response_id=response.response_id, source=response.source,
                            data_type=DataType.RASTER if format_ == ArtifactFormat.GEOTIFF else DataType.JSON,
                            artifact=SavedArtifact(path=item, format=format_ or ArtifactFormat.JSON),
                        ))
                elif key in ("saved_paths", "saved_intermediate_paths") and isinstance(item, dict):
                    for path in item.values():
                        check_nested({"path": path})
                else:
                    check_nested(item)

    if response.data_type in (DataType.RASTER_MULTI, DataType.RASTER_INTERMEDIATE, DataType.STAC_ITEMS):
        check_nested(response.data)
        check_nested(response.metadata or {})


def generate_response_id(prefix: str) -> str:
    """
    Generate a unique response ID with agent prefix.
    
    Args:
        prefix: Agent prefix (e.g., "vec", "map", "stac", "raster")
    
    Returns:
        Unique ID like "vec_a1b2c3d4"
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# =============================================================================
# LAYER RESPONSE BUILDERS
# =============================================================================

def build_layer_response(
    source: str,
    artifact_path: str,
    summary: str,
    response_id: Optional[str] = None,
    features_count: Optional[int] = None,
    stats: Optional[Dict[str, Any]] = None,
    property_keys: Optional[Dict[str, Dict[str, Any]]] = None,
    geom_types: Optional[List[str]] = None,
    file_bytes: Optional[int] = None,
    data: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    data_type: DataType = DataType.VECTOR,
    artifact_format: ArtifactFormat = ArtifactFormat.GEOJSON,
    artifact_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a LAYER response for map visualization.
    
    Use when tool saves a GeoJSON/GeoTIFF file that can be rendered on a map.
    
    Args:
        source: Agent name (e.g., "osm_map_agent", "vector_agent")
        artifact_path: Path to saved file
        summary: Human-readable description
        response_id: Optional custom ID (auto-generated if not provided)
        features_count: Number of features in GeoJSON
        stats: Geometry statistics
        property_keys: Property schema by geometry type
        geom_types: List of geometry types
        file_bytes: File size in bytes
        data: Optional data array (for layer_with_data scenarios)
        metadata: Additional context
        data_type: Type of layer (VECTOR, RASTER, etc.)
        artifact_format: File format
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    content_type = _get_content_type(artifact_format)
    
    artifact = SavedArtifact(
        path=artifact_path,
        content_type=content_type,
        format=artifact_format,
        bytes=file_bytes,
        features_count=features_count,
        stats=stats,
        property_keys=property_keys,
        geom_types=geom_types,
        metadata=artifact_metadata,
    )
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.LAYER,
        data_type=data_type,
        data=data or [],
        summary=summary,
        artifact=artifact,
        metadata=metadata,
    )
    
    return response.model_dump_json()


def build_raster_layer_response(
    source: str,
    artifact_path: str,
    summary: str,
    crs: str,
    bounds: List[float],
    resolution: Optional[float] = None,
    bands: Optional[List[str]] = None,
    response_id: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    artifact_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a LAYER response specifically for raster outputs.
    
    Args:
        source: Agent name
        artifact_path: Path to GeoTIFF
        summary: Human-readable description
        crs: Coordinate reference system (e.g., "EPSG:4326")
        bounds: Bounding box [minx, miny, maxx, maxy]
        resolution: Pixel resolution in CRS units
        bands: List of band names
        response_id: Optional custom ID
        stats: Raster statistics
        metadata: Additional context
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    artifact = SavedArtifact(
        path=artifact_path,
        content_type="image/tiff",
        format=ArtifactFormat.GEOTIFF,
        stats=stats,
        metadata=artifact_metadata if artifact_metadata is not None else {
            "crs": crs,
            "bounds": bounds,
            "resolution": resolution,
            "bands": bands or [],
        },
    )
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.LAYER,
        data_type=DataType.RASTER,
        summary=summary,
        artifact=artifact,
        metadata=metadata,
    )
    
    return response.model_dump_json()


# =============================================================================
# DATA RESPONSE BUILDERS
# =============================================================================

def build_data_response(
    source: str,
    data: List[Dict[str, Any]],
    summary: str,
    response_id: Optional[str] = None,
    data_type: DataType = DataType.TABULAR,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a DATA response for tabular/structured results.
    
    Use when tool returns data that doesn't require map visualization.
    
    Args:
        source: Agent name
        data: Array of result objects
        summary: Human-readable description
        response_id: Optional custom ID
        data_type: Type of data (TABULAR, JSON, STATS, etc.)
        metadata: Additional context
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.DATA,
        data_type=data_type,
        data=data,
        summary=summary,
        metadata=metadata,
    )
    
    return response.model_dump_json()


def build_stac_items_response(
    source: str,
    items: List[Dict[str, Any]],
    summary: str,
    artifact_path: str,
    collections: List[str],
    date_range: Optional[tuple] = None,
    response_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a DATA response for STAC items (for raster agent consumption).
    
    Args:
        source: Agent name
        items: Array of STAC item references
        summary: Human-readable description
        artifact_path: Path to saved STAC items file
        collections: List of collection IDs
        date_range: Tuple of (start_date, end_date)
        response_id: Optional custom ID
        metadata: Additional context
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    artifact = SavedArtifact(
        path=artifact_path,
        content_type="application/json",
        format=ArtifactFormat.JSON,
        features_count=len(items),
        metadata={
            "collections": collections,
            "date_range": date_range,
        }
    )
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.DATA,
        data_type=DataType.STAC_ITEMS,
        data=items,
        summary=summary,
        artifact=artifact,
        metadata=metadata,
    )
    
    return response.model_dump_json()


def build_timeline_response(
    source: str,
    artifact_path: str,
    timeline_data: List[Dict[str, Any]],
    summary: str,
    response_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a LAYER response for time-series data.
    
    Args:
        source: Agent name
        artifact_path: Path to saved GeoJSON
        timeline_data: Array of time-series entries (used for count, not stored in response)
        summary: Human-readable description
        response_id: Optional custom ID
        metadata: Additional context (collections, date range, etc.)
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    artifact = SavedArtifact(
        path=artifact_path,
        content_type="application/geo+json",
        format=ArtifactFormat.GEOJSON,
        features_count=len(timeline_data),
    )
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.LAYER,
        data_type=DataType.TIMELINE,
        data=[],  # Data is saved to artifact_path, frontend loads from there
        summary=summary,
        artifact=artifact,
        metadata=metadata,
    )
    
    return response.model_dump_json()


# =============================================================================
# EMPTY RESPONSE BUILDER
# =============================================================================

def build_empty_response(
    source: str,
    summary: str,
    response_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build an EMPTY response when query succeeds but finds no results.
    
    Use this instead of ERROR when the query was valid but returned no data.
    
    Args:
        source: Agent name
        summary: Human-readable description of why no results
        response_id: Optional custom ID
        metadata: Additional context
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.EMPTY,
        data_type=DataType.MESSAGE,
        summary=summary,
        metadata=metadata,
    )
    
    return response.model_dump_json()


# =============================================================================
# ERROR RESPONSE BUILDER
# =============================================================================

def build_error_response(
    source: str,
    error_message: str,
    response_id: Optional[str] = None,
    summary: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build an ERROR response when tool encounters an error.
    
    Args:
        source: Agent name
        error_message: Detailed error description
        response_id: Optional custom ID
        summary: Optional brief summary (defaults to error_message)
        metadata: Additional context (traceback, params, etc.)
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.ERROR,
        data_type=DataType.MESSAGE,
        summary=summary or f"Error: {error_message[:100]}",
        error_message=error_message,
        metadata=metadata,
    )
    
    return response.model_dump_json()


# =============================================================================
# INTERMEDIATE RESPONSE BUILDER (for chaining)
# =============================================================================

def build_intermediate_response(
    source: str,
    data: Dict[str, Any],
    summary: str,
    response_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build an intermediate response for raster chaining.
    
    Use when raster operation should be chained to next step,
    not saved as final output.
    
    Args:
        source: Agent name
        data: Intermediate data (variable names, refs)
        summary: Human-readable description
        response_id: Optional custom ID
        metadata: Additional context
    
    Returns:
        JSON string of GeoFahamToolResponse
    """
    prefix = _get_prefix(source)
    rid = response_id or generate_response_id(prefix)
    
    response = GeoFahamToolResponse(
        response_id=rid,
        source=source,
        type=ResponseType.DATA,
        data_type=DataType.RASTER_INTERMEDIATE,
        data=[data],
        summary=summary,
        metadata=metadata,
    )
    
    return response.model_dump_json()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_prefix(source: str) -> str:
    """Get response ID prefix from source agent name."""
    prefixes = {
        "vector_agent": "vec",
        "osm_map_agent": "map",
        "stac_agent": "stac",
        "raster_agent": "raster",
        "raster_ops_agent": "raster",
    }
    return prefixes.get(source, source[:3])


def _get_content_type(format: ArtifactFormat) -> str:
    """Get MIME content type from artifact format."""
    content_types = {
        ArtifactFormat.GEOJSON: "application/geo+json",
        ArtifactFormat.GEOTIFF: "image/tiff",
        ArtifactFormat.COG: "image/tiff",
        ArtifactFormat.JSON: "application/json",
    }
    return content_types.get(format, "application/octet-stream")


# =============================================================================
# RESPONSE PARSING UTILITIES
# =============================================================================

def parse_response(json_str: str) -> GeoFahamToolResponse:
    """
    Parse a JSON string into GeoFahamToolResponse.
    
    Args:
        json_str: JSON string from tool response
    
    Returns:
        Parsed GeoFahamToolResponse object
    """
    return GeoFahamToolResponse.model_validate_json(json_str)


def is_error_response(json_str: str) -> bool:
    """Check if response JSON indicates an error."""
    try:
        response = parse_response(json_str)
        return response.type == ResponseType.ERROR
    except Exception:
        return True  # Parse failure = error


def get_artifact_path(json_str: str) -> Optional[str]:
    """Extract artifact path from response JSON."""
    try:
        response = parse_response(json_str)
        return response.artifact.path if response.artifact else None
    except Exception:
        return None
