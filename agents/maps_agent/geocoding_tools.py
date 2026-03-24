# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM Geocoding and Boundary Tools - Address geocoding, bounding boxes, admin boundaries.

These tools provide geocoding and administrative boundary lookups via OSM Nominatim.
"""

import logging
from typing import List, Optional, Tuple, Union

import pandas as pd
import geopandas as gpd
import osmnx as ox

from agents.core.constants import AGENT_NAMES
from agents.shared.geojson import results_to_geojson
from agents.shared.responses import (
    build_layer_response,
    build_empty_response,
    build_error_response,
)

from agents.maps_agent.utils import (
    get_polygon_from_geometry,
    osm_gdf_to_geojson_features,
    run_osmnx_async,
    validate_geometry_input,
    estimate_feature_count,
    reverse_geocode_nominatim,
    batch_reverse_geocode,
)

logger = logging.getLogger(__name__)
AGENT_NAME = AGENT_NAMES["MAPS_AGENT"]


def _extract_search_name_and_region(place_name: str) -> Tuple[str, Optional[str]]:
    """
    Extract the target name and broader region from a hierarchical place name.
    
    For "Catherine Hall, Montego Bay, Jamaica", returns:
        - search_name: "Catherine Hall"
        - broader_region: "Montego Bay, Jamaica"
    """
    parts = [p.strip() for p in place_name.split(",")]
    if len(parts) >= 2:
        search_name = parts[0]
        broader_region = ", ".join(parts[1:])
        return search_name, broader_region
    return place_name, None


async def _fallback_search_by_name(
    search_name: str,
    broader_region: str,
) -> Optional[gpd.GeoDataFrame]:
    """
    Fallback search: query OSM features by name within a broader region.
    
    This is used when Nominatim geocoding fails. It geocodes the broader region
    to get a search area, then queries for neighborhood/boundary features matching
    the target name.
    """
    try:
        print(f"Fallback: geocoding broader region '{broader_region}'")
        region_gdf = await run_osmnx_async(ox.geocode_to_gdf, broader_region)
        
        if region_gdf is None or region_gdf.empty:
            print(f"Fallback: could not geocode broader region '{broader_region}'")
            return None
        
        region_polygon = region_gdf.geometry.union_all()
        
        tags_to_try = [
            {"boundary": "administrative"},
            {"place": ["neighbourhood", "neighborhood", "suburb", "quarter", "village", "town"]},
        ]
        
        all_results = []
        search_name_lower = search_name.lower()
        
        for tags in tags_to_try:
            try:
                gdf = await run_osmnx_async(
                    ox.features_from_polygon, region_polygon, tags=tags,
                )
                if gdf is not None and not gdf.empty:
                    try:
                        gdf = gdf.reset_index()
                    except Exception:
                        pass
                    
                    if "name" in gdf.columns:
                        name_mask = gdf["name"].astype(str).str.lower().str.contains(
                            search_name_lower, na=False, regex=False
                        )
                        matched = gdf[name_mask]
                        
                        if not matched.empty:
                            matched = matched[matched.geometry.notna()]
                            matched = matched[matched.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
                            if not matched.empty:
                                all_results.append(matched)
            except Exception as e:
                logger.debug(f"Fallback query with tags {tags} failed: {e}")
                continue
        
        if not all_results:
            return None
        
        combined = pd.concat(all_results, ignore_index=True)
        combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
        
        if "name" in combined.columns:
            exact_mask = combined["name"].astype(str).str.lower() == search_name_lower
            if exact_mask.any():
                combined = combined[exact_mask]
        
        if not combined.empty:
            return combined.head(1)
        
        return None
        
    except Exception as e:
        logger.warning(f"Fallback search failed: {e}")
        return None


def _dedupe_osmnx_features_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """De-duplicate an OSMnx features GeoDataFrame."""
    if gdf is None or gdf.empty:
        return gdf

    gdf2 = gdf.copy()

    try:
        gdf2 = gdf2.reset_index()
    except Exception:
        pass

    cols = set(gdf2.columns)
    if {"element_type", "osmid"}.issubset(cols):
        gdf2 = gdf2.drop_duplicates(subset=["element_type", "osmid"], keep="first")
        return gdf2

    try:
        geom_wkb = gdf2.geometry.apply(lambda g: g.wkb if g is not None else None)
        gdf2 = gdf2.loc[~geom_wkb.duplicated(keep="first")]
    except Exception:
        pass

    return gdf2


async def get_admin_boundary(
    place_name: Union[str, List[str]],
    admin_level: Optional[int] = None,
) -> str:
    """
    Get administrative boundary polygon for a named place from OpenStreetMap.
    
    Uses OSM Nominatim to geocode the place name and retrieve its boundary.
    If Nominatim fails, falls back to searching for features by name within
    the broader region (useful for neighborhoods not indexed in Nominatim).
    
    Parameters:
        place_name (str or List[str]): 
            Name of the place to get boundary for. Can be a list of fallback variants.
        admin_level (int, optional): 
            OSM admin_level to filter (2=country, 4=state, 6=county, 8=city).
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing the administrative boundary.
    """
    place_name_variants = [place_name] if isinstance(place_name, str) else place_name
    
    try:
        gdf = None
        successful_place_name = None
        used_fallback = False
        
        # Strategy 1: Try Nominatim geocoding
        for pn in place_name_variants:
            print(f"Fetching admin boundary for: {pn}")
            try:
                gdf = await run_osmnx_async(ox.geocode_to_gdf, pn)
                if gdf is not None and not gdf.empty:
                    successful_place_name = pn
                    break
            except Exception as e:
                print(f"Admin boundary lookup failed for: {pn} ({e}), trying next variant...")
                continue
        
        # Strategy 2: Fallback - search by name
        if gdf is None or gdf.empty:
            print("Nominatim geocoding failed for all variants, trying fallback search...")
            
            for pn in place_name_variants:
                search_name, broader_region = _extract_search_name_and_region(pn)
                if broader_region:
                    print(f"Fallback: searching for '{search_name}' within '{broader_region}'")
                    gdf = await _fallback_search_by_name(search_name, broader_region)
                    if gdf is not None and not gdf.empty:
                        successful_place_name = pn
                        used_fallback = True
                        break
        
        if gdf is None or gdf.empty:
            tried = "', '".join(place_name_variants)
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Could not find boundary. Tried: ['{tried}']"
            )
        
        display_place_name = place_name_variants[0]
        geojson_data = gdf.to_geo_dict()
        
        for feat in geojson_data.get("features", []):
            if "properties" not in feat:
                feat["properties"] = {}
            feat["properties"]["name"] = display_place_name
            feat["properties"]["matched_query"] = successful_place_name
            if used_fallback:
                feat["properties"]["search_method"] = "name_search_fallback"
        
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        method_note = " (via name search fallback)" if used_fallback else ""
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched administrative boundary for {display_place_name}{method_note}. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching admin boundary: {e}")
        tried = "', '".join(place_name_variants)
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch admin boundary. Tried: ['{tried}']. Error: {str(e)}"
        )


async def get_neighborhoods(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    admin_levels: Optional[List[Union[int, str]]] = None,
    include_place_fallback: bool = True,
) -> str:
    """
    Extract neighborhood boundaries from OpenStreetMap within specified area.

    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (List[float], optional): Bounding box as [north, south, east, west] in WGS84.
        admin_levels (List[Union[int, str]], optional): OSM admin levels (default [9, 10]).
        include_place_fallback (bool): Also query place=neighbourhood/suburb/quarter.

    Returns:
        GeoFahamToolResponse with GeoJSON layer containing neighborhood boundaries.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)

        if not admin_levels:
            admin_levels = [9, 10]
        admin_levels_str = [str(x) for x in admin_levels]

        boundary_admin_tags = {"boundary": "administrative", "admin_level": admin_levels_str}
        place_neighborhood_tags = {"place": ["neighbourhood", "neighborhood", "suburb", "quarter"]}

        print(f"Fetching neighborhoods from OSM with {input_type}={input_value}")

        gdf_admin = gpd.GeoDataFrame()
        gdf_place = gpd.GeoDataFrame()
        admin_query_failed = False

        try:
            if input_type == "polygon":
                polygon = get_polygon_from_geometry(input_value)
                warning = estimate_feature_count(polygon)
                if warning:
                    logger.warning(warning)
                gdf_admin = await run_osmnx_async(ox.features_from_polygon, polygon, tags=boundary_admin_tags)
            elif input_type == "place":
                gdf_admin = await run_osmnx_async(ox.features_from_place, input_value, tags=boundary_admin_tags)
            else:
                north, south, east, west = input_value
                gdf_admin = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=boundary_admin_tags)
        except Exception as e:
            admin_query_failed = True
            logger.warning(f"Admin-boundary neighborhood query failed ({e})")
            gdf_admin = gpd.GeoDataFrame()

        if not gdf_admin.empty:
            if "admin_level" in gdf_admin.columns:
                gdf_admin = gdf_admin[gdf_admin["admin_level"].astype(str).isin(admin_levels_str)]
            gdf_admin = gdf_admin[gdf_admin.geometry.notna()]
            gdf_admin = gdf_admin[gdf_admin.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]

        if include_place_fallback and (admin_query_failed or gdf_admin.empty):
            try:
                if input_type == "polygon":
                    polygon = get_polygon_from_geometry(input_value)
                    gdf_place = await run_osmnx_async(ox.features_from_polygon, polygon, tags=place_neighborhood_tags)
                elif input_type == "place":
                    gdf_place = await run_osmnx_async(ox.features_from_place, input_value, tags=place_neighborhood_tags)
                else:
                    north, south, east, west = input_value
                    gdf_place = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=place_neighborhood_tags)
            except Exception as e:
                logger.warning(f"Place-based neighborhood fallback query failed: {e}")
                gdf_place = gpd.GeoDataFrame()

            if not gdf_place.empty:
                gdf_place = gdf_place[gdf_place.geometry.notna()]
                gdf_place = gdf_place[gdf_place.geometry.geom_type.isin(["Polygon"])]

        if gdf_admin.empty and gdf_place.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No neighborhood boundaries found for the specified area."
            )

        gdf = gdf_admin if not gdf_admin.empty else gdf_place
        gdf = _dedupe_osmnx_features_gdf(gdf)

        features = osm_gdf_to_geojson_features(gdf, "neighborhoods")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)

        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} neighborhoods from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )

    except Exception as e:
        logger.exception(f"Error fetching neighborhoods: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch neighborhoods from OSM: {str(e)}"
        )


