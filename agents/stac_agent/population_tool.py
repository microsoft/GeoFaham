# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
WorldPop Population Tool - Query population data from local GeoTIFF files

Supports:
- Single bounding box queries (get_population_in_bbox)
- Multi-polygon GeoJSON queries with per-feature statistics (get_population_in_geojson)
"""
import rasterio
from rasterio.windows import from_bounds
from rasterio.mask import mask as rasterio_mask
import numpy as np
from typing import List, Dict, Any, Optional, Union
import os
import uuid
import json
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

from agents.core.config import get_config
from agents.core.logging import get_logger

_config = get_config()
_logger = get_logger("stac.population")
worldpop_tiff_path = os.getenv("WORLDPOP_TIFF_PATH", str(_config.paths.base_dir / "worldpop" / "global_pop_2020_CN_1km_R2025A_UA_v1.tif"))
output_tiff_path = str(_config.paths.base_dir / "query_tiff")

# Threshold for switching from unary_union to bounding box
_LARGE_FEATURE_THRESHOLD = 100


def _safe_union_geometries(geometries: List[Any]) -> Any:
    """
    Safely union geometries, handling topology errors gracefully.
    
    For large feature sets, uses bounding box instead of expensive unary_union.
    For smaller sets, repairs invalid geometries before union.
    """
    if not geometries:
        return None
    
    # For large feature sets, use bounding box (fast, always works)
    if len(geometries) > _LARGE_FEATURE_THRESHOLD:
        _logger.info(f"Large geometry set ({len(geometries)} features) - using bounding box for aggregate stats")
        all_bounds = [g.bounds for g in geometries]
        minx = min(b[0] for b in all_bounds)
        miny = min(b[1] for b in all_bounds)
        maxx = max(b[2] for b in all_bounds)
        maxy = max(b[3] for b in all_bounds)
        return box(minx, miny, maxx, maxy)
    
    # For smaller sets, repair and union
    try:
        # Try direct union first
        return unary_union(geometries)
    except Exception as e:
        _logger.warning(f"unary_union failed ({e}), attempting geometry repair")
        try:
            # Repair invalid geometries with buffer(0)
            repaired = [g.buffer(0) if not g.is_valid else g for g in geometries]
            return unary_union(repaired)
        except Exception as e2:
            _logger.warning(f"Repaired union failed ({e2}), falling back to bounding box")
            all_bounds = [g.bounds for g in geometries]
            minx = min(b[0] for b in all_bounds)
            miny = min(b[1] for b in all_bounds)
            maxx = max(b[2] for b in all_bounds)
            maxy = max(b[3] for b in all_bounds)
            return box(minx, miny, maxx, maxy)

def get_population_in_bbox(
    bbox: List[float],
) -> Dict[str, Any]:
    """
    Get population statistics for a bounding box from WorldPop GeoTIFF.
    
    Args:
        bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
        output_tiff_path: Optional path to save the clipped population GeoTIFF
        
    Returns:
        Dictionary containing:
            - total_population: Total population in bbox
            - mean_density: Mean population density (people per pixel)
            - max_density: Maximum population density
            - area_km2: Approximate area covered in km²
            - resolution_m: Pixel resolution in meters
            - bbox: Input bounding box
            - data_shape: Shape of the population array (rows, cols)
            - output_file: Path to saved GeoTIFF (if output_tiff_path provided)
            
    Example:
        >>> bbox = [-118.5, 34.0, -118.2, 34.3]  # Los Angeles area
        >>> result = get_population_in_bbox(bbox, output_tiff_path="la_population.tif")
        >>> print(f"Total population: {result['total_population']:,.0f}")
    """
    if not os.path.exists(worldpop_tiff_path):
        raise FileNotFoundError(
            f"WorldPop GeoTIFF not found at: {worldpop_tiff_path}\n"
            f"Please download WorldPop data first."
        )
    
    try:
        with rasterio.open(worldpop_tiff_path) as src:
            # Get the window for the bbox
            window = from_bounds(*bbox, transform=src.transform)
            
            # Read only the windowed data (not the whole file)
            population_data = src.read(1, window=window)
            
            # Handle NoData values
            if src.nodata is not None:
                population_data = np.where(
                    population_data == src.nodata, 
                    0, 
                    population_data
                )
            
            # Replace negative values with 0 (sometimes used for NoData)
            population_data = np.where(population_data < 0, 0, population_data)
            
            # Calculate statistics
            total_population = np.sum(population_data)
            mean_density = np.mean(population_data)
            max_density = np.max(population_data)
            
            # Calculate approximate area (assuming equal-area or near-equator)
            # For 1km WorldPop data, each pixel is ~1 km²
            pixel_count = population_data.size
            
            # Get actual resolution in meters
            transform = src.window_transform(window)
            resolution_m = abs(transform.a) * 111320  # degrees to meters (approximate)
            area_km2 = (resolution_m / 1000) ** 2 * pixel_count
            
            # Save as GeoTIFF if output path provided
            output_tiff_file_path = f"{output_tiff_path}/population_clip_{uuid.uuid4()}.tif"
            with rasterio.open(
                output_tiff_file_path,
                'w',
                driver='GTiff',
                height=population_data.shape[0],
                width=population_data.shape[1],
                count=1,
                dtype=population_data.dtype,
                crs=src.crs,
                transform=transform,
                compress='lzw'
            ) as dst:
                dst.write(population_data, 1)
                dst.update_tags(
                    source='WorldPop Global 2020',
                    original_resolution='1km',
                    data_type='population_count',
                    units='people_per_pixel',
                    description='Population count clipped from WorldPop global dataset'
                )
            
            result = {
                "total_population": float(total_population),
                "mean_density": float(mean_density),
                "max_density": float(max_density),
                "area_km2": float(area_km2),
                "resolution_m": float(resolution_m),
                "bbox": bbox,
                "data_shape": population_data.shape,
                "pixel_count": int(pixel_count)
            }
            
            result["output_file"] = output_tiff_file_path
            result["file_meta"] = {
                "source": "WorldPop Global 2020",
                "original_resolution": "1km",
                "data_type": "population_count",
                "units": "people_per_pixel",
                "description": "Population count clipped from WorldPop global dataset"
            }
                        
            return result
            
    except Exception as e:
        raise Exception(f"Error reading WorldPop data: {str(e)}")


def _compute_population_stats_for_geometry(
    src,
    geometry: Dict[str, Any],
    nodata_value: Optional[float] = None
) -> Dict[str, Any]:
    """
    Compute population statistics for a single geometry using rasterio mask.
    
    Args:
        src: Open rasterio dataset
        geometry: GeoJSON geometry dict
        nodata_value: NoData value from the raster
        
    Returns:
        Dictionary with population statistics for this geometry
    """
    try:
        # Mask the raster with the geometry
        out_image, out_transform = rasterio_mask(src, [geometry], crop=True, all_touched=True)
        population_data = out_image[0]  # First band
        
        # Handle NoData values
        if nodata_value is not None:
            population_data = np.where(population_data == nodata_value, 0, population_data)
        
        # Replace negative values with 0
        population_data = np.where(population_data < 0, 0, population_data)
        
        # Calculate statistics
        valid_pixels = population_data[population_data > 0]
        total_population = float(np.sum(population_data))
        mean_density = float(np.mean(population_data)) if population_data.size > 0 else 0.0
        max_density = float(np.max(population_data)) if population_data.size > 0 else 0.0
        pixel_count = int(population_data.size)
        
        # Calculate area
        resolution_m = abs(out_transform.a) * 111320  # degrees to meters (approximate)
        area_km2 = (resolution_m / 1000) ** 2 * pixel_count
        
        return {
            "total_population": total_population,
            "mean_density": mean_density,
            "max_density": max_density,
            "area_km2": float(area_km2),
            "pixel_count": pixel_count
        }
    except Exception as e:
        # Return zeros if geometry doesn't intersect raster or other error
        return {
            "total_population": 0.0,
            "mean_density": 0.0,
            "max_density": 0.0,
            "area_km2": 0.0,
            "pixel_count": 0,
            "error": str(e)
        }


def get_population_in_geojson(
    geojson_path: str,
    per_feature: bool = True
) -> Dict[str, Any]:
    """
    Get population statistics for features in a GeoJSON file.
    
    Supports both single and multiple polygons. When per_feature=True, returns
    population statistics for each feature individually along with aggregate totals.
    
    Args:
        geojson_path: Path to GeoJSON file containing polygon(s)
        per_feature: If True, compute stats for each feature separately.
                    If False, compute only aggregate stats for all features combined.
        
    Returns:
        Dictionary containing:
            - total_population: Total population across all features
            - feature_count: Number of features processed
            - per_feature_stats: List of stats per feature (if per_feature=True)
            - aggregate_stats: Combined statistics
            - file_meta: Metadata about the source data
            
    Example:
        >>> result = get_population_in_geojson("neighborhoods.geojson", per_feature=True)
        >>> for feat in result['per_feature_stats']:
        ...     print(f"{feat['feature_id']}: {feat['total_population']:,.0f} people")
    """
    if not os.path.exists(worldpop_tiff_path):
        raise FileNotFoundError(
            f"WorldPop GeoTIFF not found at: {worldpop_tiff_path}\n"
            f"Please download WorldPop data first."
        )
    
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")
    
    # Load GeoJSON
    with open(geojson_path, 'r') as f:
        geojson_data = json.load(f)
    
    # Handle both FeatureCollection and single Feature
    if geojson_data.get('type') == 'FeatureCollection':
        features = geojson_data.get('features', [])
    elif geojson_data.get('type') == 'Feature':
        features = [geojson_data]
    else:
        # Assume it's a geometry directly
        features = [{'type': 'Feature', 'geometry': geojson_data, 'properties': {}}]
    
    if not features:
        raise ValueError("No features found in GeoJSON file")
    
    try:
        with rasterio.open(worldpop_tiff_path) as src:
            nodata_value = src.nodata
            resolution_m = abs(src.transform.a) * 111320
            
            per_feature_stats = []
            all_geometries = []
            
            for idx, feature in enumerate(features):
                geometry = feature.get('geometry')
                properties = feature.get('properties', {})
                
                if geometry is None:
                    continue
                
                # Get feature identifier from properties
                feature_id = (
                    properties.get('name') or 
                    properties.get('id') or 
                    properties.get('NAME') or 
                    properties.get('ID') or
                    f"feature_{idx}"
                )
                
                geom_shape = shape(geometry)
                all_geometries.append(geom_shape)
                
                if per_feature:
                    # Compute stats for this feature
                    stats = _compute_population_stats_for_geometry(src, geometry, nodata_value)
                    stats['feature_id'] = feature_id
                    stats['feature_index'] = idx
                    # Include relevant properties from the feature
                    stats['properties'] = {k: v for k, v in properties.items() 
                                          if isinstance(v, (str, int, float, bool, type(None)))}
                    per_feature_stats.append(stats)
            
            # Compute aggregate stats using union of all geometries
            if all_geometries:
                union_geom = _safe_union_geometries(all_geometries)
                aggregate_stats = _compute_population_stats_for_geometry(
                    src, mapping(union_geom), nodata_value
                )
            else:
                aggregate_stats = {
                    "total_population": 0.0,
                    "mean_density": 0.0,
                    "max_density": 0.0,
                    "area_km2": 0.0,
                    "pixel_count": 0
                }
            
            # Build result
            result = {
                "total_population": aggregate_stats['total_population'],
                "feature_count": len(features),
                "aggregate_stats": aggregate_stats,
                "resolution_m": float(resolution_m),
                "file_meta": {
                    "source": "WorldPop Global 2020",
                    "original_resolution": "1km",
                    "data_type": "population_count",
                    "units": "people_per_pixel",
                    "description": "Population count from WorldPop global dataset"
                }
            }
            
            if per_feature:
                # Limit per-feature stats to avoid massive responses
                # For large feature sets, return only summary + top/bottom by population
                MAX_PER_FEATURE_STATS = 100
                
                if len(per_feature_stats) > MAX_PER_FEATURE_STATS:
                    _logger.info(f"Large feature set ({len(per_feature_stats)} features) - truncating per-feature stats to {MAX_PER_FEATURE_STATS}")
                    
                    # Sort by population descending
                    sorted_stats = sorted(per_feature_stats, key=lambda x: x['total_population'], reverse=True)
                    
                    # Keep top 50 and bottom 50
                    top_n = MAX_PER_FEATURE_STATS // 2
                    truncated_stats = sorted_stats[:top_n] + sorted_stats[-top_n:]
                    
                    # Mark as truncated
                    result["per_feature_stats"] = truncated_stats
                    result["per_feature_truncated"] = True
                    result["per_feature_truncated_info"] = {
                        "original_count": len(per_feature_stats),
                        "returned_count": len(truncated_stats),
                        "selection": f"Top {top_n} and bottom {top_n} by population"
                    }
                else:
                    result["per_feature_stats"] = per_feature_stats
                
                # Add summary of ALL per-feature results (computed before truncation)
                if per_feature_stats:
                    populations = [s['total_population'] for s in per_feature_stats]
                    result["summary"] = {
                        "total_features": len(per_feature_stats),
                        "total_population": sum(populations),
                        "min_population": min(populations),
                        "max_population": max(populations),
                        "mean_population": sum(populations) / len(populations) if populations else 0
                    }
            
            return result
            
    except Exception as e:
        raise Exception(f"Error processing population data: {str(e)}")

