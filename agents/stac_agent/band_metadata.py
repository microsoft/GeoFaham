# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Band metadata and visualization parameter handling for STAC collections.
"""

import os
import json
from typing import Dict, Any, Optional, List

from agents.core.config import get_config

# Lazy-loaded band metadata for rescale values
_BAND_METADATA = None


def _get_band_metadata_path() -> str:
    """Get path to band metadata file from config."""
    config = get_config()
    return str(config.paths.stac_band_metadata)


def load_band_metadata() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Lazy load band metadata on first access.
    
    Returns:
        Dict mapping collection_id -> band_name -> band_info
    """
    global _BAND_METADATA
    if _BAND_METADATA is not None:
        return _BAND_METADATA
    
    _BAND_METADATA = {}
    metadata_path = _get_band_metadata_path()
    
    try:
        with open(metadata_path, 'r') as f:
            collections_data = json.load(f)
            for collection in collections_data:
                collection_id = collection.get('id')
                if collection_id:
                    _BAND_METADATA[collection_id] = {}
                    for band in collection.get('available_bands', []):
                        band_id = band.get('id')
                        raster_bands = band.get('raster:bands', [])
                        if band_id and raster_bands:
                            raster_info = raster_bands[0]
                            _BAND_METADATA[collection_id][band_id] = {
                                'scale': raster_info.get('scale'),
                                'data_type': raster_info.get('data_type'),
                                'unit': raster_info.get('unit'),
                                'spatial_resolution': raster_info.get('spatial_resolution')
                            }
        print(f"Loaded band metadata for {len(_BAND_METADATA)} collections")
    except FileNotFoundError:
        print(f"Warning: Band metadata file not found at {metadata_path}")
    except Exception as e:
        print(f"Warning: Could not load band metadata: {str(e)}")
    
    return _BAND_METADATA


# Data type to rescale mapping
DTYPE_RESCALE = {
    "uint8": "0,255",
    "uint16": "0,10000",  # Sentinel-2 reflectance is 0-10000
    "int16": "-32768,32767",
    "float32": "0,1",
    "float64": "0,1"
}

# Collection-specific rescale overrides based on actual MPC data
# Format: collection_id -> {band_name: (dtype, rescale_string)}
COLLECTION_BAND_INFO = {
    "sentinel-2-l2a": {
        # Pre-rendered assets (uint8)
        "visual": ("uint8", "0,255"),
        "preview": ("uint8", "0,255"),
        # Reflectance bands (uint16, 0-10000 range)
        "B01": ("uint16", "0,10000"),
        "B02": ("uint16", "0,10000"),
        "B03": ("uint16", "0,10000"),
        "B04": ("uint16", "0,10000"),
        "B05": ("uint16", "0,10000"),
        "B06": ("uint16", "0,10000"),
        "B07": ("uint16", "0,10000"),
        "B08": ("uint16", "0,10000"),
        "B8A": ("uint16", "0,10000"),
        "B09": ("uint16", "0,10000"),
        "B11": ("uint16", "0,10000"),
        "B12": ("uint16", "0,10000"),
        # Scene classification (uint8, categorical)
        "SCL": ("uint8", "0,11"),
        # Water vapor / aerosol (uint16)
        "WVP": ("uint16", "0,65535"),
        "AOT": ("uint16", "0,65535"),
    },
    "landsat-c2-l2": {
        # Surface reflectance bands
        "coastal": ("uint16", "0,65535"),
        "blue": ("uint16", "0,65535"),
        "green": ("uint16", "0,65535"),
        "red": ("uint16", "0,65535"),
        "nir08": ("uint16", "0,65535"),
        "swir16": ("uint16", "0,65535"),
        "swir22": ("uint16", "0,65535"),
        # Thermal bands
        "lwir": ("uint16", "0,65535"),
        "lwir11": ("uint16", "0,65535"),
    },
    "naip": {
        "image": ("uint8", "0,255"),
        "red": ("uint8", "0,255"),
        "green": ("uint8", "0,255"),
        "blue": ("uint8", "0,255"),
        "nir": ("uint8", "0,255"),
    },
    "sentinel-1-grd": {
        "vv": ("float32", "-25,5"),
        "vh": ("float32", "-30,0"),
        "hh": ("float32", "-25,5"),
        "hv": ("float32", "-30,0"),
    },
    "io-lulc-annual-v02": {
        "data": ("uint8", "0,11"),  # Land use classification
    },
    "esa-worldcover": {
        "map": ("uint8", "0,100"),  # Land cover classification
    },
    "cop-dem-glo-30": {
        "data": ("float32", "-500,9000"),  # Elevation in meters
    },
    "hgb": {
        "data": ("uint8", "0,255"),  # Building heights
    },
}


