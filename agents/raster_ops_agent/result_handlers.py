# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Result handlers for processing raster execution outputs.
"""

import uuid
import xarray as xr
import geopandas as gpd

from agents.raster_ops_agent.io_utils import (
    is_computed,
    get_bounds,
    compute_stats,
    write_result_as_cog,
)


async def handle_single_raster(result: xr.DataArray) -> dict:
    """
    Handle a single raster result - compute, write COG, and return layer info.
    
    Args:
        result: xarray DataArray (may be lazy/dask)
        
    Returns:
        Dict with type, url, statistics, bounds, and scale info
    """
    if not is_computed(result):
        print("Array was not computed, computing now...")
        result_computed = result.compute()
    else:
        result_computed = result
    
    statistics = compute_stats(result_computed)
    output_name = f"raster_code_result_{uuid.uuid4().hex[:8]}"
    output_path = await write_result_as_cog(result_computed, output_name)
    bounds_4326 = get_bounds(result_computed)

    return {
        "type": "single_layer",
        "url": output_path,
        "statistics": statistics,
        "bounds": bounds_4326,
        "min_scale": statistics.get("min"),
        "max_scale": statistics.get("max")
    }


async def handle_temporal_sequence(result: dict) -> dict:
    """
    Handle temporal sequence results - write multiple COGs and build timeline response.
    
    Args:
        result: Dict mapping labels to xarray DataArrays
        
    Returns:
        Dict with type, temporal_layers list, and scale info
    """
    temporal_layers = []
    
    for label, raster in result.items():
        if not is_computed(raster):
            print("Array was not computed, computing now...")
            raster_computed = raster.compute()
        else:
            raster_computed = raster
        
        # Create filename-safe label
        safe_label = label.replace('-', '').replace('/', '').replace(' ', '')
        output_name = f"timeline_{safe_label}_{uuid.uuid4().hex[:6]}"
        
        cog_path = await write_result_as_cog(raster_computed, output_name)
        stats = compute_stats(raster_computed)
        bounds_4326 = get_bounds(raster_computed)
        
        layer_info = {
            "url": cog_path,
            "bounds": bounds_4326,
            "statistics": stats,
            "label": label,
        }
        
        temporal_layers.append(layer_info)
    
    if temporal_layers:
        return {
            "type": "temporal_sequence",
            "temporal_layers": temporal_layers,
            "min_scale": min(
                layer.get('statistics', {}).get('min', float('inf')) 
                for layer in temporal_layers
            ),
            "max_scale": max(
                layer.get('statistics', {}).get('max', float('-inf')) 
                for layer in temporal_layers
            )
        }
    
    return {"type": "temporal_sequence", "temporal_layers": []}