async def get_address_coordinates(
    address: Union[str, List[str]],
) -> str:
    """
    Geocode an address, POI or place name to retrieve its geographic coordinates.
    
    Works for ANY place type including POIs (hospitals, landmarks), addresses,
    neighborhoods, cities, etc.
    
    Parameters:
        address (str or List[str]): Address or place name to geocode. Can be a list of fallbacks.
    
    Returns:
        GeoFahamToolResponse with GeoJSON Point feature containing coordinates.
    """
    address_variants = [address] if isinstance(address, str) else address
    
    try:
        coords = None
        successful_address = None
        
        for addr in address_variants:
            logger.info(f"Geocoding address: {addr}")
            try:
                coords = await run_osmnx_async(ox.geocode, addr)
                if coords is not None:
                    successful_address = addr
                    break
            except Exception as e:
                logger.info(f"Geocoding failed for: {addr} ({e}), trying next variant...")
                continue
        
        if coords is None:
            tried = "', '".join(address_variants)
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Could not geocode address. Tried: ['{tried}']"
            )
        
        lat, lon = coords
        display_address = address_variants[0]
        
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": display_address,
                "display_name": display_address,
                "matched_query": successful_address,
            }
        }
        
        geojson_data = {"type": "FeatureCollection", "features": [feature]}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        logger.info(f"Geocoded '{successful_address}'.")
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Geocoded '{display_address}'. Saved as Point in {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error geocoding address: {e}")
        tried = "', '".join(address_variants)
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to geocode address. Tried: ['{tried}']. Error: {str(e)}"
        )


