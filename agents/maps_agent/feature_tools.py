# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM Feature Extraction Tools - Roads, Buildings, Waterways, Bridges, POIs, Landuse, Natural, Infrastructure.

These tools extract geographic features from OpenStreetMap for disaster assessment.
"""

import logging
from typing import List, Optional

import geopandas as gpd
import osmnx as ox

from agents.core.constants import AGENT_NAMES
from agents.shared.geojson import results_to_geojson
from agents.shared.responses import (
    build_layer_response,
    build_empty_response,
    build_error_response,
)

from agents.maps_agent.categories import (
    RoadCategory,
    BuildingCategory,
    WaterwayCategory,
    POICategory,
    LanduseCategory,
    NaturalCategory,
    InfrastructureCategory,
)
from agents.maps_agent.utils import (
    get_polygon_from_geometry,
    osm_gdf_to_geojson_features,
    run_osmnx_async,
    validate_geometry_input,
    estimate_feature_count,
    OSM_ROAD_TYPES,
    OSM_BUILDING_TYPES,
    OSM_WATERWAY_TYPES,
    OSM_BRIDGE_TAGS,
    OSM_INFRASTRUCTURE_TYPES,
    OSM_LANDUSE_TYPES,
    OSM_NATURAL_FEATURES,
    OSM_POI_CATEGORIES,
)

logger = logging.getLogger(__name__)
AGENT_NAME = AGENT_NAMES["MAPS_AGENT"]


async def get_roads(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    road_category: RoadCategory = RoadCategory.ALL,
    custom_highway_types: Optional[List[str]] = None,
    include_bridges: bool = False,
) -> str:
    """
    Extract road network from OpenStreetMap within specified area.
    
    This tool retrieves road/highway features from OSM, which is essential for 
    disaster damage assessment as it includes all road types from highways to 
    footpaths, including bridge and tunnel attributes.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode (e.g., "St. Louis, Missouri, USA").
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        road_category (RoadCategory): Category of roads to retrieve (MAJOR, MINOR, PATHS, SERVICE, ALL).
        custom_highway_types (List[str], optional): Custom list of OSM highway types to filter.
        include_bridges (bool): If True, only returns roads that are bridges.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing road features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        if custom_highway_types:
            highway_filter = custom_highway_types
        else:
            highway_filter = OSM_ROAD_TYPES.get(road_category.value)
        
        print(f"Fetching roads from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            warning = estimate_feature_count(polygon)
            if warning:
                logger.warning(warning)
            gdf = await run_osmnx_async(
                ox.features_from_polygon, polygon,
                tags={"highway": highway_filter if highway_filter else True}
            )
        elif input_type == "place":
            gdf = await run_osmnx_async(
                ox.features_from_place, input_value,
                tags={"highway": highway_filter if highway_filter else True}
            )
        else:  # bbox
            north, south, east, west = input_value
            gdf = await run_osmnx_async(
                ox.features_from_bbox, north, south, east, west,
                tags={"highway": highway_filter if highway_filter else True}
            )
        
        if include_bridges and not gdf.empty:
            if "bridge" in gdf.columns:
                gdf = gdf[gdf["bridge"].notna()]
        
        if not gdf.empty:
            gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No roads found for the specified area and filters."
            )
        
        features = osm_gdf_to_geojson_features(gdf, "roads")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        category_desc = road_category.value if not custom_highway_types else f"custom ({', '.join(custom_highway_types)})"
        bridge_desc = " (bridges only)" if include_bridges else ""
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {category_desc} roads{bridge_desc} from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching roads: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch roads from OSM: {str(e)}"
        )


