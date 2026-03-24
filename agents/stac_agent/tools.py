# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
STAC Agent Tools - Execute STAC queries against Microsoft Planetary Computer
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional, List
import aiofiles
import geopandas as gpd

from agents.core.types import DataType
from agents.core.config import get_export_dir
from agents.core.constants import AGENT_NAMES
from agents.shared.responses import (
    build_data_response,
    build_stac_items_response,
    build_timeline_response,
    build_error_response,
)

from agents.stac_agent.population_tool import get_population_in_bbox, get_population_in_geojson
from agents.stac_agent.collection_groups import (
    CollectionGroup,
    parse_collections_input,
    validate_required_groups,
    format_group_summary
)
from agents.stac_agent.lulc_tool import esa_classes, esir_classes
from agents.stac_agent.collection_data import (
    get_collection_details as _get_collection_details,
    COLLECTION_INDEX,
    FALLBACK_RECOMMENDATIONS
)
from agents.stac_agent.band_metadata import (
    get_rescale_for_band,
    get_visualization_params,
    format_visualization_hints,
    is_prerendered_asset,
)
from agents.stac_agent.search import (
    validate_bbox_coverage,
    search_single_collection,
    analyze_temporal_coverage,
)
from agents.stac_agent.mosaic import create_mosaic_or_tiles

AGENT_NAME = AGENT_NAMES["STAC_AGENT"]

try:
    import pystac_client
    import planetary_computer
    STAC_AVAILABLE = True
except ImportError:
    STAC_AVAILABLE = False
    print("Warning: pystac_client or planetary_computer not installed. STAC functionality will be limited.")


def get_collection_details(collection_ids: List[str]) -> str:
    """
    Get detailed information about STAC collections.
    
    Args:
        collection_ids: List of collection IDs to look up
        
    Returns:
        JSON string with collection details
    """
    # Call the collection_data function with the full list
    details = _get_collection_details(collection_ids)
    
    # Extract unknown collections if any
    unknown = details.pop("_unknown_collections", [])
    
    return build_data_response(
        source=AGENT_NAME,
        data=[{
            "type": "collection_details",
            "collections": details,
            "unknown_collections": unknown
        }],
        summary=f"Retrieved details for {len(details)} collections: {', '.join(details.keys())}" + 
                (f". Unknown collections: {unknown}" if unknown else ""),
        data_type=DataType.JSON
    )


