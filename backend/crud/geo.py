# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import json
from typing import List

def parse_geojson_to_multipolygon(geojson_obj: dict) -> str:
    """Return a GeoJSON string for a MultiPolygon (or Polygon coerced to MultiPolygon).
    Accepts Feature, FeatureCollection, Feature, or raw geometry object.
    Minimal validation; DB/PostGIS will enforce geometry rules.
    """
    if not isinstance(geojson_obj, dict):
        raise ValueError("GeoJSON must be an object")
    if geojson_obj.get('type') == 'FeatureCollection':
        geoms = []
        for f in geojson_obj.get('features', []):
            if isinstance(f, dict) and f.get('geometry'):
                geoms.append(f['geometry'])
        if not geoms:
            raise ValueError("FeatureCollection has no geometries")
        if len(geoms) == 1:
            return parse_geojson_to_multipolygon(geoms[0])
        polys: List = []
        for g in geoms:
            t = g.get('type')
            if t == 'Polygon':
                polys.append(g['coordinates'])
            elif t == 'MultiPolygon':
                polys.extend(g['coordinates'])
        if not polys:
            raise ValueError("Only Polygon/MultiPolygon geometries supported for aggregation")
        return json.dumps({"type": "MultiPolygon", "coordinates": polys})
    if geojson_obj.get('type') == 'Feature':
        geom = geojson_obj.get('geometry')
        if not geom:
            raise ValueError("Feature missing geometry")
        return parse_geojson_to_multipolygon(geom)
    gtype = geojson_obj.get('type')
    if gtype == 'Polygon':
        return json.dumps({"type": "MultiPolygon", "coordinates": [geojson_obj['coordinates']]})
    if gtype == 'MultiPolygon':
        return json.dumps(geojson_obj)
    raise ValueError(f"Unsupported geometry type: {gtype}")

def coerce_to_multipolygon(geom: dict) -> str:
    """Coerce a Polygon or MultiPolygon geometry object to a MultiPolygon JSON string.
    Raises on unsupported geometry types. Does not handle Feature/FeatureCollection."""
    if not isinstance(geom, dict):
        raise ValueError("Geometry must be object")
    gtype = geom.get('type')
    if gtype == 'Polygon':
        return json.dumps({"type": "MultiPolygon", "coordinates": [geom['coordinates']]})
    if gtype == 'MultiPolygon':
        return json.dumps(geom)
    raise ValueError(f"Unsupported geometry type for admin/building ingestion: {gtype}")

def merge_flood_map_by_dn(geojson_obj: dict) -> List[dict]:
    """Parse GeoJSON FeatureCollection and group polygons by DN value.
    Returns list of dicts with {dn: int, multipolygon: dict, metadata: dict}.
    Similar to upload_flood_map.py logic but returns structured data."""
    from collections import defaultdict
    
    if not isinstance(geojson_obj, dict):
        raise ValueError("GeoJSON must be an object")
    
    if geojson_obj.get('type') != 'FeatureCollection':
        raise ValueError("Expected FeatureCollection for flood map upload")
    
    features = geojson_obj.get('features', [])
    if not features:
        raise ValueError("FeatureCollection has no features")
    
    # Group by DN value
    dn_groups = defaultdict(list)
    
    for feature in features:
        if feature.get('type') != 'Feature':
            continue
        
        properties = feature.get('properties', {})
        dn = properties.get('DN')
        
        if dn is None:
            continue  # Skip features without DN
        
        geom = feature.get('geometry')
        if not geom:
            continue
        
        gtype = geom.get('type')
        
        # Collect polygon coordinates
        if gtype == 'Polygon':
            dn_groups[dn].append(geom['coordinates'])
        elif gtype == 'MultiPolygon':
            # Unpack MultiPolygon into individual polygon coordinates
            dn_groups[dn].extend(geom['coordinates'])
    
    if not dn_groups:
        raise ValueError("No valid features with DN property found")
    
    # Create merged results
    results = []
    for dn, polygon_coords in dn_groups.items():
        multipolygon = {
            "type": "MultiPolygon",
            "coordinates": polygon_coords
        }
        metadata = {
            "polygon_count": len(polygon_coords)
        }
        results.append({
            "dn": int(dn),
            "multipolygon": multipolygon,
            "metadata": metadata
        })
    
    return results
