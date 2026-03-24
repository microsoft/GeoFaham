# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
STAC Collection Data - Single Source of Truth

This module provides:
1. COLLECTION_INDEX - Compact metadata for system prompt (~50 tokens per collection)
2. COLLECTION_DETAILS - Full metadata retrieved on-demand via tool
3. Helper functions for collection lookup
"""

import json
import os
from typing import Dict, List, Any, Optional

# ============================================================================
# COLLECTION INDEX (Compact - for system prompt)
# Format: {id: {name, category, resolution, use_cases, coverage, is_static, has_cloud_filter, status}}
# ============================================================================

COLLECTION_INDEX = {
    # === OPTICAL IMAGERY ===
    "sentinel-2-l2a": {
        "name": "Sentinel-2 L2A",
        "category": "optical",
        "resolution": "10m",
        "use_cases": ["true color", "NDVI", "damage assessment", "change detection", "flood mapping"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": True,
        "status": "excellent",
        "temporal_start": "2015-06"
    },
    "landsat-c2-l2": {
        "name": "Landsat Collection 2 L2",
        "category": "optical",
        "resolution": "30m",
        "use_cases": ["historical analysis", "thermal", "long-term change", "fire temperature"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": True,
        "status": "excellent",
        "temporal_start": "1982"
    },
    "naip": {
        "name": "NAIP Aerial Imagery",
        "category": "aerial",
        "resolution": "0.6m",
        "use_cases": ["building damage", "infrastructure", "high-resolution mapping"],
        "coverage": "usa_only",
        "is_static": False,
        "has_cloud_filter": True,
        "status": "good",
        "temporal_start": "2009"
    },
    "hls2-l30": {
        "name": "Harmonized Landsat-Sentinel L30",
        "category": "optical",
        "resolution": "30m",
        "use_cases": ["consistent time-series", "multi-sensor fusion"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": True,
        "status": "excellent",
        "temporal_start": "2013"
    },
    "hls2-s30": {
        "name": "Harmonized Landsat-Sentinel S30",
        "category": "optical",
        "resolution": "30m",
        "use_cases": ["consistent time-series", "multi-sensor fusion"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": True,
        "status": "excellent",
        "temporal_start": "2015"
    },

    # === SAR/RADAR (Weather-Independent) ===
    "sentinel-1-grd": {
        "name": "Sentinel-1 SAR GRD",
        "category": "sar",
        "resolution": "10m",
        "use_cases": ["flood detection", "water extent", "all-weather monitoring", "oil spill"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2014"
    },
    "sentinel-1-rtc": {
        "name": "Sentinel-1 SAR RTC",
        "category": "sar",
        "resolution": "10m",
        "use_cases": ["landslide detection", "terrain deformation", "mountainous areas"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2014"
    },

    # === FIRE DETECTION ===
    "modis-14A1-061": {
        "name": "MODIS Active Fire Daily",
        "category": "fire",
        "resolution": "1km",
        "use_cases": ["real-time fire detection", "active fire tracking", "thermal anomaly"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-64A1-061": {
        "name": "MODIS Burned Area Monthly",
        "category": "fire",
        "resolution": "500m",
        "use_cases": ["burn scar mapping", "fire extent", "post-fire assessment"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },

    # === VEGETATION ===
    "modis-13Q1-061": {
        "name": "MODIS Vegetation Indices 16-Day",
        "category": "vegetation",
        "resolution": "250m",
        "use_cases": ["vegetation health", "NDVI/EVI", "crop monitoring", "drought"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-13A1-061": {
        "name": "MODIS Vegetation Indices 500m",
        "category": "vegetation",
        "resolution": "500m",
        "use_cases": ["vegetation health", "NDVI/EVI", "regional monitoring"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },

    # === TEMPERATURE/THERMAL ===
    "modis-11A1-061": {
        "name": "MODIS Land Surface Temp Daily",
        "category": "thermal",
        "resolution": "1km",
        "use_cases": ["heat stress", "urban heat island", "fire risk", "thermal anomaly"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-11A2-061": {
        "name": "MODIS Land Surface Temp 8-Day",
        "category": "thermal",
        "resolution": "1km",
        "use_cases": ["temperature trends", "thermal analysis"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },

    # === ELEVATION/DEM (STATIC) ===
    "cop-dem-glo-30": {
        "name": "Copernicus DEM 30m",
        "category": "elevation",
        "resolution": "30m",
        "use_cases": ["terrain analysis", "flood modeling", "slope", "watershed"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": None
    },
    "cop-dem-glo-90": {
        "name": "Copernicus DEM 90m",
        "category": "elevation",
        "resolution": "90m",
        "use_cases": ["regional terrain", "large-area analysis"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": None
    },
    "nasadem": {
        "name": "NASA DEM",
        "category": "elevation",
        "resolution": "30m",
        "use_cases": ["elevation", "slope", "aspect", "hydrological modeling"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": None
    },
    "3dep-seamless": {
        "name": "USGS 3DEP",
        "category": "elevation",
        "resolution": "10m",
        "use_cases": ["high-res terrain", "USA elevation"],
        "coverage": "usa_only",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "medium",
        "temporal_start": None
    },
    "alos-dem": {
        "name": "ALOS World 3D DEM",
        "category": "elevation",
        "resolution": "30m",
        "use_cases": ["elevation", "terrain analysis"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "good",
        "temporal_start": None
    },

    # === LAND USE/LAND COVER ===
    "esa-worldcover": {
        "name": "ESA WorldCover",
        "category": "landcover",
        "resolution": "10m",
        "use_cases": ["land cover classification", "urban areas", "forests", "cropland"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": None
    },
    "io-lulc-annual-v02": {
        "name": "Esri Land Cover Annual",
        "category": "landcover",
        "resolution": "10m",
        "use_cases": ["annual land cover", "change detection", "urban growth"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2017"
    },
    "io-lulc-9-class": {
        "name": "Esri Land Cover 9-Class",
        "category": "landcover",
        "resolution": "10m",
        "use_cases": ["simplified land cover"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "good",
        "temporal_start": "2017"
    },
    "usda-cdl": {
        "name": "USDA Cropland Data Layer",
        "category": "landcover",
        "resolution": "30m",
        "use_cases": ["crop classification", "agriculture mapping"],
        "coverage": "usa_only",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2008"
    },

    # === POPULATION ===
    "worldpop-population": {
        "name": "WorldPop Population",
        "category": "population",
        "resolution": "100m",
        "use_cases": ["population density", "exposure analysis", "demographics"],
        "coverage": "global",
        "is_static": True,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": None
    },

    # === WATER ===
    "jrc-gsw": {
        "name": "JRC Global Surface Water",
        "category": "water",
        "resolution": "30m",
        "use_cases": ["water occurrence", "seasonality", "water change"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "1984"
    },

    # === OCEAN/MARINE ===
    "noaa-cdr-sea-surface-temperature-optimum-interpolation": {
        "name": "NOAA Sea Surface Temperature",
        "category": "ocean",
        "resolution": "25km",
        "use_cases": ["sea surface temperature", "marine analysis"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "1981"
    },

    # === WEATHER/PRECIPITATION ===
    "noaa-mrms-qpe-1h-pass2": {
        "name": "NOAA MRMS Precipitation 1h",
        "category": "weather",
        "resolution": "1km",
        "use_cases": ["precipitation", "rainfall", "flood risk"],
        "coverage": "usa_only",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "good",
        "temporal_start": "2020"
    },
    "noaa-mrms-qpe-24h-pass2": {
        "name": "NOAA MRMS Precipitation 24h",
        "category": "weather",
        "resolution": "1km",
        "use_cases": ["daily precipitation", "accumulated rainfall"],
        "coverage": "usa_only",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "good",
        "temporal_start": "2020"
    },
    "goes-cmi": {
        "name": "GOES Cloud & Moisture Imagery",
        "category": "weather",
        "resolution": "2km",
        "use_cases": ["real-time weather", "cloud tracking", "storm monitoring"],
        "coverage": "americas",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "good",
        "temporal_start": "2017"
    },

    # === ADDITIONAL MODIS PRODUCTS ===
    "modis-09A1-061": {
        "name": "MODIS Surface Reflectance 8-Day",
        "category": "optical",
        "resolution": "500m",
        "use_cases": ["surface reflectance", "atmospheric corrected imagery"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-09Q1-061": {
        "name": "MODIS Surface Reflectance 250m",
        "category": "optical",
        "resolution": "250m",
        "use_cases": ["high-res surface reflectance"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-43A4-061": {
        "name": "MODIS BRDF-Corrected Reflectance",
        "category": "optical",
        "resolution": "500m",
        "use_cases": ["nadir BRDF", "consistent reflectance"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-10A1-061": {
        "name": "MODIS Snow Cover Daily",
        "category": "snow",
        "resolution": "500m",
        "use_cases": ["snow cover", "snow extent"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
    "modis-10A2-061": {
        "name": "MODIS Snow Cover 8-Day",
        "category": "snow",
        "resolution": "500m",
        "use_cases": ["snow extent", "maximum snow cover"],
        "coverage": "global",
        "is_static": False,
        "has_cloud_filter": False,
        "status": "excellent",
        "temporal_start": "2000"
    },
}

# ============================================================================
# COLLECTION DETAILS (Full metadata - retrieved on-demand)
# ============================================================================

COLLECTION_DETAILS = {
    "sentinel-2-l2a": {
        "description": "High-resolution multispectral optical imagery with 10m resolution. Best for true color visualization, vegetation analysis (NDVI), and disaster damage assessment. Global coverage with 5-day revisit time.",
        "bands": {
            "B02": {"name": "Blue", "wavelength": "490nm", "resolution": "10m"},
            "B03": {"name": "Green", "wavelength": "560nm", "resolution": "10m"},
            "B04": {"name": "Red", "wavelength": "665nm", "resolution": "10m"},
            "B08": {"name": "NIR", "wavelength": "842nm", "resolution": "10m"},
            "B11": {"name": "SWIR1", "wavelength": "1610nm", "resolution": "20m"},
            "B12": {"name": "SWIR2", "wavelength": "2190nm", "resolution": "20m"},
            "SCL": {"name": "Scene Classification", "resolution": "20m"},
            "visual": {"name": "True Color RGB", "resolution": "10m"}
        },
        "visualization": {
            "true_color": ["B04", "B03", "B02"],
            "false_color": ["B08", "B04", "B03"],
            "swir": ["B12", "B11", "B04"],
            "ndvi": "expression: (B08-B04)/(B08+B04)"
        },
        "query_template": {
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 50
        },
        "temporal": {"start": "2015-06-27", "end": "ongoing", "revisit_days": 5},
        "limitations": "Cloud cover can obscure imagery; requires clear weather"
    },

    "landsat-c2-l2": {
        "description": "Longest continuous Earth observation record (1982-present) with 30m resolution. Includes thermal infrared bands. Excellent for historical analysis and thermal anomaly detection.",
        "bands": {
            "red": {"name": "Red", "resolution": "30m"},
            "green": {"name": "Green", "resolution": "30m"},
            "blue": {"name": "Blue", "resolution": "30m"},
            "nir08": {"name": "NIR", "resolution": "30m"},
            "swir16": {"name": "SWIR1", "resolution": "30m"},
            "swir22": {"name": "SWIR2", "resolution": "30m"},
            "lwir11": {"name": "Thermal", "resolution": "100m"}
        },
        "visualization": {
            "true_color": ["red", "green", "blue"],
            "thermal": ["lwir11"]
        },
        "query_template": {
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 50
        },
        "temporal": {"start": "1982-08-22", "end": "ongoing", "revisit_days": 16},
        "limitations": "16-day revisit; coarser resolution than Sentinel-2"
    },

    "sentinel-1-grd": {
        "description": "All-weather C-band SAR imagery that penetrates clouds and darkness. Essential for flood detection when optical imagery unavailable. Dual-polarization (VV, VH).",
        "bands": {
            "VV": {"name": "VV Polarization", "resolution": "10m"},
            "VH": {"name": "VH Polarization", "resolution": "10m"}
        },
        "visualization": {
            "grayscale": ["VV"],
            "composite": ["VV", "VH", "VV"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2014-10-03", "end": "ongoing", "revisit_days": 6},
        "limitations": "Requires SAR expertise; no color information"
    },

    "sentinel-1-rtc": {
        "description": "Terrain-corrected SAR data optimized for mountainous regions. Eliminates geometric distortions from terrain. Ideal for landslide detection.",
        "bands": {
            "VV": {"name": "VV Polarization", "resolution": "10m"},
            "VH": {"name": "VH Polarization", "resolution": "10m"}
        },
        "visualization": {
            "grayscale": ["VV"],
            "composite": ["VV", "VH", "VV"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2014-10-03", "end": "ongoing", "revisit_days": 6},
        "limitations": "Limited advantage in flat terrain"
    },

    "naip": {
        "description": "Ultra-high resolution (0.6m) aerial imagery for USA. 4-band (RGB + NIR). Updated every 2-3 years per state.",
        "bands": {
            "red": {"name": "Red", "resolution": "0.6m"},
            "green": {"name": "Green", "resolution": "0.6m"},
            "blue": {"name": "Blue", "resolution": "0.6m"},
            "nir": {"name": "NIR", "resolution": "0.6m"},
            "image": {"name": "RGBIR composite", "resolution": "0.6m"}
        },
        "visualization": {
            "true_color": ["red", "green", "blue"],
            "cir": ["nir", "red", "green"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2009", "end": "ongoing", "update_frequency": "2-3 years"},
        "limitations": "USA only; not real-time"
    },

    "modis-14A1-061": {
        "description": "Real-time daily fire detection using thermal infrared. Detects active fires within ~3 hours of observation. Confidence levels help filter false positives.",
        "bands": {
            "FireMask": {"name": "Fire Mask", "resolution": "1km"},
            "MaxFRP": {"name": "Max Fire Radiative Power", "resolution": "1km"},
            "QA": {"name": "Quality Assessment", "resolution": "1km"}
        },
        "visualization": {
            "fire_mask": ["FireMask"]
        },
        "query_template": {
            "query": {},
            "limit": 100
        },
        "temporal": {"start": "2000-11-01", "end": "ongoing", "update_frequency": "daily"},
        "limitations": "1km resolution misses small fires; cloud cover affects detection"
    },

    "modis-64A1-061": {
        "description": "Monthly burned area mapping with 500m resolution. Maps burn scars and fire progression. Best for post-fire assessment.",
        "bands": {
            "Burn_Date": {"name": "Burn Date", "resolution": "500m"},
            "Burn_Date_Uncertainty": {"name": "Uncertainty", "resolution": "500m"},
            "QA": {"name": "Quality", "resolution": "500m"}
        },
        "visualization": {
            "burn_date": ["Burn_Date"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2000-11-01", "end": "ongoing", "update_frequency": "monthly"},
        "limitations": "Monthly resolution; not for real-time monitoring"
    },

    "modis-13Q1-061": {
        "description": "250m NDVI and EVI vegetation indices updated every 16 days. Monitors vegetation health, crop conditions, and forest stress.",
        "bands": {
            "250m_16_days_NDVI": {"name": "NDVI", "resolution": "250m"},
            "250m_16_days_EVI": {"name": "EVI", "resolution": "250m"},
            "250m_16_days_VI_Quality": {"name": "Quality", "resolution": "250m"}
        },
        "visualization": {
            "ndvi": ["250m_16_days_NDVI"],
            "evi": ["250m_16_days_EVI"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2000-02-18", "end": "ongoing", "update_frequency": "16 days"},
        "limitations": "16-day composite; not real-time"
    },

    "modis-11A1-061": {
        "description": "Daily land surface temperature at 1km. Day and night measurements. For heat stress monitoring and urban heat island analysis.",
        "bands": {
            "LST_Day_1km": {"name": "Day LST", "resolution": "1km"},
            "LST_Night_1km": {"name": "Night LST", "resolution": "1km"},
            "QC_Day": {"name": "Day Quality", "resolution": "1km"},
            "QC_Night": {"name": "Night Quality", "resolution": "1km"}
        },
        "visualization": {
            "day_temp": ["LST_Day_1km"],
            "night_temp": ["LST_Night_1km"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2000-03-05", "end": "ongoing", "update_frequency": "daily"},
        "limitations": "Cloud cover affects measurements"
    },

    "cop-dem-glo-30": {
        "description": "Global 30m digital elevation model. Best available global DEM for topographic analysis, flood modeling, and terrain visualization. STATIC - no datetime needed.",
        "bands": {
            "data": {"name": "Elevation", "resolution": "30m", "unit": "meters"}
        },
        "visualization": {
            "elevation": ["data"],
            "hillshade": "computed"
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"static": True},
        "limitations": "Static data; no temporal changes detected"
    },

    "cop-dem-glo-90": {
        "description": "Global 90m digital elevation model. For regional/continental scale terrain analysis. STATIC - no datetime needed.",
        "bands": {
            "data": {"name": "Elevation", "resolution": "90m", "unit": "meters"}
        },
        "visualization": {
            "elevation": ["data"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"static": True},
        "limitations": "Static; coarser than 30m version"
    },

    "nasadem": {
        "description": "30m global DEM with slope and aspect derivatives. Based on reprocessed SRTM. STATIC - no datetime needed.",
        "bands": {
            "elevation": {"name": "Elevation", "resolution": "30m"},
            "slope": {"name": "Slope", "resolution": "30m"},
            "aspect": {"name": "Aspect", "resolution": "30m"}
        },
        "visualization": {
            "elevation": ["elevation"],
            "slope": ["slope"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"static": True},
        "limitations": "Static; limited to ±60° latitude"
    },

    "esa-worldcover": {
        "description": "10m global land cover classification. Classes: Water, Trees, Flooded vegetation, Crops, Built area, Bare ground, Snow/ice, Clouds, Rangeland.",
        "bands": {
            "map": {"name": "Land Cover Class", "resolution": "10m"}
        },
        "classes": {
            0: "No Data", 10: "Tree cover", 20: "Shrubland", 30: "Grassland",
            40: "Cropland", 50: "Built-up", 60: "Bare/sparse", 70: "Snow/ice",
            80: "Water", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss/lichen"
        },
        "visualization": {
            "land_cover": ["map"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"static": True, "reference_year": "2020-2021"},
        "limitations": "Static snapshot; annual updates available"
    },

    "io-lulc-annual-v02": {
        "description": "10m annual land cover from Esri. Classes: Tree cover, Shrubland, Grassland, Cropland, Built-up, Bare vegetation, Snow/ice, Water, Wetland, Mangroves, Moss/lichen.",
        "bands": {
            "data": {"name": "Land Cover Class", "resolution": "10m"}
        },
        "classes": {
            1: "Water", 2: "Trees", 4: "Flooded vegetation", 5: "Crops",
            7: "Built area", 8: "Bare ground", 9: "Snow/ice", 10: "Clouds", 11: "Rangeland"
        },
        "visualization": {
            "land_cover": ["data"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "2017", "end": "ongoing", "update_frequency": "annual"},
        "limitations": "Annual updates; may lag current conditions"
    },

    "worldpop-population": {
        "description": "100m population density estimates. Static 2020 data. Returns population count and statistics for AOI. Supports per-feature stats for multi-polygon inputs.",
        "bands": {
            "population": {"name": "Population Count", "resolution": "100m"}
        },
        "visualization": {
            "population": ["population"]
        },
        "query_template": {
            "query": {},
            "limit": 1
        },
        "temporal": {"static": True, "reference_year": "2020"},
        "limitations": "Static 2020 data; estimates not census"
    },

    "jrc-gsw": {
        "description": "30m global surface water mapping. Includes water occurrence, seasonality, and change. 1984-present.",
        "bands": {
            "occurrence": {"name": "Water Occurrence", "resolution": "30m"},
            "change": {"name": "Change Intensity", "resolution": "30m"},
            "seasonality": {"name": "Seasonality", "resolution": "30m"},
            "recurrence": {"name": "Recurrence", "resolution": "30m"},
            "transitions": {"name": "Transitions", "resolution": "30m"},
            "extent": {"name": "Maximum Extent", "resolution": "30m"}
        },
        "visualization": {
            "occurrence": ["occurrence"],
            "seasonality": ["seasonality"]
        },
        "query_template": {
            "query": {},
            "limit": 50
        },
        "temporal": {"start": "1984", "end": "ongoing"},
        "limitations": "Historical composite; not real-time"
    },

    "hls2-l30": {
        "description": "30m harmonized Landsat-Sentinel data (Landsat-derived). Combines sensors for consistent time-series analysis.",
        "bands": {
            "B02": {"name": "Blue", "resolution": "30m"},
            "B03": {"name": "Green", "resolution": "30m"},
            "B04": {"name": "Red", "resolution": "30m"},
            "B05": {"name": "NIR", "resolution": "30m"},
            "B06": {"name": "SWIR1", "resolution": "30m"},
            "B07": {"name": "SWIR2", "resolution": "30m"}
        },
        "visualization": {
            "true_color": ["B04", "B03", "B02"]
        },
        "query_template": {
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 50
        },
        "temporal": {"start": "2013-04-11", "end": "ongoing"},
        "limitations": "30m resolution (not native Sentinel-2 10m)"
    },

    "hls2-s30": {
        "description": "30m harmonized Landsat-Sentinel data (Sentinel-2-derived). Resampled to 30m for sensor fusion.",
        "bands": {
            "B02": {"name": "Blue", "resolution": "30m"},
            "B03": {"name": "Green", "resolution": "30m"},
            "B04": {"name": "Red", "resolution": "30m"},
            "B8A": {"name": "NIR", "resolution": "30m"},
            "B11": {"name": "SWIR1", "resolution": "30m"},
            "B12": {"name": "SWIR2", "resolution": "30m"}
        },
        "visualization": {
            "true_color": ["B04", "B03", "B02"]
        },
        "query_template": {
            "query": {"eo:cloud_cover": {"lt": 20}},
            "limit": 50
        },
        "temporal": {"start": "2015-06-23", "end": "ongoing"},
        "limitations": "Resampled from 10m"
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_collection_index() -> Dict[str, Any]:
    """Return the compact collection index for system prompt."""
    return COLLECTION_INDEX


def get_collection_details(collection_ids: List[str]) -> Dict[str, Any]:
    """
    Retrieve full details for specified collections.
    
    Args:
        collection_ids: List of collection IDs to retrieve details for
        
    Returns:
        Dictionary with collection details, or error info for unknown collections
    """
    result = {}
    unknown = []
    
    for cid in collection_ids:
        if cid in COLLECTION_DETAILS:
            result[cid] = {
                **COLLECTION_INDEX.get(cid, {}),
                **COLLECTION_DETAILS[cid]
            }
        elif cid in COLLECTION_INDEX:
            # Has index but no detailed info - return index with note
            result[cid] = {
                **COLLECTION_INDEX[cid],
                "note": "Detailed band information not available. Use standard STAC query."
            }
        else:
            unknown.append(cid)
    
    if unknown:
        result["_unknown_collections"] = unknown
        
    return result


def get_collections_by_category(category: str) -> List[str]:
    """Get all collection IDs in a category."""
    return [cid for cid, info in COLLECTION_INDEX.items() if info.get("category") == category]


def get_static_collections() -> List[str]:
    """Get all static collection IDs (no datetime filter needed)."""
    return [cid for cid, info in COLLECTION_INDEX.items() if info.get("is_static")]


def get_collections_with_cloud_filter() -> List[str]:
    """Get all collection IDs that support cloud filtering."""
    return [cid for cid, info in COLLECTION_INDEX.items() if info.get("has_cloud_filter")]


def format_collection_index_for_prompt() -> str:
    """Format the collection index as compact text for the system prompt."""
    lines = []
    
    # Group by category
    categories = {}
    for cid, info in COLLECTION_INDEX.items():
        cat = info.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((cid, info))
    
    # Format each category
    for cat in sorted(categories.keys()):
        lines.append(f"\n**{cat.upper()}:**")
        for cid, info in sorted(categories[cat], key=lambda x: x[0]):
            use_cases = ", ".join(info.get("use_cases", [])[:3])
            static = " [STATIC]" if info.get("is_static") else ""
            coverage = f" [{info.get('coverage')}]" if info.get("coverage") != "global" else ""
            lines.append(f"- `{cid}`: {info['resolution']}, {use_cases}{static}{coverage}")
    
    return "\n".join(lines)


# Category mappings for quick lookup
CATEGORY_MAPPING = {
    "optical": ["sentinel-2-l2a", "landsat-c2-l2", "naip", "hls2-l30", "hls2-s30", "modis-09A1-061", "modis-09Q1-061", "modis-43A4-061"],
    "sar": ["sentinel-1-grd", "sentinel-1-rtc"],
    "fire": ["modis-14A1-061", "modis-64A1-061"],
    "vegetation": ["modis-13Q1-061", "modis-13A1-061"],
    "thermal": ["modis-11A1-061", "modis-11A2-061"],
    "elevation": ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless", "alos-dem"],
    "landcover": ["esa-worldcover", "io-lulc-annual-v02", "io-lulc-9-class", "usda-cdl"],
    "population": ["worldpop-population"],
    "water": ["jrc-gsw"],
    "snow": ["modis-10A1-061", "modis-10A2-061"],
    "ocean": ["noaa-cdr-sea-surface-temperature-optimum-interpolation"],
    "weather": ["noaa-mrms-qpe-1h-pass2", "noaa-mrms-qpe-24h-pass2", "goes-cmi"],
}

# Recommended fallbacks for common scenarios
FALLBACK_RECOMMENDATIONS = {
    "general_imagery": ["sentinel-2-l2a", "landsat-c2-l2"],
    "usa_high_res": ["naip", "sentinel-2-l2a"],
    "flood_detection": ["sentinel-1-grd", "sentinel-2-l2a"],
    "wildfire_active": ["modis-14A1-061", "sentinel-2-l2a"],
    "wildfire_damage": ["sentinel-2-l2a", "modis-64A1-061"],
    "vegetation_health": ["sentinel-2-l2a", "modis-13Q1-061"],
    "elevation": ["cop-dem-glo-30", "nasadem"],
    "land_cover": ["esa-worldcover", "io-lulc-annual-v02"],
    "all_weather": ["sentinel-1-grd", "sentinel-1-rtc"],
}