async def execute_stac_search(
    collections: Dict[str, Any],
    geojson_path: str,
    limit: int = 50,
    mode: str = "fetch",
    min_coverage_percent: float = 80.0,
    reasoning: Optional[Dict[str, str]] = None
) -> str:
    """
    Execute STAC query against Microsoft Planetary Computer with dual-date support.
    
    Args:
        collections: Dict[str, Any] - Grouped collections with priority and temporal ranges:
            {
                "flood_detection": {
                    "collection_ids": ["sentinel-1-grd"],
                    "priority": "high",
                    "query": {},
                    "daterange1": "2024-01-01/2024-01-31",
                    "daterange2": "2024-02-01/2024-02-28",
                    "visualization": {"sentinel-1-grd": {"bands": ["vv", "vh"]}}
                },
                ...
            }
        geojson_path: str - Path to GeoJSON file defining the area of interest
        limit: Maximum number of items to return per date/collection (default 50)
        mode: "fetch" (analysis, supports daterange2) or "show" (visualization, single date)
        min_coverage_percent: float - Minimum bbox coverage required (default 80.0)
        reasoning: Optional[Dict[str, str]] - LLM explanation of collection/datetime selection

    Returns:
        JSON string with GeoFahamToolResponse containing results and metadata
    """

    export_dir = get_export_dir()
    
    if not STAC_AVAILABLE:
        return build_error_response(
            source=AGENT_NAME,
            error_message="STAC functionality not available. Please install: pip install pystac-client planetary-computer",
            metadata={"error": "missing_dependencies"}
        )
    
    try:
        # Parse collections input
        try:
            collection_groups = parse_collections_input(collections)
        except ValueError as e:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Invalid collections format: {str(e)}",
                metadata={"error": "invalid_collections_format"}
            )
        
        if not collection_groups:
            return build_error_response(
                source=AGENT_NAME,
                error_message="No collections specified in STAC query",
                metadata={"error": "missing_collections"}
            )
        
        # Load GeoJSON file
        gdf = gpd.read_file(geojson_path)
        
        # Check if this is a population-only query
        is_population_only = (
            len(collection_groups) == 1 and 
            len(collection_groups[0].collection_ids) == 1 and 
            "worldpop-population" in collection_groups[0].collection_ids
        )
        
        if is_population_only:
            return await _handle_population_only_query(geojson_path)
        
        # For non-population queries, enforce single feature constraint
        validation_error = _validate_geojson(gdf)
        if validation_error:
            return validation_error
        
        bbox = gdf.total_bounds.tolist()
        
        # Connect to Planetary Computer STAC API
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace
        )
        
        # Search each collection group
        group_results, required_groups_success = _search_all_groups(
            catalog, collection_groups, bbox, limit, min_coverage_percent
        )
        
        # Validate all required groups succeeded
        all_required_ok, failed_required = validate_required_groups(required_groups_success)
        
        if not all_required_ok:
            return _build_failure_response(
                collection_groups, group_results, failed_required, 
                min_coverage_percent
            )
        
        print(f"\n{'='*60}")
        print("✓ All required groups succeeded")
        print(f"{'='*60}")
        
        # Get population stats
        population_stats = _get_population_stats(geojson_path)
        
        # Create deterministic hash for file naming
        all_collection_ids = [r["collection_id"] for r in group_results.values() if r["collection_id"]]
        query_hash = hashlib.md5(
            json.dumps({
                "collections": sorted(all_collection_ids),
                "bbox": bbox
            }, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        os.makedirs(export_dir, exist_ok=True)
        
        if mode == "fetch":
            return await _handle_fetch_mode(
                group_results, bbox, geojson_path, query_hash, 
                export_dir, population_stats
            )
        else:
            return await _handle_show_mode(
                collection_groups, group_results, bbox, limit, query_hash,
                export_dir, population_stats, reasoning
            )
    
    except Exception as e:
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"STAC search failed: {str(e)}",
            metadata={"error": str(e), "collections": collections}
        )


def _validate_geojson(gdf) -> Optional[str]:
    """Validate GeoJSON has exactly one polygon feature."""
    if len(gdf) != 1:
        return build_error_response(
            source=AGENT_NAME,
            error_message="GeoJSON must contain exactly one feature",
            metadata={"error": "invalid_feature_count"}
        )
    
    if gdf.iloc[0].geometry.geom_type not in ["Polygon", "MultiPolygon"]:
        return build_error_response(
            source=AGENT_NAME,
            error_message="GeoJSON must contain only Polygon or MultiPolygon geometries",
            metadata={"error": "invalid_geometry_type"}
        )
    
    return None


async def _handle_population_only_query(geojson_path: str) -> str:
    """Handle population-only queries separately."""
    print("Population-only query detected - fetching population data with per-feature stats")
    try:
        population_stats = get_population_in_geojson(geojson_path, per_feature=True)
        print(f"Population stats: total={population_stats.get('total_population', 'N/A')}")
        
        feature_count = population_stats.get('feature_count', 1)
        total_pop = population_stats.get('total_population', 0)
        if feature_count > 1 and 'per_feature_stats' in population_stats:
            summary = f"Population data retrieved for {feature_count} features. Total: {total_pop:,.0f} people."
        else:
            summary = f"Population data retrieved: {total_pop:,.0f} people in the area of interest."
        
        return build_data_response(
            source=AGENT_NAME,
            data=[{"type": "population_stats", "data": population_stats}],
            summary=summary,
            data_type=DataType.STATS
        )
    except Exception as e:
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch population data: {str(e)}",
            metadata={"error": str(e)}
        )


