# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
STAC search functionality for Microsoft Planetary Computer.
"""

from typing import Dict, Any, Optional, List, Tuple
from shapely.geometry import shape, box
from shapely.ops import unary_union

from agents.core.logging import get_logger

_logger = get_logger("stac.search")

# Threshold for switching from unary_union to bounding box
_LARGE_FEATURE_THRESHOLD = 100


def _safe_union_geometries(geometries: List[Any]) -> Any:
    """
    Safely union geometries, handling topology errors gracefully.
    
    For large feature sets, uses bounding box instead of expensive unary_union.
    For smaller sets, repairs invalid geometries before union.
    """
    if not geometries:
        return None
    
    # For large feature sets, use bounding box (fast, always works)
    if len(geometries) > _LARGE_FEATURE_THRESHOLD:
        _logger.info(f"Large geometry set ({len(geometries)} features) - using bounding box")
        all_bounds = [g.bounds for g in geometries]
        minx = min(b[0] for b in all_bounds)
        miny = min(b[1] for b in all_bounds)
        maxx = max(b[2] for b in all_bounds)
        maxy = max(b[3] for b in all_bounds)
        return box(minx, miny, maxx, maxy)
    
    # For smaller sets, try union with fallback
    try:
        return unary_union(geometries)
    except Exception as e:
        _logger.warning(f"unary_union failed ({e}), attempting geometry repair")
        try:
            repaired = [g.buffer(0) if not g.is_valid else g for g in geometries]
            return unary_union(repaired)
        except Exception as e2:
            _logger.warning(f"Repaired union failed ({e2}), falling back to bounding box")
            all_bounds = [g.bounds for g in geometries]
            minx = min(b[0] for b in all_bounds)
            miny = min(b[1] for b in all_bounds)
            maxx = max(b[2] for b in all_bounds)
            maxy = max(b[3] for b in all_bounds)
            return box(minx, miny, maxx, maxy)


def validate_bbox_coverage(items, bbox: List[float], min_coverage_percent: float = 80.0) -> Tuple[bool, float]:
    """
    Check if STAC items adequately cover the bounding box.
    
    Args:
        items: List of STAC items
        bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
        min_coverage_percent: Minimum required coverage percentage
        
    Returns:
        Tuple of (is_valid, coverage_percent)
    """
    if not items:
        return False, 0.0
        
    aoi = box(*bbox)
    aoi_area = aoi.area
    
    # Union all item footprints using optimized unary_union
    geometries = []
    for item in items:
        try:
            geometries.append(shape(item.geometry))
        except Exception as e:
            print(f"Warning: Could not process item geometry: {str(e)}")
            continue
    
    if not geometries:
        return False, 0.0
    
    union_geom = _safe_union_geometries(geometries)
    
    try:
        intersection = aoi.intersection(union_geom)
        coverage_percent = (intersection.area / aoi_area) * 100
        return coverage_percent >= min_coverage_percent, coverage_percent
    except Exception as e:
        print(f"Warning: Coverage calculation failed: {str(e)}")
        return False, 0.0


def _raster_bands2string(bands):
    """Convert raster bands metadata to string representation."""
    if "raster:bands" in bands:
        bands = bands["raster:bands"]
        return ", ".join(f"{k} = {v}" for band in bands for k, v in band.items() if k not in ["name", "description"])
    return ""


def search_single_collection(
    catalog,
    collection_id: str,
    bbox: List[float],
    date1: Optional[str],
    date2: Optional[str],
    limit: int,
    query_filters: Dict[str, Any],
    min_coverage_percent: float
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Search a single collection for items within bbox and date range(s).
    
    Args:
        catalog: pystac_client.Client instance
        collection_id: STAC collection ID
        bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
        date1: Primary date range (ISO format, e.g., "2024-01-01/2024-01-31")
        date2: Optional secondary date range for comparison
        limit: Maximum items per date range
        query_filters: Additional STAC query filters
        min_coverage_percent: Minimum coverage threshold
        
    Returns:
        Tuple of (date1_result, date2_result) where each is:
        {
            "collection_id": str,
            "items": List[dict],
            "item_count": int,
            "coverage_percent": float,
            "bands": List[str]
        }
        or None if search failed
    """
    print(f"\n--- Searching {collection_id} ---")
    
    def _do_search(datetime_str: Optional[str]) -> Optional[Dict]:
        """Execute single STAC search."""
        try:
            search_params = {
                "collections": [collection_id],
                "bbox": bbox,
                "limit": limit
            }
            
            if datetime_str:
                search_params["datetime"] = datetime_str
            
            if query_filters:
                search_params["query"] = query_filters
            
            search = catalog.search(**search_params)
            items = list(search.items())
            
            if not items:
                print(f"No items found for {collection_id} with datetime={datetime_str}")
                return None
            
            # Validate coverage
            is_valid, coverage = validate_bbox_coverage(items, bbox, min_coverage_percent)
            
            if not is_valid:
                print(f"Coverage too low for {collection_id}: {coverage:.1f}% < {min_coverage_percent}%")
                return None
            
            # Extract band info from first item
            bands = []
            if items and hasattr(items[0], 'assets'):
                bands = list(items[0].assets.keys())
            
            # Convert to dicts for serialization - use to_dict() to preserve full STAC structure
            items_as_dicts = []
            for item in items:
                item_dict = item.to_dict()
                # Normalize datetime if missing
                if item_dict.get("properties", {}).get("datetime") is None:
                    item_dict["properties"]["datetime"] = item_dict["properties"].get("start_datetime")
                items_as_dicts.append(item_dict)
            
            print(f"Found {len(items)} items for {collection_id}, coverage: {coverage:.1f}%")
            
            return {
                "collection_id": collection_id,
                "items": items_as_dicts,
                "item_count": len(items),
                "coverage_percent": coverage,
                "bands": bands
            }
            
        except Exception as e:
            print(f"Search failed for {collection_id}: {str(e)}")
            return None
    
    # Search date1
    date1_result = _do_search(date1)
    
    # Search date2 if provided and date1 succeeded
    date2_result = None
    if date1_result and date2:
        date2_result = _do_search(date2)
    
    return date1_result, date2_result


