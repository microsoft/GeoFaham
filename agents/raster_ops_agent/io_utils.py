# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Raster I/O utilities for writing results as COG and GeoJSON files.
"""

import os
import uuid
import numpy as np
import xarray as xr
import geopandas as gpd
import dask.array as dask_array
from rasterio.warp import transform_bounds

from agents.core.config import get_config

# Get export directory from config
_config = get_config()
QUERY_JSONS_PATH = str(_config.paths.export_dir)
os.makedirs(QUERY_JSONS_PATH, exist_ok=True)


def is_computed(da: xr.DataArray) -> bool:
    """Check if array has been computed (not lazy dask array)."""
    return not isinstance(da.data, dask_array.Array)


def get_bounds(raster_computed: xr.DataArray) -> tuple:
    """
    Get bounds in EPSG:4326.
    
    Args:
        raster_computed: Computed xarray DataArray
        
    Returns:
        Tuple of (minx, miny, maxx, maxy) in EPSG:4326
    """
    src_crs = raster_computed.rio.crs
    bounds_native = (
        float(raster_computed.x.min()), 
        float(raster_computed.y.min()),
        float(raster_computed.x.max()), 
        float(raster_computed.y.max())
    )
    
    if src_crs is not None and src_crs.to_epsg() != 4326:
        bounds_4326 = transform_bounds(src_crs, "EPSG:4326", *bounds_native)
    else:
        bounds_4326 = bounds_native
    return bounds_4326


def compute_stats(da: xr.DataArray) -> dict:
    """
    Compute statistics for a raster DataArray, properly handling nodata.
    
    Args:
        da: xarray DataArray
        
    Returns:
        Dict with statistics (min, max, mean, std, percentiles or class_distribution)
    """
    arr = da.values
    
    # Get nodata value if set
    nodata = da.rio.nodata if hasattr(da, 'rio') and da.rio.nodata is not None else None
    
    # Mask nodata and non-finite values
    mask = np.isfinite(arr)
    if nodata is not None:
        mask &= (arr != nodata)
    
    valid_arr = arr[mask]
    
    if valid_arr.size == 0:
        return {"count": 0, "valid_pixels": 0, "total_pixels": arr.size}
    
    # For integer data, compute class distribution
    if np.issubdtype(da.dtype, np.integer):
        unique, counts = np.unique(valid_arr, return_counts=True)
        percentages = counts / counts.sum() * 100
        class_distribution = dict(zip(unique.tolist(), percentages.tolist()))
        return {
            "shape": da.shape,
            "valid_pixels": int(valid_arr.size),
            "total_pixels": int(arr.size),
            "min": int(valid_arr.min()),
            "max": int(valid_arr.max()),
            "class_distribution": class_distribution
        }
    
    # For continuous data, include percentiles
    percentiles = np.percentile(valid_arr, [10, 25, 50, 75, 90])
    return {
        "shape": da.shape,
        "valid_pixels": int(valid_arr.size),
        "total_pixels": int(arr.size),
        "min": float(valid_arr.min()),
        "max": float(valid_arr.max()),
        "mean": float(valid_arr.mean()),
        "std": float(valid_arr.std()),
        "percentiles": {
            "p10": float(percentiles[0]),
            "p25": float(percentiles[1]),
            "p50": float(percentiles[2]),
            "p75": float(percentiles[3]),
            "p90": float(percentiles[4])
        }
    }


async def write_result_as_cog(result: xr.DataArray, output_name: str) -> str:
    """
    Write xarray DataArray result as Cloud-Optimized GeoTIFF.
    
    Args:
        result: xarray DataArray to write
        output_name: Name for the output file (without extension)
        
    Returns:
        Path to the written COG file
    """
    output_path = os.path.join(QUERY_JSONS_PATH, f"{output_name}.tif")
    
    if "time" in result.dims and result.sizes["time"] > 1:
        result = result.isel(time=0).drop_vars("time")

    result.rio.to_raster(
        output_path,
        driver="COG",
        compress="deflate",
        blocksize=512,
        overview_level=4,
        overview_resampling="average"
    )
    print(f"Wrote COG to {output_path}")
    return output_path


def write_result_as_geojson(result: gpd.GeoDataFrame, output_name: str) -> str:
    """
    Write GeoDataFrame result as GeoJSON.
    
    Args:
        result: GeoDataFrame to write
        output_name: Name for the output file (without extension)
        
    Returns:
        Path to the written GeoJSON file
    """
    output_path = os.path.join(QUERY_JSONS_PATH, f"{output_name}.geojson")
    result.to_file(output_path, driver='GeoJSON')
    print(f"Wrote GeoJSON to {output_path}")
    return output_path


def save_intermediate_layer(layer, base_name: str, layer_key: str = "") -> str:
    """
    Save a single layer (raster or vector) as an intermediate file.
    
    Args:
        layer: xr.DataArray or gpd.GeoDataFrame to save
        base_name: Base filename for the intermediate
        layer_key: Optional key to append to filename
        
    Returns:
        Path to the saved file, or None if unsupported type
    """
    suffix = f"_{layer_key}" if layer_key else ""
    
    if isinstance(layer, xr.DataArray):
        save_path = os.path.join(QUERY_JSONS_PATH, f"{base_name}{suffix}.tif")
        if not is_computed(layer):
            layer = layer.compute()
        
        if layer.rio.crs is None:
            print(f"Layer {base_name}{suffix} has no CRS, skipping save")
            return None
        
        layer.rio.to_raster(save_path, driver="GTiff", compress="deflate")
        print(f"Saved intermediate raster to {save_path}")
        return save_path
        
    elif isinstance(layer, gpd.GeoDataFrame):
        save_path = os.path.join(QUERY_JSONS_PATH, f"{base_name}{suffix}.geojson")
        layer.to_file(save_path, driver="GeoJSON")
        print(f"Saved intermediate vector to {save_path}")
        return save_path
    
    return None


def save_intermediate_results(result, intermediate_name: str) -> dict:
    """
    Save intermediate results to disk based on result type.
    
    Args:
        result: Single layer or dict of layers to save
        intermediate_name: Base name for saved files
        
    Returns:
        Dict with saved paths and count
    """
    if isinstance(result, (xr.DataArray, gpd.GeoDataFrame)):
        save_path = save_intermediate_layer(result, intermediate_name)
        return {"saved_intermediate_path": save_path, "count": 1}
        
    elif isinstance(result, dict):
        saved_paths = {}
        for key, layer in result.items():
            if isinstance(layer, dict):
                # Nested dict (e.g., temporal timeline)
                for subkey, sublayer in layer.items():
                    path = save_intermediate_layer(sublayer, intermediate_name, f"{key}_{subkey}")
                    if path:
                        saved_paths[f"{key}.{subkey}"] = path
            else:
                path = save_intermediate_layer(layer, intermediate_name, key)
                if path:
                    saved_paths[key] = path
        
        return {"saved_intermediate_paths": saved_paths, "count": len(saved_paths)}
    
    return {"count": 0}
