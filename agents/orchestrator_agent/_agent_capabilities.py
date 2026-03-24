# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Agent Capabilities Documentation for Orchestrator Planner

This module contains detailed documentation about each sub-agent's capabilities,
constraints, inputs/outputs, and usage guidelines. This is injected into the
orchestrator's planning prompt to help it make better decisions.

Design Principles:
- Describe capabilities abstractly, not tied to specific examples
- State constraints as general rules
- Allow planner flexibility to reason about novel cases
"""

# Import from central location
from agents.core.constants import AGENT_NAMES


# =============================================================================
# DETAILED AGENT CAPABILITIES DOCUMENTATION
# =============================================================================

AGENT_CAPABILITIES_DOC = """
## AGENT CAPABILITIES & CONSTRAINTS

---

### postgis_agent

**Role:** Query the PostGIS disaster database containing historical disaster records, building damage assessments, and flood maps.

**Data Sources:**
- Disaster metadata (type, date, location, AOI/extent geometry)
- Building damage assessments (damage percentage, damage status, building geometry)
- Flood maps (flood extent polygons, flood severity classes)

**Inputs:**
- Natural language task describing what to retrieve or analyze
- Optional: GeoJSON file paths for spatial filtering or joins

**Outputs:**
- GeoJSON layers (vector features with attributes) with statistical summary of the results including count by damage level, percentage by damage level, and other relevant metrics
- Tabular data (aggregated statistics, counts)


**Constraints:**
- **Single-purpose per call:** Each step should accomplish ONE focused objective (e.g., retrieve AOI OR query damage Or Flood Map, not all or two)
- **Database-only:** Cannot access external data sources; use map_search_agent for OSM features
- **Read-only:** Can only query, not modify data
- **Flood extent vs. Flood Extent AOI:** Flood extent refers to the actual flood polygons, while Flood Extent AOI is a single GeoJSON defining the area of interest.
- **Building damage labeling:** Buildings are not labeled by name or categories or other identifiers like neighborhood; each building has a damage assessment.
- **AOI of each disaster:** The AOI represents the outer boundary of the disaster in single polygon with no sub-region level boundaires.

**Capabilities:**
- Retrieve disaster AOI/extent geometry
- Query buildings by damage level, location, or disaster
- Retrieve flood extent maps
- Spatial operations: intersection, containment, proximity, clustering
- Aggregate statistics: counts, percentages, groupings
- Spatial joins with external GeoJSON (POIs, boundaries from other agents)
- **Create buffer geometries** from points, lines, or polygons (use `create_buffer` tool)

**Tools:**
- `execute_query`: Standard PostGIS SELECT queries
- `execute_query_with_geojson`: Queries with external GeoJSON spatial joins
- `create_buffer`: Create distance-based buffer polygons around input geometries

---

### map_search_agent

**Role:** Extract geographic features from OpenStreetMap for areas worldwide.

**Data Sources:**
- OpenStreetMap via Overpass API and Nominatim geocoding

**Inputs (one of):**
- Place name string (should include full hierarchy: city, state, country)
- GeoJSON file path defining area of interest
- Bounding box coordinates

**Outputs:**
- GeoJSON files containing extracted features with OSM attributes

**Constraints:**
- **Single feature type per call:** Each step extracts ONE category from the table below. Categories cannot be combined in a single call.
- **Single AOI per call:** Each call operates on ONE area of interest. Multiple locations require separate calls.
- **Requires location context:** Place names should be unambiguous with full geographic hierarchy
- **OSM data only:** No disaster-specific data; use postgis_agent for damage/flood data
- **AOI file requirement:** The AOI file MUST contain a single Polygon, the tool will fail if the input AOI contains multiple polygons features.
- **Static/current data only:** OSM features represent current state without historical timestamps. For date-specific analysis (e.g., "forest cover on March 15, 2020"), use stac_agent to fetch satellite imagery from that date instead.