async def get_buildings(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    building_category: BuildingCategory = BuildingCategory.ALL,
    custom_building_types: Optional[List[str]] = None,
) -> str:
    """
    Extract building footprints from OpenStreetMap within specified area.
    
    Essential for disaster damage assessment to identify building locations,
    types, and attributes like height and levels.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        building_category (BuildingCategory): Category of buildings to retrieve.
        custom_building_types (List[str], optional): Custom list of OSM building types.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing building footprints.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        if custom_building_types:
            building_filter = custom_building_types
        else:
            building_filter = OSM_BUILDING_TYPES.get(building_category.value, True)
        
        if isinstance(building_filter, list):
            tags = {"building": building_filter}
        else:
            tags = {"building": True}
        
        print(f"Fetching buildings from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)

        if not gdf.empty:
            gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No buildings found for the specified area and filters."
            )
        
        features = osm_gdf_to_geojson_features(gdf, "buildings")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {building_category.value} buildings from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching buildings: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch buildings from OSM: {str(e)}"
        )


async def get_waterways(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    waterway_category: WaterwayCategory = WaterwayCategory.ALL,
    custom_waterway_types: Optional[List[str]] = None,
) -> str:
    """
    Extract waterways (rivers, streams, canals) from OpenStreetMap.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        waterway_category (WaterwayCategory): Category of waterways (RIVERS, STREAMS, ALL).
        custom_waterway_types (List[str], optional): Custom list of OSM waterway types.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing waterway features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        if custom_waterway_types:
            waterway_filter = custom_waterway_types
        else:
            waterway_filter = OSM_WATERWAY_TYPES.get(waterway_category.value)
        
        if waterway_filter:
            tags = {"waterway": waterway_filter}
        else:
            tags = {"waterway": True}
        
        print(f"Fetching waterways from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if not gdf.empty:
            gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString", "Polygon", "MultiPolygon"])]
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No waterways found for the specified area and filters."
            )
        
        features = osm_gdf_to_geojson_features(gdf, "waterways")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {waterway_category.value} waterways from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching waterways: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch waterways from OSM: {str(e)}"
        )


async def get_bridges(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
) -> str:
    """
    Extract bridges from OpenStreetMap within specified area.
    
    Bridges are critical infrastructure for disaster assessment. Returns features
    where bridge=yes, including highways and railways that cross water/roads.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing bridge features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        tags = OSM_BRIDGE_TAGS
        
        print(f"Fetching bridges from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if not gdf.empty:
            if "bridge" in gdf.columns:
                gdf = gdf[gdf["bridge"].notna() & (gdf["bridge"] != "no")]
            gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString", "Polygon", "MultiPolygon"])]
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No bridges found for the specified area."
            )
        
        features = osm_gdf_to_geojson_features(gdf, "bridges")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} bridges from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching bridges: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch bridges from OSM: {str(e)}"
        )


async def get_pois(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    poi_category: POICategory = POICategory.EMERGENCY,
) -> str:
    """
    Extract Points of Interest from OpenStreetMap for disaster assessment.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        poi_category (POICategory): Category of POIs (EMERGENCY, EDUCATION, HEALTHCARE, SHELTER, FOOD, TRANSPORTATION, UTILITIES).
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing POI features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        tags = OSM_POI_CATEGORIES.get(poi_category.value, {})
        if not tags:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Unknown POI category: {poi_category}"
            )
        
        print(f"Fetching {poi_category.value} POIs from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary=f"No {poi_category.value} POIs found for the specified area."
            )
        
        features = osm_gdf_to_geojson_features(gdf, f"pois_{poi_category.value}")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {poi_category.value} POIs from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching POIs: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch POIs from OSM: {str(e)}"
        )


async def get_landuse(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    landuse_category: LanduseCategory = LanduseCategory.ALL,
    custom_landuse_types: Optional[List[str]] = None,
) -> str:
    """
    Extract land use areas from OpenStreetMap.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        landuse_category (LanduseCategory): Category of land use (URBAN, AGRICULTURE, NATURAL, RECREATION, ALL).
        custom_landuse_types (List[str], optional): Custom list of OSM landuse types.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing landuse features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        if custom_landuse_types:
            landuse_filter = custom_landuse_types
        else:
            landuse_filter = OSM_LANDUSE_TYPES.get(landuse_category.value)
        
        if landuse_filter:
            tags = {"landuse": landuse_filter}
        else:
            tags = {"landuse": True}
        
        print(f"Fetching landuse from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if not gdf.empty:
            gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary="No landuse areas found for the specified area and filters."
            )
        
        features = osm_gdf_to_geojson_features(gdf, "landuse")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {landuse_category.value} landuse areas from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching landuse: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch landuse from OSM: {str(e)}"
        )


async def get_natural_features(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    natural_category: NaturalCategory = NaturalCategory.WATER,
) -> str:
    """
    Extract natural features from OpenStreetMap.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        natural_category (NaturalCategory): Category of features (WATER, VEGETATION, TERRAIN, COASTAL).
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing natural features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        tags = OSM_NATURAL_FEATURES.get(natural_category.value, {"natural": True})
        
        print(f"Fetching {natural_category.value} natural features from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary=f"No {natural_category.value} natural features found."
            )
        
        features = osm_gdf_to_geojson_features(gdf, f"natural_{natural_category.value}")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {natural_category.value} natural features from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching natural features: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch natural features from OSM: {str(e)}"
        )


