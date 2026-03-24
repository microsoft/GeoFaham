# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Mosaic and tile URL generation for STAC visualization.
"""

import os
import json
from typing import Dict, Any, List, Optional
import aiofiles
import geopandas as gpd

from agents.core.config import get_export_dir
from agents.stac_agent.band_metadata import is_prerendered_asset


# MPC API base URL
MPC_TILE_API_URL = "https://planetarycomputer.microsoft.com/api/data/v1"


async def create_mosaic_or_tiles(
    features: List[dict],
    primary_collection: str,
    vis_params: Optional[dict],
    query_hash: str,
    export_dir: str
) -> tuple[dict, dict, Optional[str]]:
    """
    Create MosaicJSON or per-item tile URLs based on visualization config.
    
    Args:
        features: GeoJSON features with STAC item properties
        primary_collection: Collection ID
        vis_params: Visualization parameters with bands/rescale
        query_hash: Hash for filename uniqueness
        export_dir: Directory for output files
        
    Returns:
        Tuple of (mosaics dict, stac_item_tiles dict, mosaic_path or None)
    """
    try:
        from cogeo_mosaic.mosaic import MosaicJSON
        MOSAIC_AVAILABLE = True
    except ImportError:
        MOSAIC_AVAILABLE = False
    
    mosaics = {}
    stac_item_tiles = {}
    mosaic_path = None
    
    if not features or not vis_params:
        return mosaics, stac_item_tiles, mosaic_path
    
    bands = vis_params.get('bands', [])
    rescales = vis_params.get('rescale', [])
    
    if not bands:
        return mosaics, stac_item_tiles, mosaic_path
    
    use_mosaic = is_prerendered_asset(primary_collection, bands) and MOSAIC_AVAILABLE
    
    # Group features by datetime
    df = gpd.GeoDataFrame.from_features(features)
    
    for group_id, (group_name, group) in enumerate(df.groupby('datetime')):
        if use_mosaic:
            # Pre-rendered single asset: use MosaicJSON
            asset_urls = []
            for assets in group.assets:
                if bands[0] in assets:
                    asset_urls.append(assets[bands[0]])
            
            if asset_urls:
                mosaic_filename = f"stac_mosaic_{query_hash}_{group_id}.json"
                mosaic_path = os.path.join(export_dir, mosaic_filename)
                
                try:
                    mosaic_json_data = MosaicJSON.from_urls(
                        asset_urls,
                        minzoom=8,
                        maxzoom=14,
                        max_threads=5
                    )
                    
                    async with aiofiles.open(mosaic_path, 'w') as f:
                        await f.write(json.dumps(mosaic_json_data.model_dump(exclude_none=True), indent=2))
                    
                    print(f"Created MosaicJSON with {len(asset_urls)} assets: {mosaic_path}")
                    mosaics[group_name] = mosaic_path
                except Exception as mosaic_error:
                    print(f"Warning: Failed to create MosaicJSON: {str(mosaic_error)}")
                    print("Falling back to STAC item tiles...")
                    use_mosaic = False
        
        if not use_mosaic:
            # Multi-band or fallback: create per-item STAC tile URLs
            items_tile_info = _create_item_tile_urls(group, bands, rescales, primary_collection)
            
            if items_tile_info:
                stac_item_tiles[group_name] = {
                    "strategy": "stac_item_tiles",
                    "items": items_tile_info,
                    "item_count": len(items_tile_info),
                    "bands": bands,
                    "rescale": rescales
                }
                print(f"Created STAC item tile URLs for {len(items_tile_info)} items in group {group_name}")
    
    return mosaics, stac_item_tiles, mosaic_path


def _create_item_tile_urls(
    group: gpd.GeoDataFrame, 
    bands: List[str], 
    rescales: List[str],
    default_collection: str
) -> List[dict]:
    """
    Create per-item STAC tile URLs for multi-band visualization.
    
    Args:
        group: GeoDataFrame of items for a single datetime group
        bands: List of band names
        rescales: List of rescale values
        default_collection: Default collection ID if not in row
        
    Returns:
        List of tile info dicts
    """
    items_tile_info = []
    
    for idx, row in group.iterrows():
        assets = row['assets']
        item_id = row['stac_item_id']
        collection = row.get('collection', default_collection)
        
        # Check all required bands are available
        if not all(band in assets for band in bands):
            continue
        
        # Build assets parameter string
        assets_params = "&".join([f"assets={band}" for band in bands])
        
        # Build rescale parameters
        if isinstance(rescales, list) and len(rescales) == len(bands):
            rescale_params = "&".join([f"rescale={r}" for r in rescales])
        elif rescales:
            rescale_val = rescales[0] if isinstance(rescales, list) else rescales
            rescale_params = "&".join([f"rescale={rescale_val}" for _ in bands])
        else:
            rescale_params = ""
        
        # MPC's STAC item tile endpoint
        tile_url_template = (
            f"{MPC_TILE_API_URL}/"
            f"item/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}?"
            f"collection={collection}&item={item_id}&"
            f"{assets_params}"
        )
        if rescale_params:
            tile_url_template += f"&{rescale_params}"
        
        items_tile_info.append({
            "item_id": item_id,
            "collection": collection,
            "tile_url_template": tile_url_template,
            "bands": bands,
            "rescale": rescales
        })
    
    return items_tile_info
