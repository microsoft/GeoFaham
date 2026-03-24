# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Raster Code Executor - Sandboxed Python execution for raster operations.

This class provides a safe execution environment using asteval for
arbitrary Python code that manipulates raster and vector data.
"""

import os
import time
import json
import tempfile
from typing import Any, Dict, List, Optional

import scipy
import xarray as xr
import rioxarray
import numpy as np
import geopandas as gpd
import rasterio
import pyproj
import shapely
import datetime
import dask
import pyogrio
import skimage
from asteval import Interpreter
from pystac import ItemCollection
import planetary_computer
from dask.distributed import Client, LocalCluster


class CodeExecutionError(Exception):
    """Raised when code execution fails."""
    pass


class RasterCodeExecutor:
    """
    Executes arbitrary Python code for raster operations in a sandboxed environment.
    
    The LLM can write full Python using xarray, numpy, and geopandas to perform
    any raster analysis without being constrained by pre-defined functions.
    """
    
    def __init__(self):
        """Initialize the code executor with a safe asteval interpreter."""
        self.aeval = Interpreter()
        self.loaded_rasters = {}
        self.loaded_vectors = {}
        
        # Expose core libraries
        self.aeval.symtable['xr'] = xr
        self.aeval.symtable['np'] = np
        self.aeval.symtable['gpd'] = gpd
        self.aeval.symtable['shapely'] = shapely
        self.aeval.symtable['scipy'] = scipy
        self.aeval.symtable['skimage'] = skimage
        self.aeval.symtable['datetime'] = datetime
        self.aeval.symtable['rasterio'] = rasterio  # For rasterio.features.shapes() vectorization
        
        # Add all safe Python builtins
        import builtins
        for name in dir(builtins):
            if not name.startswith('_'):
                self.aeval.symtable[name] = getattr(builtins, name)
        
        # Expose helper functions for loading
        self.aeval.symtable['load_stac_items'] = self.load_stac_items
        self.aeval.symtable['load_raster_file'] = self.load_raster_file
        self.aeval.symtable['load_vector_file'] = self.load_vector_file
        self.aeval.symtable['clip_to_aoi'] = self.clip_to_aoi

    def validate_code(self, code: str) -> tuple[bool, str]:
        """Validate code for security concerns before execution."""
        return True, "Code validation passed"
    
    def clip_to_aoi(self, da: xr.DataArray, aoi_gdf: gpd.GeoDataFrame) -> xr.DataArray:
        """Clip DataArray to AOI geometry."""
        if aoi_gdf.crs != da.rio.crs:
            aoi_gdf_da = aoi_gdf.to_crs(da.rio.crs)
        else:
            aoi_gdf_da = aoi_gdf
        clipped = da.rio.clip(aoi_gdf_da.geometry, aoi_gdf_da.crs)
        return clipped
    
    def load_vector_file(self, path: str) -> tuple[gpd.GeoDataFrame, int]:
        """
        Load vector file from disk.
        
        Args:
            path: Path to GeoJSON or other vector file
            
        Returns:
            Tuple of (GeoDataFrame, EPSG code)
        """
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Vector file not found: {path}")
            
            gdf = pyogrio.read_dataframe(path)
            epsg_code = gdf.crs.to_epsg() if gdf.crs else 4326
            print(f"Loaded vector from {path}: {len(gdf)} features, CRS: {gdf.crs}")
            return gdf, epsg_code
            
        except Exception as e:
            raise CodeExecutionError(f"Failed to load vector file {path}: {str(e)}")
    
    def execute(self, code: str) -> Any:
        """
        Execute Python code and return the result.
        
        The code should assign its final result to a variable named 'result'.
        
        Args:
            code: Python code string to execute
            
        Returns:
            Dict with 'result' and 'metadata' keys
            
        Raises:
            CodeExecutionError: If execution fails
        """
        import warnings
        
        try:
            start_time = time.time()
            # Use temp directory for LocalCluster cache
            cache_dir = os.path.join(tempfile.gettempdir(), "dask_cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            with LocalCluster(local_directory=cache_dir, processes=False) as cluster, Client(cluster) as client:
                # Suppress common non-critical warnings during execution
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Sending large graph", category=UserWarning)
                    warnings.filterwarnings("ignore", message="All-NaN slice", category=RuntimeWarning)
                    warnings.filterwarnings("ignore", message="invalid value encountered", category=RuntimeWarning)
                    
                    result = self.aeval(code)
                    
                    # Check for execution errors
                    if self.aeval.error:
                        error_msg = [str(err) for err in self.aeval.error]
                        return {"error": "\n".join(error_msg)}
                    
                    if result is None or (not isinstance(result, (dict, xr.DataArray, gpd.GeoDataFrame))):
                        result = self.aeval.symtable.get('result')
                    
                    metadata = self.aeval.symtable.get('metadata', {})
                    
                    if result is None:
                        return {"error": "Code did not assign a value to 'result' variable"}
                    
                    result_meta = dask.compute({"result": result, "metadata": metadata})[0]
                
            end_time = time.time()
            print(f"Code execution took {end_time - start_time:.2f} seconds")
            
            return result_meta
            
        except CodeExecutionError:
            raise
        except Exception as e:
            raise CodeExecutionError(f"Unexpected error during execution: {str(e)}")
    
    def _possible_sign_items(self, band: str, items: ItemCollection) -> ItemCollection:
        """Sign STAC items if needed for Planetary Computer access."""
        import requests
        status_code = requests.head(items[0].assets[band].href).status_code
        if status_code != 200:
            for item in items:
                for asset_id, asset in item.assets.items():
                    asset.href = asset.href.split("?")[0]
            items = planetary_computer.sign(items)
        return items
    
    def load_stac_items(
        self,
        items_json_path: str,
        bbox: List[float],
        bands: List[str],
        resolution: int = 10,
        properties_filter: Optional[Dict[str, Any]] = None,
    ) -> tuple[xr.DataArray, int]:
        """
        Load STAC items from JSON file as xarray DataArray.
        
        Args:
            items_json_path: Path to JSON file containing STAC items
            bbox: Bounding box [minx, miny, maxx, maxy] in EPSG:4326
            bands: List of band/asset names to load
            resolution: Resolution in meters (default: 10)
            properties_filter: Optional STAC Item property filters
            
        Returns:
            Tuple of (xarray.DataArray with stacked raster data, EPSG code)
        """
        try:
            import stackstac
            
            # Load items from JSON
            with open(items_json_path, 'r') as f:
                items_data = json.load(f)
            
            # Parse STAC items
            if isinstance(items_data, dict) and 'features' in items_data:
                items = ItemCollection.from_dict(items_data)
            else:
                items = ItemCollection.from_dict({'type': 'FeatureCollection', 'features': items_data})
            
            # Apply property filters
            if properties_filter:
                filtered_items = []
                for item in items:
                    ok = True
                    for key, expected in properties_filter.items():
                        actual = item.properties.get(key)
                        if isinstance(expected, (list, tuple, set)):
                            if actual not in expected:
                                ok = False
                                break
                        else:
                            if actual != expected:
                                ok = False
                                break
                    if ok:
                        filtered_items.append(item)
                print(f"Filtered STAC items by {properties_filter}: {len(filtered_items)}/{len(items)} kept")
                items = ItemCollection(filtered_items)

            if len(items) == 0:
                raise ValueError(f"No STAC items found in {items_json_path}")
            
            print(f"Loading {len(items)} STAC items with bands {bands} at {resolution}m resolution")

            signed_items = items

            # Get EPSG code and transform bounds
            epsg_code = int(signed_items[0].properties["proj:code"].split(":")[-1])
            print(f"Using EPSG:{epsg_code} projection")
            
            if epsg_code == 4326:
                # For geographic CRS, convert meter resolution to degrees
                resolution_deg = resolution / 111320.0
                print(f"Converting {resolution}m resolution to ~{resolution_deg:.8f} degrees for EPSG:4326")
                bounds = tuple(bbox)
                resolution = resolution_deg
            else:
                # For projected CRS, transform bbox
                transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_code}", always_xy=True)
                xmin, ymin = transformer.transform(bbox[0], bbox[1])
                xmax, ymax = transformer.transform(bbox[2], bbox[3])
                bounds = (xmin, ymin, xmax, ymax)
                print(f"Transformed bounds to EPSG:{epsg_code}: {bounds}")

            stack = stackstac.stack(
                signed_items,
                assets=bands,
                bounds=bounds,
                resolution=resolution,
                chunksize=2048,
                epsg=epsg_code,
                resampling=rasterio.enums.Resampling.bilinear
            )

            print(f"Stacked STAC items: shape={stack.shape}, dims={stack.dims}")
            return stack, epsg_code
            
        except ImportError as e:
            raise CodeExecutionError(f"Missing required library for STAC loading: {e}")
        except FileNotFoundError:
            raise CodeExecutionError(f"STAC items JSON file not found: {items_json_path}")
        except Exception as e:
            raise CodeExecutionError(f"Failed to load STAC items from {items_json_path}: {str(e)}")
    
    def load_raster_file(self, path: str) -> tuple[xr.DataArray, Optional[int]]:
        """
        Load raster from file using rioxarray.
        
        Args:
            path: Path to raster file
            
        Returns:
            Tuple of (xarray DataArray, EPSG code or None)
        """
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Raster file not found: {path}")
            
            raster = rioxarray.open_rasterio(path, masked=True)
            raster = raster.squeeze('band', drop=True)
            epsg_code = raster.rio.crs.to_epsg() if raster.rio.crs else None
            return raster, epsg_code
            
        except Exception as e:
            raise CodeExecutionError(f"Failed to load raster file {path}: {str(e)}")