def analyze_temporal_coverage(items: List[dict], bbox: List[float]) -> dict:
    """
    Analyze temporal distribution and spatial coverage of STAC items.
    Groups by date and calculates coverage for each time period.
    
    Returns:
        {
            "date_groups": {
                "2023-06-15": {"count": 3, "coverage_percent": 95.2},
                ...
            },
            "temporal_gaps": ["2023-09-15/2023-09-30"],
            "total_dates": 45,
            "coverage_summary": "Good coverage for 42/45 dates"
        }
    """
    from collections import defaultdict
    
    # Group items by date (YYYY-MM-DD)
    date_groups = defaultdict(list)
    
    for item in items:
        # Extract date from item
        dt_str = item.get("properties", {}).get("datetime")
        if dt_str:
            date_only = dt_str.split("T")[0]  # "2023-06-15"
            date_groups[date_only].append(item)
    
    # Calculate coverage for each date
    coverage_by_date = {}
    aoi = box(*bbox)
    aoi_area = aoi.area
    
    for date, items_for_date in sorted(date_groups.items()):
        # Union geometries for this date
        geometries = []
        for item in items_for_date:
            try:
                geometries.append(shape(item["geometry"]))
            except:
                continue
        
        if geometries:
            union_geom = _safe_union_geometries(geometries)
            intersection = aoi.intersection(union_geom)
            coverage_pct = (intersection.area / aoi_area) * 100
        else:
            coverage_pct = 0.0
        
        coverage_by_date[date] = {
            "count": len(items_for_date),
            "coverage_percent": round(coverage_pct, 1)
        }
    
    # Identify temporal gaps (dates with < 50% coverage)
    gaps = [date for date, info in coverage_by_date.items() 
            if info["coverage_percent"] < 50]
    
    # Generate summary
    good_coverage = sum(1 for info in coverage_by_date.values() 
                       if info["coverage_percent"] >= 80)
    total_dates = len(coverage_by_date)
    
    return {
        "date_groups": coverage_by_date,
        "temporal_gaps": gaps,
        "total_dates": total_dates,
        "good_coverage_dates": good_coverage,
        "coverage_summary": f"{good_coverage}/{total_dates} dates with >80% coverage"
    }
