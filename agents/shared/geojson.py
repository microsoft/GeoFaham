# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoJSON Utilities

Functions for reading, writing, and processing GeoJSON data.
"""

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Union

import aiofiles

from agents.core.config import get_config
from agents.core.constants import GEOMETRY_CATEGORIES, POINT_TYPES, LINE_TYPES, POLYGON_TYPES
from agents.core.exceptions import GeoJSONParseError, GeoJSONWriteError
from agents.core.types import SavedArtifact
from agents.core.logging import get_logger
from agents.shared.serialization import serialize_value
from agents.shared.analysis import analyze_geojson_features, collect_property_schema

logger = get_logger("shared.geojson")


def generate_response_id() -> str:
    """Generate a unique response ID."""
    return "response_" + str(uuid.uuid4())[:12]


def classify_geometry_type(geom_type: str) -> str:
    """
    Map GeoJSON geometry type to category (points/lines/polygons).
    
    Args:
        geom_type: GeoJSON geometry type (e.g., "Point", "Polygon")
    
    Returns:
        Category string: "points", "lines", or "polygons"
    
    Raises:
        ValueError: If geometry type is unknown
    """
    if geom_type not in GEOMETRY_CATEGORIES:
        raise ValueError(f"Unknown geometry type: {geom_type}")
    return GEOMETRY_CATEGORIES[geom_type]


def parse_geojson_files(paths: Union[str, List[str]]) -> Dict[str, Any]:
    """
    Parse one or more GeoJSON files into a unified structure.
    
    Args:
        paths: Single path or list of paths to GeoJSON files
    
    Returns:
        Dict with keys:
        - features: list of all features
        - features_by_type: {"points": [...], "lines": [...], "polygons": [...]}
        - feature_count: total count
    
    Raises:
        GeoJSONParseError: If parsing fails
    """
    if isinstance(paths, str):
        paths = [paths]
    
    all_features: List[Dict[str, Any]] = []
    
    for path in paths:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            raise GeoJSONParseError(f"Failed to parse GeoJSON: {e}", file_path=path)
        
        if data.get("type") == "FeatureCollection":
            all_features.extend(data.get("features", []))
        elif data.get("type") == "Feature":
            all_features.append(data)
        elif data.get("type") in POINT_TYPES | LINE_TYPES | POLYGON_TYPES:
            # Raw geometry - wrap as Feature
            all_features.append({
                "type": "Feature",
                "geometry": data,
                "properties": {}
            })
        else:
            raise GeoJSONParseError(
                f"Unsupported GeoJSON type: {data.get('type')}", 
                file_path=path
            )
    
    if not all_features:
        raise GeoJSONParseError("No features found in GeoJSON files")
    
    # Group by geometry type
    features_by_type: Dict[str, List[Dict]] = {"points": [], "lines": [], "polygons": []}
    for feature in all_features:
        geom = feature.get("geometry")
        if geom:
            geom_type = geom.get("type")
            if geom_type:
                category = classify_geometry_type(geom_type)
                features_by_type[category].append(feature)
    
    return {
        "features": all_features,
        "features_by_type": features_by_type,
        "feature_count": len(all_features),
    }


async def results_to_geojson(
    results: Dict[str, Any], 
    compute_stats: bool = False
) -> Union[SavedArtifact, str]:
    """
    Convert results dict to GeoJSON file and return SavedArtifact with metadata.
    
    Handles OSM-style data where features may have varying properties by:
    1. Scanning all features to build complete property schema per geometry type
    2. Only including properties that have at least one non-null value
    3. Inferring types from actual values, not just first feature
    
    Args:
        results: GeoJSON-like dict with "features" key
        compute_stats: If True, compute feature statistics
    
    Returns:
        SavedArtifact on success, error string on failure
    """
    config = get_config()
    uid = uuid.uuid4().hex
    file_path = os.path.join(str(config.paths.export_dir), f"{uid}.geojson")
    
    # Keys to remove from properties (cleanup)
    exclude_patterns = {"id", "index", "copyright"}
    
    features = results.get("features", [])
    
    for feature in features:
        props = feature.get("properties", {})
        keys_to_remove = [
            k for k in list(props.keys())
            if (any(pat.lower() in k.lower() for pat in exclude_patterns) or k.startswith("_"))
            and k.lower() != "cluster_id"
        ]
        for k in keys_to_remove:
            props.pop(k, None)
        # Serialize values to JSON-compatible types
        for k, v in props.items():
            props[k] = serialize_value(v)
    
    # Write GeoJSON file
    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(results, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Error writing GeoJSON file: {e}")
        return f"Error writing GeoJSON file: {e}"
    
    # Compute stats if requested
    stats = analyze_geojson_features(features) if compute_stats else None
    
    # Collect property schema per geometry type (scanning all features)
    property_keys = {
        'points': collect_property_schema(features, ['Point', 'MultiPoint']),
        'polygons': collect_property_schema(features, ['Polygon', 'MultiPolygon']),
        'lines': collect_property_schema(features, ['LineString', 'MultiLineString']),
    }
    
    # Collect unique geometry types
    geom_types = list({
        feat['geometry']['type'] 
        for feat in features 
        if feat.get('geometry')
    })
    
    artifact = SavedArtifact(
        path=file_path,
        features_count=len(features),
        bytes=os.path.getsize(file_path),
        stats=stats,
        property_keys=property_keys,
        geom_types=geom_types
    )
    
    return artifact