def _search_all_groups(catalog, collection_groups, bbox, limit, min_coverage_percent):
    """Search all collection groups and return results."""
    group_results = {}
    required_groups_success = {}
    
    for group in collection_groups:
        # Skip worldpop-population groups
        if "worldpop-population" in group.collection_ids:
            print(f"Skipping population group '{group.name}' - will be fetched separately")
            continue
        
        print(f"\n{'='*60}")
        print(f"Searching group: {group.name} (priority: {group.priority})")
        print(f"{'='*60}")
        
        group_date1_result = None
        group_date2_result = None
        successful_collection = None
        
        # Try each collection in the group
        for collection_id in group.collection_ids:
            date1_result, date2_result = search_single_collection(
                catalog=catalog,
                collection_id=collection_id,
                bbox=bbox,
                date1=group.daterange1,
                date2=group.daterange2,
                limit=limit,
                query_filters=group.query,
                min_coverage_percent=min_coverage_percent
            )
            
            if date1_result:
                group_date1_result = date1_result
                group_date2_result = date2_result
                successful_collection = collection_id
                print(f"✓ Group '{group.name}' succeeded with {collection_id}")
                break
        
        group_results[group.name] = {
            "collection_id": successful_collection,
            "date1_result": group_date1_result,
            "date2_result": group_date2_result,
            "priority": group.priority
        }
        
        if group.is_required:
            required_groups_success[group.name] = successful_collection
    
    return group_results, required_groups_success


def _build_failure_response(collection_groups, group_results, failed_required, 
                           min_coverage_percent):
    """Build error response when required groups fail."""
    failed_groups_info = []
    for group_name in failed_required:
        group = next(g for g in collection_groups if g.name == group_name)
        failed_groups_info.append(f"  - {group_name}: tried {', '.join(group.collection_ids)}")
    
    error_msg = (
        f"Required collection group(s) failed: {', '.join(failed_required)}\n\n"
        f"Failed groups:\n" + "\n".join(failed_groups_info) + "\n\n"
        f"What would you like to do?\n"
        f"1. Retry with different collections\n"
        f"2. Adjust coverage threshold (current: {min_coverage_percent}%)\n"
        f"3. Adjust date ranges\n"
        f"4. Proceed with partial results (only successful groups)"
    )
    
    return build_error_response(
        source=AGENT_NAME,
        error_message=error_msg,
        metadata={
            "failed_required_groups": failed_required,
            "group_results": {
                name: {
                    "collection_id": result["collection_id"],
                    "priority": result["priority"],
                    "succeeded": result["collection_id"] is not None
                }
                for name, result in group_results.items()
            },
            "min_coverage_percent": min_coverage_percent
        }
    )


def _get_population_stats(geojson_path: str) -> Optional[dict]:
    """Get population statistics for the area."""
    try:
        population_stats = get_population_in_geojson(geojson_path, per_feature=True)
        print(f"Population stats: total={population_stats.get('total_population', 'N/A')}")
        return population_stats
    except Exception as e:
        print(f"Warning: Failed to get population stats: {str(e)}")
        return None