def is_prerendered_asset(collection_id: str, bands: list) -> bool:
    """
    Check if the bands represent a pre-rendered asset (single RGB file) vs separate band files.
    
    Pre-rendered assets like 'visual' or 'image' are already combined RGB and can use MosaicJSON.
    Separate bands like ['red', 'green', 'blue'] need per-item STAC tile URLs.
    """
    # Known pre-rendered asset names (single file containing RGB)
    prerendered_assets = {
        "sentinel-2-l2a": ["visual", "preview"],
        "naip": ["image"],
        "landsat-c2-l2": [],  # Landsat has no pre-rendered true color
    }
    
    if len(bands) == 1:
        collection_prerendered = prerendered_assets.get(collection_id, [])
        return bands[0] in collection_prerendered
    
    return False


def get_rescale_for_band(collection_id: str, band_name: str) -> str:
    """
    Get appropriate rescale value for a collection/band combination.
    
    Args:
        collection_id: STAC collection ID
        band_name: Band/asset name
        
    Returns:
        Rescale string like "0,10000" for TiTiler
    """
    # Check collection-specific info first
    if collection_id in COLLECTION_BAND_INFO:
        band_info = COLLECTION_BAND_INFO[collection_id].get(band_name)
        if band_info:
            return band_info[1]  # Return rescale string
    
    # Try to infer from band metadata file
    band_metadata = load_band_metadata()
    if collection_id in band_metadata and band_name in band_metadata[collection_id]:
        meta = band_metadata[collection_id][band_name]
        data_type = meta.get('data_type', '')
        if data_type in DTYPE_RESCALE:
            return DTYPE_RESCALE[data_type]
    
    # Generic fallback based on common patterns
    return "0,255"


def get_visualization_params(collection_id: str, bands: list) -> dict:
    """
    Build complete visualization parameters for a collection.
    
    Args:
        collection_id: STAC collection ID
        bands: List of band names
        
    Returns:
        Dict with bands and rescale values ready for TiTiler
    """
    rescales = [get_rescale_for_band(collection_id, band) for band in bands]
    
    return {
        "bands": bands,
        "rescale": rescales
    }


def format_visualization_hints(collection_id: str, vis_params: dict) -> dict:
    """
    Format visualization params into structure expected by frontend.
    
    Args:
        collection_id: Primary collection ID
        vis_params: Dict with 'bands' and 'rescale' lists
        
    Returns:
        Dict in frontend-expected format with tile_mode info
    """
    if not vis_params:
        return {"primary_collection": collection_id, "layers": []}
    
    bands = vis_params.get("bands", [])
    rescales = vis_params.get("rescale", [])
    
    # Determine rendering type and tile mode
    is_prerendered = is_prerendered_asset(collection_id, bands)
    
    if len(bands) == 1:
        rendering_type = "single_band"
        rescale_str = rescales[0] if rescales else None
        tile_mode = "mosaic" if is_prerendered else "stac_items"
    else:
        rendering_type = "multi_band"
        rescale_str = rescales if rescales else None
        tile_mode = "stac_items"
    
    layer = {
        "collection_id": collection_id,
        "bands": bands,
        "rescale": rescale_str,
        "rendering_type": rendering_type,
        "tile_mode": tile_mode
    }
    
    return {
        "primary_collection": collection_id,
        "layers": [layer]
    }
