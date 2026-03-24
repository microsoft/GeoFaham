# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
STAC Agent - Satellite imagery retrieval from Microsoft Planetary Computer
"""

from agents.stac_agent.assistant import create_stac_agent
from agents.stac_agent.tools import execute_stac_search, get_collection_details
from agents.stac_agent.collection_data import (
    COLLECTION_INDEX,
    COLLECTION_DETAILS,
    CATEGORY_MAPPING,
    FALLBACK_RECOMMENDATIONS,
    get_static_collections,
    get_collections_with_cloud_filter,
)

# Backward compatibility aliases
COLLECTION_PROFILES = COLLECTION_INDEX
COLLECTION_CATEGORIES = CATEGORY_MAPPING
STATIC_COLLECTIONS = get_static_collections()
OPTICAL_COLLECTIONS = get_collections_with_cloud_filter()

__all__ = [
    "create_stac_agent",
    "execute_stac_search",
    "get_collection_details",
    "COLLECTION_INDEX",
    "COLLECTION_DETAILS",
    "CATEGORY_MAPPING",
    "FALLBACK_RECOMMENDATIONS",
    # Backward compatibility
    "COLLECTION_PROFILES",
    "COLLECTION_CATEGORIES",
    "STATIC_COLLECTIONS",
    "OPTICAL_COLLECTIONS"
]
