# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoJSON Analysis Utilities

Functions for analyzing GeoJSON features and computing statistics.
"""

import json
from typing import Any, Dict, List, Optional

import geopandas as gpd
import pandas as pd

from agents.core.logging import get_logger

logger = get_logger("shared.analysis")


def infer_python_type(value: Any) -> Optional[str]:
    """
    Infer a simplified type name for a value.
    
    Args:
        value: Any Python value
    
    Returns:
        Type name string or None if value is None
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def collect_property_schema(
    features: List[Dict[str, Any]], 
    geom_filter: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Collect property schema for features matching specified geometry types.
    
    Scans ALL features to:
    1. Collect all unique property keys
    2. Infer types from non-null values (first non-null wins)
    3. Track null counts to indicate nullability
    4. Only include keys that have at least one non-null value
    
    Args:
        features: List of GeoJSON features
        geom_filter: List of geometry type names to include
        
    Returns:
        Dict mapping property names to schema info:
        {"type": "str", "nullable": True, "fill_pct": 75}
    """
    key_info: Dict[str, Dict[str, Any]] = {}
    feature_count = 0
    
    # First pass: collect types and count nulls
    for feat in features:
        geom = feat.get("geometry", {})
        if geom.get("type") not in geom_filter:
            continue
        
        feature_count += 1
        props = feat.get("properties", {})
        
        for key, value in props.items():
            if key not in key_info:
                key_info[key] = {"type": None, "non_null_count": 0}
            
            if value is not None:
                key_info[key]["non_null_count"] += 1
                # Set type from first non-null value
                if key_info[key]["type"] is None:
                    key_info[key]["type"] = infer_python_type(value)
    
    # Second pass: compute final schema with nullability
    result: Dict[str, Dict[str, Any]] = {}
    for key, info in key_info.items():
        # Skip keys that are null for ALL features
        if info["type"] is None:
            continue
        
        non_null = info["non_null_count"]
        fill_pct = round(100 * non_null / feature_count) if feature_count > 0 else 0
        
        result[key] = {
            "type": info["type"],
            "nullable": non_null < feature_count,
            "fill_pct": fill_pct
        }
    
    return result


def analyze_geojson_features(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze a GeoJSON feature collection for spatial and attribute statistics.
    
    Returns a dictionary with:
    - Feature count and geometry types
    - Bounding box
    - Area statistics for polygons
    - Time coverage if time fields exist
    - Attribute summaries (numerical, categorical, binary)
    - Cluster analysis if cluster_id present
    
    Args:
        features: List of GeoJSON features
    
    Returns:
        Dict containing analysis results
    """
    if not features:
        return {"feature_count": 0}
    
    try:
        gdf = gpd.GeoDataFrame.from_features(features)
    except Exception as e:
        logger.warning(f"Failed to create GeoDataFrame: {e}")
        return {"feature_count": len(features), "error": str(e)}
    
    gdf.set_crs(epsg=4326, allow_override=True, inplace=True)
    
    analysis: Dict[str, Any] = {}
    
    # Cluster analysis
    has_clustering = 'cluster_id' in gdf.columns
    if has_clustering:
        cluster_analysis = _analyze_clusters(gdf)
        analysis['cluster_analysis'] = cluster_analysis
    
    # Basic stats
    analysis['feature_count'] = len(gdf)
    analysis['geometry_types'] = gdf.geometry.geom_type.value_counts().to_dict()
    analysis['bounding_box'] = gdf.total_bounds.tolist()
    
    # Area stats for polygons
    if any(gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])):
        try:
            gdf_proj = gdf.to_crs(epsg=3857)
            gdf_proj['poly_area_m2'] = gdf_proj.area
            analysis['poly_average_area_m2'] = gdf_proj['poly_area_m2'].mean()
            analysis['poly_total_area_m2'] = gdf_proj['poly_area_m2'].sum()
        except Exception as e:
            logger.warning(f"Failed to compute area stats: {e}")
    
    # Time coverage
    time_fields = [col for col in gdf.columns if 'date' in col.lower() or 'time' in col.lower()]
    for tf in time_fields:
        try:
            gdf[tf] = pd.to_datetime(gdf[tf], errors='coerce')
            analysis[f'{tf}_range'] = [str(gdf[tf].min()), str(gdf[tf].max())]
        except Exception:
            continue
    
    # Attribute summaries
    analysis['attribute_summary'] = _analyze_attributes(gdf, has_clustering)
    
    # Grouped summaries for key fields
    if 'categories' in gdf.columns:
        analysis['grouped_by_categories'] = gdf.groupby('categories').size().to_dict()
    
    return analysis