**Available Extractions:**
| Category | Examples |
|----------|----------|
| Administrative boundaries | City, county, neighborhood polygons |
| Points of Interest | Hospitals, schools, fire stations, shelters, utilities |
| Transportation | Roads by class, bridges, railways |
| Buildings | By type (residential, commercial, industrial, public) |
| Water features | Rivers, streams, canals, lakes |
| Infrastructure | Power lines, communication towers, water supply |
| Natural features | Vegetation, terrain, coastal features |
| Land use zones | Residential, commercial, industrial, agricultural areas |
| Forward geocoding | Find coordinates of any named place, POI, landmark, facility, or address |
| Reverse geocoding | Convert coordinates to addresses; supports raw coords or GeoJSON features (uses centroid for polygons and lines) |
| Named linear features | Get full geometry of specific roads, rivers, railways by name (not for POIs) |
| Search inside an AOI | Find features within a specified area of interest (AOI) like neighborhoods, roads, POIs |
---

### stac_agent

**Role:** Retrieve satellite imagery and geospatial raster datasets from Microsoft Planetary Computer STAC catalog.

**Data Sources:**
- 113+ satellite and geospatial collections (Sentinel-2, Landsat, MODIS, etc.)
- Population data (WorldPop)
- Land cover maps (ESA WorldCover, ESRI LULC)
- Elevation data (Copernicus DEM)

**Inputs:**
- GeoJSON file path defining area of interest (required)
- Analysis purpose / context
- Temporal parameters (date ranges, disaster dates)

**Outputs:**
- **Fetch mode:** STAC items JSON files (metadata + asset URLs for raster_ops_agent)
- **Show mode:** Mosaic layer for direct visualization
- **Population queries:** Returns per-feature statistics when AOI contains multiple polygons
- **Land cover:** Classified raster with legend

**Constraints:**
- **Requires AOI input:** Must receive GeoJSON from previous step or user upload
- **Temporal awareness:** Satellite imagery requires date context; static datasets (DEM, population) do not
- **AOI file requirement:** For satellite imagery queries, the AOI file MUST contain a single Polygon. Population queries support multiple polygons.

**Key Capabilities:**
| Capability | Description |
|------------|-------------|
| Multi-collection queries | Fetch multiple data types in one call (imagery + LULC + population) |
| Dual-date support | Pre/post disaster imagery in single fetch |
| Coverage validation | Automatic fallback to alternative collections if coverage insufficient |
| Population statistics | Per-feature stats for multi-polygon AOIs (neighborhoods, districts, etc.) |
| Cloud filtering | Automatic for optical imagery |

**Population Data - Multi-Polygon Support:**
When the AOI GeoJSON contains multiple features (e.g., neighborhoods, districts), population queries return:
- `total_population`: Aggregate for entire AOI
- `per_feature_stats`: Population for each feature with `feature_id`, `total_population`, `mean_density`, `area_km2`
- `summary`: Min/max/mean population across features

**Note:** For large AOIs (>100 features), per-feature stats are truncated to top/bottom 50 by population. For full per-feature breakdown, use a simplified AOI with named regions (neighborhoods, districts) rather than raw flood extent or buildings polygons.

This enables queries like "population of each neighborhood" or "which district has highest population" without additional processing.

---

### raster_ops_agent

**Role:** Perform raster analysis and computation on satellite imagery via Python code generation.

**Data Sources:**
- STAC items from stac_agent (satellite imagery)
- Raster files (GeoTIFF, COG)
- Vector files for masking/zoning (GeoJSON)

**Inputs:**
- STAC items JSON file path(s) from stac_agent
- Analysis objective in natural language
- Optional: Vector boundaries for clipping or zonal analysis

**Outputs:**
- Raster results (Cloud-Optimized GeoTIFF)
- Vector results (GeoJSON polygons from classification)
- Computed statistics

**Constraints:**
- **Requires imagery input:** Cannot fetch satellite data directly; depends on stac_agent output
- **Single analysis focus:** Each step should target one analytical objective
- **Computational:** For derived products, not raw data retrieval

**Capabilities:**
| Category | Examples |
|----------|----------|
| Spectral indices | NDVI, NDWI, NBR, NDBI, EVI |
| Change detection | Pre/post comparison, dNBR, temporal differencing |
| Classification | Thresholding, clustering, severity levels |
| Temporal analysis | Time series composites, trend detection, recovery curves |
| Zonal statistics | Aggregate values per polygon region |
| Masking | Cloud masking, water masking, AOI clipping |