async def _handle_fetch_mode(group_results, bbox, geojson_path, query_hash,
                             export_dir, population_stats) -> str:
    """Handle fetch mode - save separate files for analysis."""
    raster_sources = []
    total_date1_items = 0
    total_date2_items = 0
    all_collections = []
    
    for group_name, result in group_results.items():
        if not result["collection_id"]:
            continue
        
        date1_result = result["date1_result"]
        date2_result = result["date2_result"]
        collection_id = result["collection_id"]
        all_collections.append(collection_id)
        
        # Add temporal coverage analysis
        date1_result["temporal_coverage"] = analyze_temporal_coverage(date1_result["items"], bbox)
        
        # Save date1
        geojson_date1 = {
            "type": "FeatureCollection",
            "features": date1_result['items'],
            "metadata": {
                "collection": collection_id,
                "collection_group": group_name,
                "datetime": date1_result["items"][0]["properties"].get("datetime", "static") if date1_result["items"] else "static",
                "scenes_found": date1_result["item_count"],
                "coverage_percent": date1_result["coverage_percent"],
                "bbox": bbox,
                "bands": date1_result["bands"],
                "temporal_coverage": date1_result["temporal_coverage"],
                "aoi_path": geojson_path
            }
        }
        
        filename_date1 = f"stac_results_{query_hash}_{group_name}_date1.geojson"
        output_path_date1 = os.path.join(export_dir, filename_date1)
        async with aiofiles.open(output_path_date1, 'w') as f:
            await f.write(json.dumps(geojson_date1, indent=2))
        print(f"Saved {group_name} date1 GeoJSON to {output_path_date1}")
        
        raster_sources.append({
            "type": "stac_items",
            "collection_group": group_name,
            "items_json_path": output_path_date1,
            "search_params": geojson_date1["metadata"]
        })
        total_date1_items += date1_result["item_count"]
        
        # Save date2 if exists
        if date2_result:
            date2_result["temporal_coverage"] = analyze_temporal_coverage(date2_result["items"], bbox)
            
            geojson_date2 = {
                "type": "FeatureCollection",
                "features": date2_result["items"],
                "metadata": {
                    "collection": collection_id,
                    "collection_group": group_name,
                    "datetime": date2_result["items"][0]["properties"].get("datetime", "static") if date2_result["items"] else "static",
                    "scenes_found": date2_result["item_count"],
                    "coverage_percent": date2_result["coverage_percent"],
                    "bbox": bbox,
                    "bands": date2_result["bands"],
                    "temporal_coverage": date2_result["temporal_coverage"],
                    "aoi_path": geojson_path
                }
            }
            
            filename_date2 = f"stac_results_{query_hash}_{group_name}_date2.geojson"
            output_path_date2 = os.path.join(export_dir, filename_date2)
            async with aiofiles.open(output_path_date2, 'w') as f:
                await f.write(json.dumps(geojson_date2, indent=2))
            print(f"Saved {group_name} date2 GeoJSON to {output_path_date2}")
            
            raster_sources.append({
                "type": "stac_items",
                "collection_group": group_name,
                "items_json_path": output_path_date2,
                "search_params": geojson_date2["metadata"]
            })
            total_date2_items += date2_result["item_count"]
    
    # Add population data
    if population_stats:
        raster_sources.append({"type": "population_stats", "data": population_stats})
    
    # Build summary
    successful_groups = [name for name, r in group_results.items() if r["collection_id"]]
    date2_msg = f", Date 2: {total_date2_items}" if total_date2_items > 0 else ""
    groups_msg = f" across {len(successful_groups)} collection groups: {', '.join(successful_groups)}" if successful_groups else ""
    summary = f"Found STAC items - Date 1: {total_date1_items}{date2_msg}{groups_msg}."
    
    # Use first output path as artifact path
    artifact_path = raster_sources[0]["items_json_path"] if raster_sources else None
    
    return build_stac_items_response(
        source=AGENT_NAME,
        items=raster_sources,
        summary=summary,
        artifact_path=artifact_path or "",
        collections=list(set(all_collections)),
        date_range=None
    )