async def get_place_bounding_box(
    address: Union[str, List[str]],
) -> str:
    """
    Retrieve the geographic bounding box for a location using OSM Nominatim.
    
    Returns the rectangular geographic extent of the location as a GeoJSON Polygon.
    
    Parameters:
        address (str or List[str]): Location to get bounding box for. Can be a list of fallbacks.
    
    Returns:
        GeoFahamToolResponse with GeoJSON Polygon feature containing the bounding box.
    """
    address_variants = [address] if isinstance(address, str) else address
    
    try:
        gdf = None
        successful_address = None
        
        for addr in address_variants:
            logger.info(f"Getting bounding box for: {addr}")
            try:
                gdf = await run_osmnx_async(ox.geocode_to_gdf, addr)
                if gdf is not None and not gdf.empty:
                    successful_address = addr
                    break
            except Exception as e:
                logger.info(f"Bounding box lookup failed for: {addr} ({e}), trying next variant...")
                continue
        
        if gdf is None or gdf.empty:
            tried = "', '".join(address_variants)
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Could not find bounding box. Tried: ['{tried}']"
            )
        
        display_address = address_variants[0]
        bounds = gdf.total_bounds
        
        from shapely.geometry import box as shapely_box
        bbox_polygon = shapely_box(bounds[0], bounds[1], bounds[2], bounds[3])
        
        feature = {
            "type": "Feature",
            "geometry": bbox_polygon.__geo_interface__,
            "properties": {
                "name": display_address,
                "display_name": display_address,
                "matched_query": successful_address,
                "bbox": list(bounds),
            }
        }
        
        geojson_data = {"type": "FeatureCollection", "features": [feature]}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        logger.info(f"Got bounding box for '{successful_address}'.")
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Got bounding box for '{display_address}'. Saved to {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error getting bounding box: {e}")
        tried = "', '".join(address_variants)
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to get bounding box. Tried: ['{tried}']. Error: {str(e)}"
        )


