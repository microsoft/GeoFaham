# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Utility functions for OSM Maps Agent.

This module provides helper functions for:
- Geometry processing and normalization
- Feature property extraction and standardization  
- Coordinate/boundary conversion utilities
- OSMnx result to GeoJSON conversion
"""

import geopandas as gpd
import osmnx as ox
from shapely.geometry import box, Polygon, MultiPolygon, Point
from shapely.ops import unary_union
from typing import Any, Dict, List, Optional, Tuple, Union
import asyncio
from functools import partial
import logging
import aiohttp

from agents.core.config import get_config

logger = logging.getLogger(__name__)

# =============================================================================
# OSMnx Configuration - CENTRALIZED SETTINGS
# =============================================================================

def _configure_osmnx():
    """Configure OSMnx with settings from config."""
    config = get_config()
    
    ox.settings.log_console = False
    ox.settings.use_cache = True
    ox.settings.cache_folder = config.osm.cache_folder
    ox.settings.nominatim_url = config.osm.nominatim_url
    ox.settings.overpass_url = config.osm.overpass_url
    
    logger.info(f"OSMnx configured with Nominatim: {config.osm.nominatim_url}, Overpass: {config.osm.overpass_url}")

# Configure on module load
_configure_osmnx()


# OSM Tag Categories for disaster assessment
OSM_ROAD_TYPES = {
    "major": ["motorway", "trunk", "primary", "secondary"],
    "minor": ["tertiary", "residential", "unclassified", "living_street"],
    "paths": ["footway", "cycleway", "path", "pedestrian", "track"],
    "service": ["service", "driveway"],
    "all": None,  # All road types
}

OSM_BUILDING_TYPES = {
    "residential": ["house", "apartments", "residential", "detached", "terrace", "semi"],
    "commercial": ["commercial", "retail", "office", "supermarket", "shop"],
    "industrial": ["industrial", "warehouse", "factory", "manufacturing"],
    "public": ["public", "government", "civic", "school", "hospital", "university"],
    "religious": ["church", "mosque", "temple", "synagogue", "chapel"],
    "emergency": ["fire_station", "police", "hospital"],
    "all": True,  # All building types
}

OSM_WATERWAY_TYPES = {
    "rivers": ["river", "canal"],
    "streams": ["stream", "drain", "ditch"],
    "all": ["river", "stream", "canal", "drain", "ditch", "brook"],
}

OSM_BRIDGE_TAGS = {
    "bridge": ["yes", "viaduct", "aqueduct", "movable", "cantilever", "covered"],
}

OSM_INFRASTRUCTURE_TYPES = {
    "power": {"power": ["line", "tower", "pole", "substation", "plant"]},
    "communication": {"telecom": True, "tower": ["communication", "observation"]},
    "water_supply": {"man_made": ["water_tower", "reservoir_covered", "water_works"]},
    "sewage": {"man_made": ["wastewater_plant"], "amenity": ["wastewater"]},
    "transport": {"railway": True, "aeroway": True, "route": ["ferry", "bus"]},
}

OSM_LANDUSE_TYPES = {
    "urban": ["residential", "commercial", "industrial", "retail"],
    "agriculture": ["farmland", "farmyard", "orchard", "vineyard", "meadow"],
    "natural": ["forest", "grass", "wood", "wetland", "scrub"],
    "recreation": ["recreation_ground", "park", "cemetery", "allotments"],
    "all": None,
}

OSM_NATURAL_FEATURES = {
    "water": {"natural": ["water", "bay", "strait", "wetland"], "landuse": ["reservoir", "basin"]},
    "vegetation": {"natural": ["wood", "scrub", "grassland", "heath"]},
    "terrain": {"natural": ["cliff", "peak", "ridge", "valley", "sand", "beach"]},
    "coastal": {"natural": ["coastline", "beach", "shoal"]},
}

OSM_POI_CATEGORIES = {
    "emergency": {"amenity": ["hospital", "clinic", "doctors", "fire_station", "police"]},
    "education": {"amenity": ["school", "university", "college", "kindergarten", "library"]},
    "healthcare": {"amenity": ["hospital", "clinic", "doctors", "pharmacy", "dentist"]},
    "shelter": {"amenity": ["shelter", "community_centre", "social_facility"], "building": ["civic"]},
    "food": {"amenity": ["restaurant", "cafe", "fast_food", "food_court"]},
    "transportation": {"amenity": ["fuel", "bus_station", "ferry_terminal"], "railway": ["station"]},
    "utilities": {"amenity": ["water_point", "drinking_water"], "man_made": ["water_well"]},
}


def get_bbox_from_geometry(geometry: Union[gpd.GeoDataFrame, Dict, str]) -> Tuple[float, float, float, float]:
    """
    Extract bounding box from various geometry formats.
    
    Args:
        geometry: GeoDataFrame, GeoJSON dict, or file path
        
    Returns:
        Tuple of (north, south, east, west) for osmnx
    """
    if isinstance(geometry, str):
        gdf = gpd.read_file(geometry)
    elif isinstance(geometry, dict):
        gdf = gpd.GeoDataFrame.from_features(geometry.get("features", [geometry]))
    elif isinstance(geometry, gpd.GeoDataFrame):
        gdf = geometry
    else:
        raise ValueError(f"Unsupported geometry type: {type(geometry)}")
    
    gdf = gdf.set_crs(epsg=4326, allow_override=True)
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    return bounds[3], bounds[1], bounds[2], bounds[0]  # north, south, east, west


def geometries_to_aoi(geometries: List, use_convex_hull: bool = True) -> Polygon:
    """
    Convert multiple geometries to a single AOI polygon.
    
    Handles scattered/disconnected geometries (e.g., flood extents, damage points)
    by computing the convex hull - the smallest convex polygon containing all inputs.
    
    Args:
        geometries: List of Shapely geometries
        use_convex_hull: If True, return convex hull for MultiPolygon results.
                        If False, return the raw unary_union result.
    
    Returns:
        Single Shapely Polygon representing the AOI
    """
    if not geometries:
        raise ValueError("No geometries provided")
    
    merged = unary_union(geometries)
    
    if use_convex_hull and merged.geom_type == 'MultiPolygon':
        logger.info(f"Converting MultiPolygon ({len(merged.geoms)} parts) to convex hull AOI")
        return merged.convex_hull
    
    return merged


def get_polygon_from_geometry(geometry: Union[gpd.GeoDataFrame, Dict, str]) -> Polygon:
    """
    Extract unified polygon from various geometry formats.
    
    For multi-feature inputs (e.g., multiple flood extent polygons), computes
    the convex hull to create a single AOI representing the affected region.
    
    Args:
        geometry: GeoDataFrame, GeoJSON dict, or file path
        
    Returns:
        Shapely Polygon (convex hull if input had multiple features)
    """
    if isinstance(geometry, str):
        gdf = gpd.read_file(geometry)
    elif isinstance(geometry, dict):
        gdf = gpd.GeoDataFrame.from_features(geometry.get("features", [geometry]))
    elif isinstance(geometry, gpd.GeoDataFrame):
        gdf = geometry
    else:
        raise ValueError(f"Unsupported geometry type: {type(geometry)}")
    
    gdf = gdf.set_crs(epsg=4326, allow_override=True)
    
    # Use bounding box for large feature sets to avoid expensive/fragile unary_union
    # This handles cases where flood extents (many polygons) are passed instead of a simple boundary
    if len(gdf) > 100:
        logger.info(f"Large geometry input ({len(gdf)} features) - using bounding box as AOI")
        return box(*gdf.total_bounds)
    
    return geometries_to_aoi(list(gdf.geometry), use_convex_hull=True)


def standardize_properties(gdf: gpd.GeoDataFrame, feature_type: str) -> gpd.GeoDataFrame:
    """
    Standardize property columns for consistent output.
    
    Args:
        gdf: GeoDataFrame with OSM features
        feature_type: Type of features (roads, buildings, etc.)
        
    Returns:
        GeoDataFrame with standardized properties
    """
    if gdf.empty:
        return gdf
    
    # Common columns to keep based on feature type
    common_cols = ["name", "geometry"]
    
    type_specific_cols = {
        "roads": ["highway", "surface", "lanes", "maxspeed", "oneway", "bridge", "tunnel", "access"],
        "buildings": ["building", "building:levels", "height", "addr:street", "addr:housenumber", "amenity"],
        "waterways": ["waterway", "name", "width", "intermittent", "tunnel"],
        "bridges": ["bridge", "highway", "railway", "layer", "name"],
        "pois": ["amenity", "shop", "tourism", "name", "addr:street", "opening_hours", "phone"],
        "landuse": ["landuse", "name", "area"],
        "natural": ["natural", "name", "water", "wetland"],
        "infrastructure": ["power", "telecom", "man_made", "railway", "aeroway"],
        "neighborhoods": [
            "place",
            "boundary",
            "admin_level",
            "population",
            "wikidata",
            "addr:city",
            "addr:postcode",
        ],
    }
    
    cols_to_keep = common_cols + type_specific_cols.get(feature_type, [])
    cols_not_to_keep  =["geometry", "website", "wikidata", "wikipedia", "opening_hours"] 
    # Keep only existing columns
    available_cols = [col for col in cols_to_keep if col in gdf.columns]
    extra_cols = [col for col in gdf.columns if col not in available_cols and col not in cols_not_to_keep and ":" not in col]
    
    # Keep some extra relevant columns (up to 10)
    available_cols.extend(extra_cols[:10])
    
    return gdf[available_cols].copy()


def osm_gdf_to_geojson_features(gdf: gpd.GeoDataFrame, feature_type: str) -> List[Dict[str, Any]]:
    """
    Convert OSMnx GeoDataFrame to GeoJSON features list with normalized schema.
    
    Ensures all features have the same property keys for consistent PostGIS CTE usage.
    Missing properties are set to null to maintain schema consistency.
    
    Args:
        gdf: GeoDataFrame with OSM data
        feature_type: Type of features for property standardization
        
    Returns:
        List of GeoJSON feature dictionaries with normalized properties
    """
    if gdf.empty:
        return []
    
    # Standardize properties
    gdf = standardize_properties(gdf, feature_type)
    
    # Reset index to avoid index-related issues
    gdf = gdf.reset_index(drop=True)
    
    # Handle duplicate column names by renaming them
    cols = list(gdf.columns)
    seen = {}
    new_cols = []
    for col in cols:
        # replace : with _ in col name
        col = col.replace(":", "_")
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    gdf.columns = new_cols
    
    # Convert to GeoJSON
    geojson = gdf.to_geo_dict()
    
    # First pass: Clean up properties and collect all unique keys
    all_property_keys = set()
    features = []
    
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        
        # Remove None values and internal osm columns
        cleaned_props = {}
        for k, v in props.items():
            if v is not None and not k.startswith("_") and k not in ["osmid", "element_type"]:
                # Handle list values by joining
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v if x is not None)
                cleaned_props[k] = v
        
        # Add feature type
        cleaned_props["osm_feature_type"] = feature_type
        
        # Collect all keys for schema normalization
        all_property_keys.update(cleaned_props.keys())
        
        feat["properties"] = cleaned_props
        features.append(feat)
    
    # Second pass: Normalize schema - ensure all features have all keys
    for feat in features:
        props = feat["properties"]
        for key in all_property_keys:
            if key not in props:
                props[key] = None  # Set missing properties to null
    
    return features


async def run_osmnx_async(func, *args, **kwargs):
    """
    Run OSMnx function asynchronously using thread pool.
    
    OSMnx is not natively async, so we run it in a thread pool executor.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def reverse_geocode_nominatim(
    lat: float,
    lon: float,
    zoom: int = 18,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Reverse geocode coordinates to address using Nominatim API.
    
    Uses the configured proxy URL from config.osm.nominatim_url.
    
    Args:
        lat: Latitude in WGS84
        lon: Longitude in WGS84
        zoom: Level of detail (0-18, higher = more detailed address)
        timeout: Request timeout in seconds
        
    Returns:
        Dict with address information or None if geocoding failed.
        Keys include: display_name, address (detailed breakdown), lat, lon
    """
    config = get_config()
    base_url = config.osm.nominatim_url.rstrip("/")
    
    # Nominatim reverse endpoint
    url = f"{base_url}/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": zoom,
        "addressdetails": 1,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"User-Agent": "GeoFaham/1.0"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "error" in data:
                        logger.warning(f"Nominatim reverse geocode error: {data['error']}")
                        return None
                    return data
                else:
                    logger.warning(f"Nominatim reverse geocode failed with status {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.warning(f"Nominatim reverse geocode timed out for ({lat}, {lon})")
        return None
    except Exception as e:
        logger.warning(f"Nominatim reverse geocode error: {e}")
        return None


async def batch_reverse_geocode(
    coordinates: List[Tuple[float, float]],
    zoom: int = 18,
    delay: float = 0.1,
) -> List[Optional[Dict[str, Any]]]:
    """
    Batch reverse geocode multiple coordinates with rate limiting.
    
    Args:
        coordinates: List of (lat, lon) tuples
        zoom: Level of detail for addresses
        delay: Delay between requests in seconds (for rate limiting)
        
    Returns:
        List of address dicts (or None for failed lookups), same order as input
    """
    results = []
    for i, (lat, lon) in enumerate(coordinates):
        if i > 0:
            await asyncio.sleep(delay)
        result = await reverse_geocode_nominatim(lat, lon, zoom=zoom)
        results.append(result)
    return results


def build_tags_from_category(
    category: str,
    category_mapping: Dict[str, Any],
    custom_values: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Build OSM tags dict from category name.
    
    Args:
        category: Category name (e.g., "major" for roads)
        category_mapping: Mapping dict for the feature type
        custom_values: Optional list of custom values to filter
        
    Returns:
        Tags dict for OSMnx query
    """
    if category not in category_mapping:
        raise ValueError(f"Unknown category: {category}. Available: {list(category_mapping.keys())}")
    
    values = category_mapping[category]
    
    if custom_values:
        values = custom_values
    
    return values


def validate_geometry_input(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None
) -> Tuple[str, Any]:
    """
    Validate and determine geometry input type.
    
    Args:
        geojson_path: Path to GeoJSON file
        place_name: Name of place to geocode
        bbox: Bounding box as list of 4 floats [north, south, east, west]
    
    Returns:
        Tuple of (input_type, value) where input_type is 'polygon', 'place', or 'bbox'
    """
    # Convert list to tuple for bbox if needed
    if bbox is not None and isinstance(bbox, list):
        if len(bbox) != 4:
            raise ValueError("bbox must have exactly 4 elements: [north, south, east, west]")
        bbox = tuple(bbox)
    
    inputs = [
        ("polygon", geojson_path),
        ("place", place_name),
        ("bbox", bbox)
    ]
    
    valid_inputs = [(t, v) for t, v in inputs if v is not None]
    
    if len(valid_inputs) == 0:
        raise ValueError("Must provide one of: geojson_path, place_name, or bbox")
    
    if len(valid_inputs) > 1:
        # Prefer polygon > place > bbox
        return valid_inputs[0]
    
    return valid_inputs[0]


def estimate_feature_count(polygon: Polygon) -> str:
    """
    Estimate if query might return too many features based on area.
    
    Args:
        polygon: Query polygon
        
    Returns:
        Warning message if area is large, empty string otherwise
    """
    # Approximate area in km² (rough, at equator)
    area_degrees = polygon.area
    area_km2 = area_degrees * 111 * 111  # Very rough approximation
    
    if area_km2 > 1000:
        return f"Warning: Large area (~{area_km2:.0f} km²). Query may be slow or timeout."
    elif area_km2 > 500:
        return f"Note: Moderate area (~{area_km2:.0f} km²). Consider filtering to specific categories."
    
    return ""
