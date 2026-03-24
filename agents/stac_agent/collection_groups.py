# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Collection Groups - Handle multiple collection groups with priority-based fallback
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass


@dataclass
class CollectionGroup:
    """Represents a group of collections with priority"""
    name: str
    collection_ids: List[str]
    priority: str  # "high" or "low"
    query: Dict[str, Any] = None  # Optional group-specific filters
    daterange1: Optional[str] = None  # Group-specific temporal range
    daterange2: Optional[str] = None  # Optional second temporal range
    visualization: Optional[Dict[str, Dict[str, Any]]] = None  # Per-collection visualization config
    
    def __post_init__(self):
        if self.query is None:
            self.query = {}
        if self.visualization is None:
            self.visualization = {}
    
    @property
    def is_required(self) -> bool:
        """Check if this group is required (high priority)"""
        return self.priority.lower() == "high"


def parse_collections_input(collections: Dict[str, Any]) -> List[CollectionGroup]:
    """
    Parse collections input into CollectionGroup objects.
    
    Expects grouped dict format:
    {
        "flood_detection": {
            "collection_ids": ["sentinel-1-grd"],
            "priority": "high"
        },
        "crop_analysis": {
            "collection_ids": ["io-lulc-9-class"],
            "priority": "high"
        }
    }
    
    Args:
        collections: Dict of collection groups
        
    Returns:
        List of CollectionGroup objects
        
    Raises:
        ValueError: If input format is invalid
    """
    if isinstance(collections, dict):
        # Grouped format
        groups = []
        for group_name, group_config in collections.items():
            if not isinstance(group_config, dict):
                raise ValueError(
                    f"Group '{group_name}' must be a dict with 'collection_ids' and 'priority'"
                )
            
            collection_ids = group_config.get("collection_ids", [])
            priority = group_config.get("priority", "high")
            query = group_config.get("query", {})
            daterange1 = group_config.get("daterange1")
            daterange2 = group_config.get("daterange2")
            visualization = group_config.get("visualization", {})
            
            if not collection_ids:
                raise ValueError(f"Group '{group_name}' must have at least one collection_id")
            
            if priority not in ["high", "low"]:
                raise ValueError(f"Group '{group_name}' priority must be 'high' or 'low', got '{priority}'")
            
            groups.append(CollectionGroup(
                name=group_name,
                collection_ids=collection_ids,
                priority=priority,
                query=query,
                daterange1=daterange1,
                daterange2=daterange2,
                visualization=visualization
            ))
        
        return groups
    
    else:
        raise ValueError(
            f"Collections must be a dict with grouped format, got {type(collections).__name__}"
        )


def validate_required_groups(group_results: Dict[str, Optional[str]]) -> tuple[bool, List[str]]:
    """
    Validate that all required (high priority) groups have successful results.
    
    Args:
        group_results: Dict mapping group name to successful collection_id (or None if failed)
        
    Returns:
        Tuple of (all_required_succeeded, failed_group_names)
    """
    failed_groups = [
        group_name for group_name, result in group_results.items() 
        if result is None
    ]
    
    return len(failed_groups) == 0, failed_groups


def format_group_summary(group_results: Dict[str, Dict[str, Any]]) -> str:
    """
    Format a human-readable summary of collection group results.
    
    Args:
        group_results: Dict with group results including collection, items, coverage
        
    Returns:
        Formatted summary string
    """
    lines = []
    for group_name, result in group_results.items():
        if result.get("collection_id"):
            collection = result["collection_id"]
            item_count = result.get("item_count", 0)
            coverage = result.get("coverage_percent", 0)
            lines.append(f"  • {group_name}: {collection} ({item_count} items, {coverage:.1f}% coverage)")
        else:
            lines.append(f"  • {group_name}: FAILED")
    
    return "\n".join(lines)