async def get_infrastructure(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    infrastructure_category: InfrastructureCategory = InfrastructureCategory.POWER,
) -> str:
    """
    Extract infrastructure features from OpenStreetMap.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        infrastructure_category (InfrastructureCategory): Category (POWER, COMMUNICATION, WATER_SUPPLY, SEWAGE, TRANSPORT).
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing infrastructure features.
    """
    try:
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        tags = OSM_INFRASTRUCTURE_TYPES.get(infrastructure_category.value, {})
        if not tags:
            return build_error_response(
                source=AGENT_NAME,
                error_message=f"Unknown infrastructure category: {infrastructure_category}"
            )
        
        print(f"Fetching {infrastructure_category.value} infrastructure from OSM with {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary=f"No {infrastructure_category.value} infrastructure found."
            )
        
        features = osm_gdf_to_geojson_features(gdf, f"infrastructure_{infrastructure_category.value}")
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(features)} {infrastructure_category.value} infrastructure features from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching infrastructure: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch infrastructure from OSM: {str(e)}"
        )


async def get_features_by_tags(
    geojson_path: Optional[str] = None,
    place_name: Optional[str] = None,
    bbox: Optional[List[float]] = None,
    tags: dict = None,
    feature_type_name: str = "custom",
) -> str:
    """
    Extract features from OpenStreetMap using custom OSM tags.
    
    Flexible tool for querying any OSM feature type using custom tag combinations.
    Refer to https://wiki.openstreetmap.org/wiki/Map_Features for OSM tag reference.
    
    Parameters:
        geojson_path (str, optional): Path to GeoJSON file defining the Area of Interest.
        place_name (str, optional): Name of place to geocode.
        bbox (tuple, optional): Bounding box as (north, south, east, west) in WGS84.
        tags (dict): OSM tags to query. Examples:
            - {"amenity": "hospital"}
            - {"highway": ["primary", "secondary"]}
            - {"building": True, "amenity": "school"}
        feature_type_name (str): Name to identify the feature type in output.
            
    Returns:
        GeoFahamToolResponse with GeoJSON layer containing matching features.
    """
    try:
        if not tags:
            return build_error_response(
                source=AGENT_NAME,
                error_message="Tags parameter is required for custom feature queries."
            )
        
        input_type, input_value = validate_geometry_input(geojson_path, place_name, bbox)
        
        print(f"Fetching {feature_type_name} features from OSM with tags={tags}, {input_type}={input_value}")
        
        if input_type == "polygon":
            polygon = get_polygon_from_geometry(input_value)
            gdf = await run_osmnx_async(ox.features_from_polygon, polygon, tags=tags)
        elif input_type == "place":
            gdf = await run_osmnx_async(ox.features_from_place, input_value, tags=tags)
        else:
            north, south, east, west = input_value
            gdf = await run_osmnx_async(ox.features_from_bbox, north, south, east, west, tags=tags)
        
        if gdf.empty:
            return build_empty_response(
                source=AGENT_NAME,
                summary=f"No {feature_type_name} features found for the specified tags and area."
            )
        
        features = osm_gdf_to_geojson_features(gdf, feature_type_name)
        geojson_data = {"type": "FeatureCollection", "features": features}
        artifact = await results_to_geojson(geojson_data, compute_stats=True)
        
        return build_layer_response(
            source=AGENT_NAME,
            artifact_path=artifact.path,
            summary=f"Fetched {len(geojson_data['features'])} {feature_type_name} features from OSM. File: {artifact.path}",
            features_count=artifact.features_count,
            stats=artifact.stats,
            property_keys=artifact.property_keys,
            geom_types=artifact.geom_types,
        )
        
    except Exception as e:
        logger.exception(f"Error fetching custom features: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=f"Failed to fetch features from OSM: {str(e)}"
        )