def _analyze_clusters(gdf: gpd.GeoDataFrame) -> Dict[str, Dict[str, Any]]:
    """Analyze features grouped by cluster_id."""
    cluster_analysis = {}
    damage_cols = ['damage_status', 'damage_pct', 'damaged']
    
    for cluster_id, gdf_group in gdf.groupby('cluster_id'):
        cluster_key = f"cluster_{cluster_id}"
        cluster_analysis[cluster_key] = {}
        
        if 'damage_status' in gdf_group.columns:
            cluster_analysis[cluster_key]['damage_status'] = (
                gdf_group['damage_status'].value_counts().to_dict()
            )
        if 'damage_pct' in gdf_group.columns:
            cluster_analysis[cluster_key]['damage_pct'] = (
                gdf_group['damage_pct'].describe().to_dict()
            )
        if 'damaged' in gdf_group.columns:
            cluster_analysis[cluster_key]['damaged'] = (
                gdf_group['damaged'].value_counts().to_dict()
            )
    
    return cluster_analysis


def _analyze_attributes(gdf: gpd.GeoDataFrame, has_clustering: bool) -> Dict[str, Any]:
    """Analyze attribute columns for statistics."""
    attributes = gdf.drop(columns='geometry', errors='ignore')
    desc_stats = {}
    
    # Columns to always skip (identifiers, contact info, etc.)
    avoid_cols = {'id', 'description', 'address', 'phone', 'email', 'url', 'categorySet'}
    
    for col in attributes.columns:
        if has_clustering and 'cluster' in col.lower():
            continue
        if col.lower() in {c.lower() for c in avoid_cols}:
            continue
        if "copyright" in col.lower():
            continue
        if "index" in col.lower():
            continue
        
        # Skip columns with unhashable types (dict, list) which can't be analyzed
        try:
            unique_vals = attributes[col].dropna().unique()
        except TypeError:
            # Column contains unhashable types (e.g., dict from JSONB)
            continue
        
        # Skip high-cardinality columns (mostly unique values, not useful for grouping)
        unique_count = len(unique_vals)
        total_count = len(attributes[col].dropna())
        unique_ratio = unique_count / total_count if total_count > 0 else 1
        
        # Skip if >70% unique AND more than 10 unique values
        # (allows small datasets with few categories to still show stats)
        if unique_ratio > 0.7 and unique_count > 10:
            continue
        
        if (pd.api.types.is_numeric_dtype(attributes[col]) 
            and len(unique_vals) > 2 
            and col != 'cluster_id'):
            desc_stats[col] = attributes[col].describe().to_dict()
        else:
            desc_stats[col] = attributes[col].value_counts().to_dict()
    
    return desc_stats


def analyze_geojson(file_path: str) -> Dict[str, Any]:
    """
    Analyze a GeoJSON file.
    
    Args:
        file_path: Path to GeoJSON file
    
    Returns:
        Dict containing analysis results
    
    Raises:
        ValueError: If file is not valid GeoJSON
    """
    with open(file_path, 'r') as f:
        geojson_data = json.load(f)
    
    if 'features' not in geojson_data:
        raise ValueError("Invalid GeoJSON: 'features' key not found.")
    
    return analyze_geojson_features(geojson_data['features'])