async def search_feature_by_name(
    feature_name: str,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    feature_type: str = "road",
) -> str:
    """
    Search for a named linear feature (road, river, railway) and return its full geometry.
    
    For POIs, landmarks, facilities, or addresses, use get_address_coordinates instead.
    
    Parameters:
        feature_name: Name of the linear feature (e.g., "Forest Park Parkway")
        place_name: Place to constrain search (e.g., "St. Louis, Missouri, USA")
        bbox: Bounding box [north, south, east, west] as alternative to place_name
        feature_type: One of "road", "water", "railway", "bridge", "river", "stream"
    
    Returns:
        GeoFahamToolResponse with GeoJSON containing all matched feature geometries.
    """
    try:
        if not place_name and not bbox:
            return build_error_response(
                source=AGENT_NAME,
                error_message="Either place_name or bbox is required to define search area."
            )
        
        print(f"Searching for {feature_type} by name: '{feature_name}' in {place_name or bbox}")
        
        type_tags = {
            "road": {"highway": True, "name": feature_name},
            "water": {"natural": "water", "name": feature_name},
            "railway": {"railway": True, "name": feature_name},
            "bridge": {"bridge": True, "name": feature_name},
            "river": {"waterway": "river", "name": feature_name},
            "stream": {"waterway": "stream", "name": feature_name},
        }
        
        tags = type_tags.get(feature_type.lower())
        if not tags:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Unknown feature_type: '{feature_type}'. Supported: {list(type_tags.keys())}"
            )
        
        if place_name:
            gdf = await run_osmnx_async(ox.features_from_place, place_name, tags=tags)
        else:
            north, south, east, west = bbox
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if gdf.empty:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Could not find {feature_type}: '{feature_name}'" + (f" in {place_name}" if place_name else "")
            )
        
        if "name" in gdf.columns:
            exact_match = gdf[gdf["name"].str.lower() == feature_name.lower()]
            if not exact_match.empty:
                gdf = exact_match.copy()
        
        gdf["searched_name"] = feature_name
        
        features = osm_gdf_to_geojson_features(gdf, feature_type=feature_type)
        
        if not features:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Could not find {feature_type}: '{feature_name}'" + (f" in {place_name}" if place_name else "")
            )
        
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        geom_types = set(f.get("geometry", {}).get("type", "unknown") for f in features)
        geom_type_str = ", ".join(geom_types)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Found {len(features)} segment(s) of {feature_type} '{feature_name}' ({geom_type_str}). File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error searching for feature by name: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to search for '{feature_name}': {str(e)}"
        )