async def _handle_show_mode(collection_groups, group_results, bbox, limit, query_hash,
                            export_dir, population_stats, reasoning) -> str:
    """Handle show mode - create visualization artifacts."""
    primary_group_name = next((name for name, r in group_results.items() if r["collection_id"]), None)
    
    if not primary_group_name:
        return build_error_response(
            source=AGENT_NAME,
            error_message="No successful collections found for visualization",
            metadata={}
        )
    
    primary_result = group_results[primary_group_name]
    date1_result = primary_result["date1_result"]
    primary_collection = primary_result["collection_id"]
    primary_group = next((g for g in collection_groups if g.name == primary_group_name), None)
    
    # Get visualization config
    primary_vis = None
    if primary_group and primary_group.visualization:
        vis_config = primary_group.visualization.get(primary_collection)
        if vis_config and vis_config.get("bands"):
            primary_vis = get_visualization_params(primary_collection, vis_config["bands"])
    
    # Convert items to GeoJSON features
    all_features = _process_stac_items(date1_result["items"], "date1", primary_collection)
    
    search_params = {
        "bbox": bbox,
        "datetime": date1_result["items"][0]["properties"].get("datetime", "static") if date1_result["items"] else "static",
        "collection": primary_collection,
        "limit": limit
    }
    
    geojson = {
        "type": "FeatureCollection",
        "features": all_features,
        "metadata": {
            "query": search_params,
            "collections": [primary_collection],
            "item_count": len(all_features),
            "reasoning": reasoning,
            "visualization_hints": format_visualization_hints(primary_collection, primary_vis)
        }
    }
    
    filename = f"stac_results_{query_hash}.geojson"
    output_path = os.path.join(export_dir, filename)
    async with aiofiles.open(output_path, 'w') as f:
        await f.write(json.dumps(geojson, indent=2))
    print(f"Saved stac GeoJSON to {output_path}")
    
    # Create mosaic or tile URLs
    mosaics, stac_item_tiles, mosaic_path = await create_mosaic_or_tiles(
        all_features, primary_collection, primary_vis, query_hash, export_dir
    )
    
    # Build summary
    date_info = ""
    if all_features and all_features[0]['properties'].get('datetime'):
        earliest = all_features[-1]['properties']['datetime'][:10]
        latest = all_features[0]['properties']['datetime'][:10]
        date_info = f" from {earliest} to {latest}"
    
    cloud_info = ""
    if primary_group and primary_group.query.get("eo:cloud_cover"):
        cloud_limit = primary_group.query["eo:cloud_cover"]["lt"]
        cloud_info = f" with cloud cover < {cloud_limit}%"
    
    mosaic_info = ""
    if mosaics:
        mosaic_info = ". MosaicJSON created for seamless rendering via TiTiler endpoint."
    elif stac_item_tiles:
        mosaic_info = ". Per-item STAC tile URLs generated for multi-band rendering."
    
    summary = f"Found {len(all_features)} satellite images from {primary_collection}{date_info}{cloud_info}{mosaic_info} Saved to {filename}"
    
    return build_timeline_response(
        source=AGENT_NAME,
        artifact_path=output_path,
        timeline_data=all_features,
        summary=summary,
        metadata={
            "query_params": search_params,
            "collections": [primary_collection],
            "item_count": len(all_features),
            "visualization_hints": format_visualization_hints(primary_collection, primary_vis),
            "mosaic_jsons": mosaics if mosaics else None,
            "stac_item_tiles": stac_item_tiles if stac_item_tiles else None,
            "population_stats": population_stats
        }
    )


def _process_stac_items(items: List[dict], date_label: str, collection_id: str) -> List[dict]:
    """Convert STAC items to GeoJSON features."""
    features = []
    for item in items:
        if isinstance(item, dict):
            item_props = item.get("properties", {})
            item_assets = item.get("assets", {})
            item_dt = item_props.get("datetime")
            item_id = item.get("id")
            item_geometry = item.get("geometry")
        else:
            item_props = item.properties
            item_assets = item.assets
            item_dt = item.datetime.isoformat() if item.datetime else None
            item_id = item.id
            item_geometry = item.geometry
        
        # Build assets dict
        if isinstance(item_assets, dict):
            assets_dict = {k: (v.get("href") if isinstance(v, dict) else v.href) for k, v in item_assets.items()}
        else:
            assets_dict = {asset_name: asset.href for asset_name, asset in item_assets.items()}
        
        properties = {
            "stac_item_id": item_id,
            "collection": collection_id,
            "date_period": date_label,
            "datetime": item_dt,
            "cloud_cover": item_props.get("eo:cloud_cover"),
            "platform": item_props.get("platform"),
            "instruments": item_props.get("instruments"),
            "assets": assets_dict
        }
        
        # Handle static collections without datetime
        if properties["datetime"] is None:
            start = item_props.get('start_datetime')
            end = item_props.get('end_datetime')
            if start and end:
                properties["datetime"] = f"{start}/{end}"
        
        # Add thumbnail if available
        if "thumbnail" in item_assets:
            thumb = item_assets["thumbnail"]
            properties["thumbnail_url"] = thumb.get("href") if isinstance(thumb, dict) else thumb.href
        elif "preview" in item_assets:
            preview = item_assets["preview"]
            properties["thumbnail_url"] = preview.get("href") if isinstance(preview, dict) else preview.href
        
        features.append({
            "type": "Feature",
            "geometry": item_geometry,
            "properties": properties
        })
    
    return features
