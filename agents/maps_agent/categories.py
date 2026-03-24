# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
OSM feature category enums for filtering map features.
"""

from enum import Enum


class RoadCategory(str, Enum):
    """Road categories for filtering OSM highway features."""
    MAJOR = "major"  # motorway, trunk, primary, secondary
    MINOR = "minor"  # tertiary, residential, unclassified, living_street
    PATHS = "paths"  # footway, cycleway, path, pedestrian, track
    SERVICE = "service"  # service, driveway
    ALL = "all"  # All road types


class BuildingCategory(str, Enum):
    """Building categories for filtering OSM building features."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    PUBLIC = "public"
    RELIGIOUS = "religious"
    EMERGENCY = "emergency"
    ALL = "all"


class WaterwayCategory(str, Enum):
    """Waterway categories for filtering OSM waterway features."""
    RIVERS = "rivers"
    STREAMS = "streams"
    ALL = "all"


class POICategory(str, Enum):
    """POI categories for disaster assessment."""
    EMERGENCY = "emergency"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    SHELTER = "shelter"
    FOOD = "food"
    TRANSPORTATION = "transportation"
    UTILITIES = "utilities"


class LanduseCategory(str, Enum):
    """Land use categories for filtering OSM landuse features."""
    URBAN = "urban"
    AGRICULTURE = "agriculture"
    NATURAL = "natural"
    RECREATION = "recreation"
    ALL = "all"


class NaturalCategory(str, Enum):
    """Natural feature categories."""
    WATER = "water"
    VEGETATION = "vegetation"
    TERRAIN = "terrain"
    COASTAL = "coastal"


class InfrastructureCategory(str, Enum):
    """Infrastructure categories."""
    POWER = "power"
    COMMUNICATION = "communication"
    WATER_SUPPLY = "water_supply"
    SEWAGE = "sewage"
    TRANSPORT = "transport"