def _cluster_coordinates(
    coords_list: List[Tuple[float, float]],
    properties_list: List[dict],
    sources_list: List[str],
    distance_m: float,
) -> Tuple[List[Tuple[float, float]], List[dict], List[str]]:
    """
    Cluster nearby coordinates to reduce redundant geocoding calls.
    
    Uses DBSCAN clustering to group points within distance_m of each other.
    Returns cluster centroids with merged properties.
    
    Args:
        coords_list: List of (lat, lon) tuples
        properties_list: Properties for each coordinate
        sources_list: Geometry source for each coordinate
        distance_m: Clustering distance in meters
    
    Returns:
        Tuple of (clustered_coords, merged_properties, merged_sources)
    """
    from sklearn.cluster import DBSCAN
    import numpy as np
    from shapely.geometry import Point
    from pyproj import Transformer
    
    if len(coords_list) <= 1:
        return coords_list, properties_list, sources_list
    
    # Convert to numpy array for DBSCAN
    coords_array = np.array([(lat, lon) for lat, lon in coords_list])
    
    # Get approximate center for UTM projection
    center_lat = np.mean(coords_array[:, 0])
    center_lon = np.mean(coords_array[:, 1])
    
    # Determine UTM zone
    utm_zone = int((center_lon + 180) // 6) + 1
    utm_epsg = 32600 + utm_zone if center_lat >= 0 else 32700 + utm_zone
    
    # Transform to UTM for distance-based clustering
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    utm_coords = np.array([transformer.transform(lon, lat) for lat, lon in coords_list])
    
    # DBSCAN clustering
    clustering = DBSCAN(eps=distance_m, min_samples=1).fit(utm_coords)
    labels = clustering.labels_
    
    # Group by cluster and compute centroids
    clustered_coords = []
    merged_properties = []
    merged_sources = []
    
    unique_labels = set(labels)
    for label in unique_labels:
        mask = labels == label
        cluster_indices = np.where(mask)[0]
        
        # Compute centroid of cluster
        cluster_lats = coords_array[mask, 0]
        cluster_lons = coords_array[mask, 1]
        centroid_lat = np.mean(cluster_lats)
        centroid_lon = np.mean(cluster_lons)
        clustered_coords.append((centroid_lat, centroid_lon))
        
        # Merge properties from all points in cluster
        merged_props = {}
        for idx in cluster_indices:
            for key, val in properties_list[idx].items():
                if key not in merged_props:
                    merged_props[key] = val
                elif merged_props[key] != val:
                    # Multiple different values - store as list or comma-separated
                    if isinstance(merged_props[key], list):
                        if val not in merged_props[key]:
                            merged_props[key].append(val)
                    else:
                        merged_props[key] = [merged_props[key], val]
        
        # Add cluster metadata
        merged_props["_cluster_size"] = len(cluster_indices)
        if len(cluster_indices) > 1:
            merged_props["_clustered_from"] = len(cluster_indices)
        
        merged_properties.append(merged_props)
        
        # Take first source (they're likely all the same type)
        merged_sources.append(sources_list[cluster_indices[0]])
    
    return clustered_coords, merged_properties, merged_sources


async def reverse_geocode(
    coordinates: Optional[List[List[float]]] = None,
    geojson_path: Optional[str] = None,
    zoom: int = 18,
    cluster_distance_m: float = 100,
) -> str:
    """
    Reverse geocode coordinates to get addresses using OSM Nominatim.
    
    Accepts either raw coordinates or a GeoJSON file. For GeoJSON input with
    non-Point geometries (Polygon, LineString), uses the centroid for geocoding.
    
    Nearby points are clustered to avoid redundant API calls (e.g., parallel 
    road carriageways that represent the same location).
    
    Parameters:
        coordinates (List[List[float]], optional): List of [lat, lon] coordinate pairs.
            Example: [[20.798, -156.331], [21.306, -157.858]]
        geojson_path (str, optional): Path to GeoJSON file with features.
            Points are used directly; Polygons/LineStrings use their centroid.
        zoom (int): Level of detail (0-18). Higher = more detailed address. Default 18.
        cluster_distance_m (float): Merge points within this distance (meters). Default 100m.
            Points closer than this are considered the same location and geocoded once.
            Set to 0 to disable clustering.
    
    Returns:
        GeoFahamToolResponse with GeoJSON Point features containing address information.
    """
    try:
        coords_list = []
        original_properties = []
        geometry_sources = []  # Track if point was original or computed centroid
        
        # Case 1: GeoJSON file input
        if geojson_path:
            logger.info(f"Reverse geocoding features from: {geojson_path}")
            gdf = gpd.read_file(geojson_path)
            
            if gdf.empty:
                return build_error_response(
                    source=AGENT_NAME,
                    error_message="GeoJSON file contains no features."
                )
            
            for idx, row in gdf.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                
                # Get point: use directly for Point, compute centroid for others
                if geom.geom_type == "Point":
                    point = geom
                    geom_source = "original"
                else:
                    point = geom.centroid
                    geom_source = f"centroid_of_{geom.geom_type}"
                
                coords_list.append((point.y, point.x))  # (lat, lon)
                geometry_sources.append(geom_source)
                
                # Preserve original properties
                props = row.drop("geometry").to_dict()
                original_properties.append(props)
        
        # Case 2: Raw coordinates list
        elif coordinates:
            logger.info(f"Reverse geocoding {len(coordinates)} coordinate(s)")
            for coord in coordinates:
                if len(coord) != 2:
                    return build_error_response(
                        source=AGENT_NAME,
                        error_message=f"Invalid coordinate format: {coord}. Expected (lat, lon) tuple."
                    )
                coords_list.append((coord[0], coord[1]))
                geometry_sources.append("original")
                original_properties.append({})
        
        else:
            return build_error_response(
                source=AGENT_NAME,
                error_message="Must provide either coordinates list or geojson_path."
            )
        
        if not coords_list:
            return build_error_response(
                source=AGENT_NAME,
                error_message="No valid geometries found to geocode."
            )
        
        # Cluster nearby points to avoid redundant geocoding (e.g., parallel carriageways)
        if cluster_distance_m > 0 and len(coords_list) > 1:
            coords_list, original_properties, geometry_sources = _cluster_coordinates(
                coords_list, original_properties, geometry_sources, cluster_distance_m
            )
            logger.info(f"After clustering ({cluster_distance_m}m): {len(coords_list)} unique locations")
        
        # Perform reverse geocoding
        if len(coords_list) == 1:
            results = [await reverse_geocode_nominatim(coords_list[0][0], coords_list[0][1], zoom=zoom)]
        else:
            results = await batch_reverse_geocode(coords_list, zoom=zoom)
        
        # Build GeoJSON features
        features = []
        success_count = 0
        
        for i, (coord, result) in enumerate(zip(coords_list, results)):
            lat_val, lon_val = coord
            
            # Start with original properties if available
            props = dict(original_properties[i]) if i < len(original_properties) else {}
            props["input_lat"] = lat_val
            props["input_lon"] = lon_val
            props["geometry_source"] = geometry_sources[i] if i < len(geometry_sources) else "original"
            
            if result:
                success_count += 1
                props["display_name"] = result.get("display_name", "")
                props["osm_type"] = result.get("osm_type", "")
                props["osm_id"] = result.get("osm_id", "")
                
                # Extract address components
                address = result.get("address", {})
                for key in ["house_number", "road", "neighbourhood", "suburb", 
                           "city", "town", "village", "county", "state", 
                           "postcode", "country", "country_code"]:
                    if key in address:
                        props[f"addr_{key}"] = address[key]
            else:
                props["display_name"] = None
                props["geocode_status"] = "failed"
            
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon_val, lat_val]},
                "properties": props,
            }
            features.append(feature)
        
        if success_count == 0:
            return build_empty_response(
                source=AGENT_NAME,
                summary=f"Reverse geocoding failed for all {len(coords_list)} coordinate(s)."
            )
        
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        summary = f"Reverse geocoded {success_count}/{len(coords_list)} coordinate(s). File: {artifact.path}"
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=summary,
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error in reverse geocoding: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to reverse geocode: {str(e)}"
        )