---

## PLANNING PRINCIPLES

### 1. Single Responsibility
Each step should have ONE clear objective. If a task requires multiple data retrievals or analyses, split into separate steps.

### 2. Data Flow Dependencies
- stac_agent and raster_ops_agent require AOI geometry → ensure prior step provides it
- raster_ops_agent requires STAC items → ensure stac_agent runs first
- postgis_agent spatial joins require external GeoJSON → ensure map_search_agent provides it
- **Spatial geometry creation** (buffers, distance-based AOIs) → postgis_agent must create geometry BEFORE other agents can use it

### 2a. Spatial Geometry Operations
When queries involve spatial constraints like radius, distance, or buffers:
- **postgis_agent** is the ONLY agent that can create derived geometries (ST_Buffer, ST_ConvexHull, etc.)
- map_search_agent can only EXTRACT existing features within a provided AOI—it cannot create buffers or distance-based geometries
- If user specifies "within X km/miles of [point/location]", first use postgis_agent to create the buffer polygon, then pass that polygon to downstream agents

### 3. Agent Selection by Data Source
| Data Need | Agent |
|-----------|-------|
| Disaster records, damage, floods | postgis_agent |
| Derived spatial geometries (buffers, distance-based AOIs) | postgis_agent |
| OSM features (POIs, roads, boundaries, infrastructure) | map_search_agent |
| Satellite imagery, population, elevation, land cover | stac_agent |
| Derived raster products (indices, classifications) | raster_ops_agent |

### 3a. Temporal vs Static Data Sources
| Data Source | Agent | Temporal Capability |
|-------------|-------|---------------------|
| Disaster database | postgis_agent | Has event dates; query by disaster_date |
| OpenStreetMap | map_search_agent | **Static/current only**; no historical snapshots |
| Satellite imagery | stac_agent → raster_ops_agent | **Date-specific**; can analyze any date with available imagery |

**Key routing rules:**
- Queries about features "as of [specific date]" or "on [date]" for natural/physical features → use stac_agent + raster_ops_agent to derive from imagery
- Queries about current infrastructure, POIs, boundaries → map_search_agent
- Queries about disaster impacts with known event dates → postgis_agent (if disaster in database)

### 4. Avoid Redundant Steps
- If stac_agent returns statistics directly (e.g., population totals), do not add raster_ops_agent to recompute them
- If postgis_agent can filter and return results in one query, do not split unnecessarily
- Reuse artifacts from previous steps when available

### 5. Context Completeness
Each step's task description should include:
- What data/analysis is needed
- Relevant geographic context (full place names)
- Relevant temporal context (disaster dates if applicable)
- How the output will be used (for downstream step awareness)

### 6. Land Use vs Land Cover

| Aspect | OSM Land Use (map_search_agent) | Satellite LULC (stac_agent) |
|--------|--------------------------------|----------------------------|
| Data Type | Vector polygons | Raster pixels (10m) |
| Source | OpenStreetMap (crowdsourced) | ESA/ESRI satellite imagery |
| Categories | Zoning: residential, commercial, industrial, agricultural, recreation | Physical cover: built-up, cropland, trees, water, grassland |
| Use Case | Human activity zones, zoning analysis | Physical land cover classification |

Routing guidance:
- Zoning-based queries (residential, commercial, industrial) → map_search_agent
- Physical land cover queries (vegetation, built-up area percentages) → stac_agent

### 7. Buildings Data Source Selection

| Source | Agent | Use Case |
|--------|-------|----------|
| Database (BDA) | postgis_agent | Building damage assessments with damage levels, pre-analyzed for disasters |
| OpenStreetMap | map_search_agent | Raw building footprints when BDA not available in database |

Routing guidance:
- Queries about damage levels, damage statistics → postgis_agent (has analyzed BDA)
- Queries needing building footprints for areas without BDA (e.g., intersect buildings with flood extent) → map_search_agent
"""


def get_agent_capabilities_doc() -> str:
    """Return the agent capabilities documentation string."""
    return AGENT_CAPABILITIES_DOC
