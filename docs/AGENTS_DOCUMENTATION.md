# GeoFaham Multi-Agent System Documentation

This document provides comprehensive documentation of all agents in the GeoFaham geospatial AI system, their capabilities, tools, inputs/outputs, and how they work together.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Orchestrator Agent](#orchestrator-agent)
4. [Vector Agent (PostGIS)](#vector-agent-postgis)
5. [Maps Agent (OSM)](#maps-agent-osm)
6. [STAC Agent](#stac-agent)
7. [Raster Ops Agent](#raster-ops-agent)
8. [Core Modules](#core-modules)
9. [Response Store](#response-store)
10. [Data Flow](#data-flow)
11. [Configuration](#configuration)

---

## System Overview

GeoFaham is a **multi-agent geospatial AI platform** built on [AutoGen](https://github.com/microsoft/autogen). It enables natural language queries about disaster damage, satellite imagery, and geospatial data.

### Agent Registry

| Agent Name | Internal Name | Purpose |
|------------|---------------|---------|
| Orchestrator | `GeoFahamGroupChat` | Coordinates agents, plans and tracks progress |
| Vector Agent | `vector_agent` | Queries PostGIS disaster database |
| Maps Agent | `osm_map_agent` | Extracts OpenStreetMap features |
| STAC Agent | `stac_agent` | Fetches satellite imagery from Planetary Computer |
| Raster Ops Agent | `raster_ops_agent` | Performs raster analysis via Python code generation |

> **Note**: For detailed agent capabilities used by the orchestrator, see `agents/orchestrator_agent/_agent_capabilities.py`.

### Standard Response Format

All agents return a `GeoFahamToolResponse` object (defined in `agents/core/types.py`):

```python
class GeoFahamToolResponse(BaseModel):
    response_id: str           # Unique response identifier (e.g., "vec_a1b2c3d4")
    source: str                # Agent that produced the response
    type: Literal["layer", "data", "error", "layer_with_data"]
    data_type: Literal["raster", "vector", "stac_items", "timeline", "json", "msg", "raster_intermediate", "raster_mix"]
    data: List[Dict[str, Any]] # Result data (for tabular responses)
    summary: str               # Human-readable summary
    error_message: Optional[str]  # Error details if type="error"
    artifact: Optional[SavedArtifact]  # Saved file metadata
    metadata: Optional[Dict[str, Any]]  # Additional metadata
```

### Saved Artifact Format

```python
class SavedArtifact(BaseModel):
    path: str                  # File path
    content_type: str          # MIME type (default: "application/geo+json")
    format: str                # "geojson", "tif", "json"
    bytes: Optional[int]       # File size
    features_count: Optional[int]  # Number of features
    stats: Optional[Dict]      # Statistics about the data
    property_keys: Optional[Dict[str, Dict[str, Any]]]  # Property schema by geometry type
    geom_types: Optional[List[str]]  # Geometry types present
    metadata: Optional[Dict]   # Additional metadata
```

> **See**: [TOOL_RESPONSE_SCHEMAS.md](TOOL_RESPONSE_SCHEMAS.md) for complete response schema documentation.

---

## Architecture

### Directory Structure

```
agents/
├── __init__.py              # Package exports (get_team, create_* functions)
├── team.py                  # Team creation (GeoFahamGroupChat)
│
├── core/                    # Foundation layer (no internal dependencies)
│   ├── __init__.py
│   ├── config.py            # Centralized configuration (AgentsConfig)
│   ├── constants.py         # Agent names, geometry types, API versions
│   ├── exceptions.py        # Custom exceptions
│   ├── types.py             # Pydantic models (GeoFahamToolResponse, SavedArtifact)
│   ├── logging.py           # Logging setup
│   └── response_store.py    # Response persistence
│
├── shared/                  # Shared utilities
│   ├── __init__.py
│   ├── serialization.py     # Value serialization (datetime, Decimal)
│   ├── geojson.py           # GeoJSON processing, artifact saving
│   └── analysis.py          # Analysis utilities
│
├── base/                    # Agent factory layer
│   ├── __init__.py
│   ├── agent.py             # Base agent patterns
│   └── client.py            # ModelClientFactory (Azure OpenAI)
│
├── vector_agent/            # PostGIS database queries
│   ├── __init__.py
│   ├── assistant.py         # create_vector_agent()
│   ├── tools.py             # VectorQueryExecutor
│   └── _prompts.py          # System prompt
│
├── maps_agent/              # OpenStreetMap extraction
│   ├── __init__.py
│   ├── assistant.py         # create_map_search_agent()
│   ├── tools.py             # Re-exports from modules
│   ├── feature_tools.py     # get_roads, get_buildings, etc.
│   ├── geocoding_tools.py   # get_address_coordinates, get_admin_boundary
│   ├── categories.py        # Enums (RoadCategory, BuildingCategory)
│   ├── utils.py             # OSM utilities
│   └── _prompts.py          # System prompt
│
├── stac_agent/              # Satellite imagery (Planetary Computer)
│   ├── __init__.py
│   ├── assistant.py         # create_stac_agent()
│   ├── tools.py             # execute_stac_search, get_collection_details
│   ├── search.py            # STAC search logic
│   ├── mosaic.py            # MosaicJSON creation
│   ├── band_metadata.py     # Band rescaling, visualization params
│   ├── collection_data.py   # Collection metadata index
│   ├── collection_groups.py # Collection grouping logic
│   ├── population_tool.py   # WorldPop population data
│   ├── lulc_tool.py         # Land use/land cover
│   └── _prompts.py          # System prompt
│
├── raster_ops_agent/        # Raster analysis via code generation
│   ├── __init__.py
│   ├── assistant.py         # create_raster_ops_agent()
│   ├── tools.py             # execute_custom_raster_code
│   ├── executor.py          # RasterCodeExecutor (sandboxed Python)
│   ├── io_utils.py          # COG writing, statistics
│   ├── result_handlers.py   # Handle raster/vector/temporal results
│   └── _prompts.py          # System prompt with code examples
│
└── orchestrator_agent/      # Multi-agent coordination
    ├── __init__.py
    ├── group_chat.py        # GeoFahamGroupChat (custom orchestrator)
    ├── orchestrator.py      # Orchestration logic
    ├── _prompts.py          # Planning and progress prompts
    └── _agent_capabilities.py  # Agent documentation for planner
```

### Layer Dependencies

```
                    ┌─────────────────────────────────┐
                    │         Agent Modules           │
                    │ (vector, maps, stac, raster)    │
                    └───────────────┬─────────────────┘
                                    │ imports
                    ┌───────────────▼─────────────────┐
                    │            base/                │
                    │   (client.py, agent.py)         │
                    └───────────────┬─────────────────┘
                                    │ imports
                    ┌───────────────▼─────────────────┐
                    │           shared/               │
                    │ (serialization, geojson, etc.)  │
                    └───────────────┬─────────────────┘
                                    │ imports
                    ┌───────────────▼─────────────────┐
                    │            core/                │
                    │ (config, types, constants, etc.)│
                    └─────────────────────────────────┘
```

---

## Orchestrator Agent

**Location**: `agents/orchestrator_agent/`

### Purpose

The `GeoFahamGroupChat` manages the multi-agent workflow using a ledger-based orchestration approach. It:

1. Analyzes user queries and extracts **facts**
2. Creates an execution **plan** with numbered steps
3. Selects the appropriate agent for each step
4. Tracks **progress** and updates the plan as needed
5. Generates a **final answer** when complete

### Architecture

```
User Query
    ↓
GeoFahamGroupChat
    ├─ Facts Extraction (What do we know?)
    ├─ Plan Generation (What steps needed?)
    ↓
Agent Selection (Based on plan step)
    ↓
Agent Execution (vector, maps, stac, raster)
    ↓
Progress Update (What was accomplished?)
    ↓
Next Step or Final Answer
```

### Key Components

| File | Purpose |
|------|---------|
| `group_chat.py` | `GeoFahamGroupChat` class - custom `SelectorGroupChat` |
| `orchestrator.py` | Orchestration logic and state management |
| `_prompts.py` | Planning, progress, and final answer prompts |
| `_agent_capabilities.py` | Detailed agent documentation for the planner |

### Agent Selection

The orchestrator uses two models:
- **Planner Model** (`ORCHESTRATOR_PLANNER`): For planning and agent selection (GPT-5.1)
- **Progress Model** (`ORCHESTRATOR_PROGRESS`): For tracking progress (can be GPT-4o)

```python
# From agents/core/constants.py
AGENT_NAMES = {
    "VECTOR_AGENT": "vector_agent",
    "MAPS_AGENT": "osm_map_agent",
    "STAC_AGENT": "stac_agent",
    "RASTER_AGENT": "raster_ops_agent",
    "ORCHESTRATOR_PLANNER": "orchestrator_planner",
    "ORCHESTRATOR_PROGRESS": "orchestrator_progress",
}
```

### Key Prompts

| Prompt | Purpose |
|--------|---------|
| `ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT` | Extract facts from context |
| `ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT` | Generate execution plan |
| `ORCHESTRATOR_PROGRESS_LEDGER_PROMPT` | Track progress after each step |
| `ORCHESTRATOR_FINAL_ANSWER_PROMPT` | Generate final answer |

---

## Vector Agent (PostGIS)

**Location**: `agents/vector_agent/`

### Purpose

Queries a PostGIS database containing disaster data including:
- Building damage assessments
- Flood extent maps
- Disaster metadata and boundaries

### Architecture

The Vector Agent uses a single `AssistantAgent` with tool reflection for error recovery:

```
User Request
    ↓
AssistantAgent (with reflect_on_tool_use=True)
    ↓
Tool Execution (execute_query or execute_query_with_geojson)
    ↓
Error? → Retry with corrections (up to max_tool_iterations=4)
    ↓
Return GeoFahamToolResponse
```

### Files

| File | Purpose |
|------|---------|
| `assistant.py` | `create_vector_agent()` factory function |
| `tools.py` | `VectorQueryExecutor` class with all query tools |
| `_prompts.py` | System prompt with SQL examples |

### Tools

#### `execute_query`

Execute a PostGIS SELECT query without external GeoJSON.

```python
async def execute_query(
    query: str,                    # SQL SELECT statement
    return_layer: bool,            # Return as GeoJSON layer for map
    results_description: str,      # Human-readable description
    return_aggregated_data: bool = False  # Include tabular data with layer
) -> str  # JSON GeoFahamToolResponse
```

#### `execute_query_with_geojson`

Execute query with external GeoJSON for spatial joins. Uses response IDs to automatically resolve file paths.

```python
async def execute_query_with_geojson(
    query: str,                    # SQL with {{GEOJSON_*_CTE}} placeholders
    return_layer: bool,            # Return as GeoJSON layer
    results_description: str,      # Description of results
    response_ids: List[str],       # IDs from previous agent responses
    return_aggregated_data: bool = False
) -> str  # JSON GeoFahamToolResponse
```

#### `get_available_responses`

Access responses from other agents in the session (shared tool).

### GeoJSON Placeholder System

When external GeoJSON is needed for spatial joins, SQL uses placeholders:

| Placeholder | Creates CTE |
|-------------|-------------|
| `{{GEOJSON_POINTS_CTE}}` | `points_from_geojson` |
| `{{GEOJSON_LINES_CTE}}` | `lines_from_geojson` |
| `{{GEOJSON_POLYGONS_CTE}}` | `polygons_from_geojson` |
| `{{GEOJSON_GEOMTYPE_CTES}}` | All applicable geometry CTEs |

**Example SQL**:
```sql
WITH {{GEOJSON_POLYGONS_CTE}}
SELECT b.*, p.name as area_name
FROM building_damage_assessment b
JOIN polygons_from_geojson p ON ST_Within(b.geom, p.geom)
WHERE b.disaster_id = 16;
```

### Database Schema

Key tables in the disaster database:

| Table | Description |
|-------|-------------|
| `disasters` | Disaster metadata (id, name, type, date, location, geom) |
| `building_damage_assessment` | Building assessments (damage_pct, damaged, geom) |
| `flood_maps` | Flood extent polygons (flood_class, geom) |

### Capabilities

| Capability | Description |
|------------|-------------|
| Disaster lookup | Query by type, date, location, disaster_id |
| Building damage | Filter by damage_pct, damage status |
| Flood analysis | Flood extent, flooded buildings, flood classes |
| Spatial predicates | ST_Within, ST_Intersects, ST_DWithin, ST_Buffer |
| Spatial clustering | DBSCAN clustering for hotspot detection |
| Spatial joins | Join with external GeoJSON via response_ids |
| Aggregations | GROUP BY with statistics, ORDER BY for relevance |

---

## Maps Agent (OSM)

**Location**: `agents/maps_agent/`

### Purpose

Extracts geographic features from OpenStreetMap using the `osmnx` library. Provides infrastructure data not available in the disaster database.

**Constraint**: One feature type per call (e.g., separate calls for hospitals vs. schools).

### Files

| File | Purpose |
|------|---------|
| `assistant.py` | `create_map_search_agent()` factory function |
| `tools.py` | Re-exports all tools from modules |
| `feature_tools.py` | OSM feature extraction (roads, buildings, etc.) |
| `geocoding_tools.py` | Geocoding and boundary tools |
| `categories.py` | Category enums (RoadCategory, BuildingCategory, etc.) |
| `utils.py` | OSM utilities and tag definitions |
| `_prompts.py` | System prompt |

### Tools Summary

| Tool | Purpose |
|------|---------|
| `get_roads` | Road network extraction |
| `get_buildings` | Building footprints |
| `get_waterways` | Rivers, streams, canals |
| `get_bridges` | Bridge structures |
| `get_pois` | Points of interest (emergency, healthcare, etc.) |
| `get_admin_boundary` | Administrative boundary polygons |
| `get_neighborhoods` | Neighborhood boundaries |
| `get_landuse` | Land use areas |
| `get_natural_features` | Natural features (water, vegetation, terrain) |
| `get_infrastructure` | Infrastructure (power, communication, water supply) |
| `get_features_by_tags` | Custom OSM tag queries |
| `get_address_coordinates` | Geocode address to point |
| `get_place_bounding_box` | Get bounding box for location |
| `search_feature_by_name` | Search named linear features |

### Category Enums

**RoadCategory**: `MAJOR`, `MINOR`, `PATHS`, `SERVICE`, `ALL`

**BuildingCategory**: `RESIDENTIAL`, `COMMERCIAL`, `INDUSTRIAL`, `PUBLIC`, `RELIGIOUS`, `EMERGENCY`, `ALL`

**POICategory**: `EMERGENCY`, `EDUCATION`, `HEALTHCARE`, `SHELTER`, `FOOD`, `TRANSPORTATION`, `UTILITIES`

**LanduseCategory**: `URBAN`, `AGRICULTURE`, `NATURAL`, `RECREATION`, `ALL`

**NaturalCategory**: `WATER`, `VEGETATION`, `TERRAIN`, `COASTAL`

**InfrastructureCategory**: `POWER`, `COMMUNICATION`, `WATER_SUPPLY`, `SEWAGE`, `TRANSPORT`

### Input Types

All feature tools accept one of three input types:
1. `geojson_path`: Path to GeoJSON file defining AOI
2. `place_name`: Name for geocoding (e.g., "Lahaina, Hawaii, USA")
3. `bbox`: Bounding box as `[north, south, east, west]`

### Example Usage

```python
# Get hospitals in a disaster area
result = await get_pois(
    place_name="Lahaina, Hawaii, USA",
    poi_category=POICategory.HEALTHCARE
)

# Get roads from a GeoJSON boundary
result = await get_roads(
    geojson_path="/path/to/aoi.geojson",
    road_category=RoadCategory.MAJOR
)

# Geocode an address
result = await get_address_coordinates(
    address=["Lahaina, Maui, Hawaii", "Lahaina, Hawaii, USA"]  # Fallback variants
)
```

---

## STAC Agent

**Location**: `agents/stac_agent/`

### Purpose

Fetches satellite imagery and geospatial datasets from **Microsoft Planetary Computer STAC API**.

### Files

| File | Purpose |
|------|---------|
| `assistant.py` | `create_stac_agent()` factory function |
| `tools.py` | `execute_stac_search`, `get_collection_details` |
| `search.py` | STAC search logic, coverage validation |
| `mosaic.py` | MosaicJSON creation for visualization |
| `band_metadata.py` | Band rescaling, visualization parameters |
| `collection_data.py` | Collection metadata index (113+ collections) |
| `collection_groups.py` | Collection grouping and parsing |
| `population_tool.py` | WorldPop population data |
| `lulc_tool.py` | Land use/land cover classification |
| `_prompts.py` | System prompt |

### Tools

#### `get_collection_details`

Get metadata about STAC collections.

```python
def get_collection_details(
    collection_ids: List[str]  # e.g., ["sentinel-2-l2a", "landsat-c2-l2"]
) -> str  # JSON with collection metadata
```

#### `execute_stac_search`

Search and retrieve satellite imagery.

```python
async def execute_stac_search(
    collections: Dict[str, Any],    # Grouped collections with priorities
    geojson_path: str,              # AOI GeoJSON file path
    limit: int = 50,                # Max items per search
    mode: str = "fetch",            # "fetch" or "show"
    min_coverage_percent: float = 80.0,  # Coverage threshold
    reasoning: Optional[Dict[str, str]] = None,
    visualization_hints: Optional[Dict[str, Any]] = None
) -> str  # JSON GeoFahamToolResponse
```

### Collection Groups Format

```python
{
    "pre_fire_imagery": {
        "collection_ids": ["sentinel-2-l2a", "landsat-c2-l2"],
        "priority": "high",
        "query": {"eo:cloud_cover": {"lt": 20}},
        "daterange1": "2023-08-01/2023-08-07"
    },
    "post_fire_imagery": {
        "collection_ids": ["sentinel-2-l2a"],
        "query": {"eo:cloud_cover": {"lt": 30}},
        "daterange1": "2023-08-09/2023-08-20"
    }
}
```

### Modes

| Mode | Purpose | Output |
|------|---------|--------|
| `fetch` | Analysis - returns STAC items JSON for raster_ops_agent | STAC items file paths |
| `show` | Visualization - creates mosaic tiles | Mosaic URL + tile endpoints |

### Coverage Validation

- Validates scene footprints cover AOI bounding box above threshold
- Falls back to next collection in priority order if coverage fails
- Ensures temporal consistency across collection groups

### Output Format

**Fetch Mode** returns STAC items file paths:
```json
{
  "type": "data",
  "data_type": "stac_items",
  "data": [
    {
      "type": "stac_items",
      "collection_group": "pre_fire_imagery",
      "items_json_path": "/runtime/artifacts/query_jsons/stac_results_abc123_pre_fire_imagery_date1.geojson",
      "search_params": {
        "collection": "sentinel-2-l2a",
        "scenes_found": 5,
        "coverage_percent": 95.2,
        "bbox": [-156.7, 20.8, -156.6, 20.9],
        "bands": ["B02", "B03", "B04", "B08", "B11", "B12"]
      }
    }
  ]
}
```

---

## Raster Ops Agent

**Location**: `agents/raster_ops_agent/`

### Purpose

Performs raster analysis via Python code generation:
- Spectral indices (NDVI, NBR, NDWI)
- Change detection (dNBR, dNDVI)
- Classification and thresholding
- Zonal statistics
- Temporal analysis

### Files

| File | Purpose |
|------|---------|
| `assistant.py` | `create_raster_ops_agent()` factory function |
| `tools.py` | `execute_custom_raster_code` tool |
| `executor.py` | `RasterCodeExecutor` - sandboxed Python execution |
| `io_utils.py` | COG writing, statistics computation |
| `result_handlers.py` | Handle raster/vector/temporal results |
| `_prompts.py` | System prompt with code examples |

### Architecture

```
LLM generates Python code
    ↓
RasterCodeExecutor.validate_code() - Check for forbidden operations
    ↓
RasterCodeExecutor.execute() - Run in sandboxed asteval environment
    ↓
Result handlers - Write COG/GeoJSON, compute statistics
    ↓
Return GeoFahamToolResponse
```

### Tool

#### `execute_custom_raster_code`

```python
async def execute_custom_raster_code(
    code: str,                  # Python code (must assign to 'result' variable)
    result_explanation: str,    # Human-readable description
    return_layer: bool,         # Write result as COG/GeoJSON for map
    expected_result_type: str   # "raster", "vector", "statistics", "mix"
) -> str  # JSON GeoFahamToolResponse
```

### Available Functions in Executor

| Function | Purpose |
|----------|---------|
| `load_stac_items(path, bbox, bands, resolution)` | Load STAC items as xarray DataArray |
| `load_raster_file(path)` | Load GeoTIFF file |
| `load_vector_file(path)` | Load GeoJSON/vector file |
| `clip_to_aoi(da, aoi_gdf)` | Clip raster to AOI polygon |

### Available Libraries

```python
# In executor sandbox
import xarray as xr       # as 'xr'
import numpy as np        # as 'np'
import geopandas as gpd   # as 'gpd'
import shapely            # geometry operations
import scipy              # scientific computing
import skimage            # image processing
from datetime import datetime, timedelta
```

### Code Patterns

**NDVI Calculation:**
```python
da, epsg = load_stac_items("/path/to/stac.json", bbox, ["B04", "B08"], 10)
red = da.sel(band="B04").mean(dim="time")
nir = da.sel(band="B08").mean(dim="time")
ndvi = (nir - red) / (nir + red)
result = ndvi
```

**Burn Severity (dNBR):**
```python
pre, _ = load_stac_items(pre_path, bbox, ["B08", "B12"], 10)
post, _ = load_stac_items(post_path, bbox, ["B08", "B12"], 10)

pre_nbr = (pre.sel(band="B08") - pre.sel(band="B12")) / (pre.sel(band="B08") + pre.sel(band="B12"))
post_nbr = (post.sel(band="B08") - post.sel(band="B12")) / (post.sel(band="B08") + post.sel(band="B12"))

dnbr = pre_nbr.mean(dim="time") - post_nbr.mean(dim="time")
result = dnbr
```

**Classification:**
```python
# Classify burn severity
severity = xr.where(dnbr < 0.1, 0,  # Unburned
           xr.where(dnbr < 0.27, 1,  # Low
           xr.where(dnbr < 0.44, 2,  # Moderate-low
           xr.where(dnbr < 0.66, 3,  # Moderate-high
           4))))  # High
result = severity.astype(np.int8)
```

### Output Types

| Type | Description | Output |
|------|-------------|--------|
| `raster` | Single xarray DataArray | COG file + statistics |
| `vector` | GeoDataFrame | GeoJSON file |
| `temporal_sequence` | Dict of DataArrays by date | Multiple COG files |
| `mix` | Dict with multiple layers | Multiple files |

---

## Core Modules

**Location**: `agents/core/`

### config.py

Centralized configuration with environment variable support and dependency injection.

```python
from agents.core.config import get_config

config = get_config()
print(config.azure_openai.endpoint)
print(config.database.host)
print(config.paths.export_dir)
print(config.get_agent_model("VECTOR_AGENT"))
```

### types.py

Pydantic models for type safety:
- `GeoFahamToolResponse` - Standard tool response
- `SavedArtifact` - File artifact metadata
- `ResponseStoreEntry` - Response with tracking metadata
- Geometry models (`Point`, `LineString`, `Polygon`)

### constants.py

Agent names and geometry type constants:
```python
from agents.core.constants import AGENT_NAMES, POINT_TYPES, POLYGON_TYPES

AGENT_NAMES["VECTOR_AGENT"]  # "vector_agent"
AGENT_NAMES["MAPS_AGENT"]    # "osm_map_agent"
```

### logging.py

Logging setup with noise suppression:
```python
from agents.core.logging import get_logger, setup_logging

setup_logging()  # Suppresses Azure identity INFO logs
logger = get_logger("my.module")
```

### exceptions.py

Custom exceptions:
- `QueryExecutionError` - Database query failed
- `QueryValidationError` - Invalid query
- `GeoJSONParseError` - Invalid GeoJSON
- `ResponseNotFoundError` - Response ID not found
- `ArtifactNotFoundError` - Artifact missing

---

## Response Store

**Location**: `agents/core/response_store.py`

### Purpose

File-backed storage for `GeoFahamToolResponse` objects, enabling agents to access results from previous steps.

### Usage

```python
from agents.core.response_store import get_response_store

store = get_response_store()

# Store a response
store.store(response, step_number=1)

# Retrieve by ID
response = store.get("vec_abc123")

# Get all responses
all_responses = store.get_all()

# Filter by source
vector_responses = store.get_by_source("vector_agent")
```

### Shared Tool

All agents have access to `get_available_responses()`:

```python
async def get_available_responses(filter_errors: bool = True) -> str:
    """Get all available responses from other agents in the current session."""
```

This allows any agent to reference artifacts from previous steps using response IDs.

---

## Data Flow

### Typical Query Flow

```
User: "Show damaged hospitals in Central West End, Saint Louis"

1. Orchestrator analyzes query
   ├─ Facts: Need hospital locations + damage data
   └─ Plan: 
      Step 1: map_search_agent - Get hospitals in Central West End
      Step 2: postgis_agent - Join with damage data
      
2. Map Search Agent executes
   └─ get_pois(place_name="Central West End, Saint Louis", poi_category="HEALTHCARE")
   └─ Returns: hospitals.geojson (artifact)
   
3. PostGIS Agent executes
   └─ SQL with {{GEOJSON_POINTS_CTE}} placeholder
   └─ Joins hospitals with building_damage table
   └─ Returns: damaged_hospitals.geojson (artifact)
   
4. Orchestrator generates final answer
```

### Satellite Imagery Flow

```
User: "Calculate NDVI change before and after the Lahaina fire"

1. Orchestrator plans
   └─ Step 1: postgis_agent - Get disaster extent
   └─ Step 2: stac_agent - Fetch pre/post imagery
   └─ Step 3: raster_ops_agent - Calculate NDVI change

2. PostGIS Agent
   └─ Returns disaster boundary polygon
   
3. STAC Agent
   └─ execute_stac_search with daterange1 (pre) and daterange2 (post)
   └─ Returns: stac_items_date1.json, stac_items_date2.json
   
4. Raster Ops Agent
   └─ Executes Python code:
      pre_da = load_stac_items(date1_path, bbox, ['B04', 'B08'])
      post_da = load_stac_items(date2_path, bbox, ['B04', 'B08'])
      pre_ndvi = (pre_da.sel(band='B08') - pre_da.sel(band='B04')) / ...
      post_ndvi = ...
      result = post_ndvi - pre_ndvi
   └─ Returns: ndvi_change.tif (COG)
```

---

## Configuration

**Location**: `agents/core/config.py`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| **Azure OpenAI** | | |
| `AZURE_OPENAI_ENDPOINT` | Default endpoint | (required) |
| `AZURE_OPENAI_KEY` | API key (optional if using Azure AD) | - |
| `AZURE_OPENAI_GPT4O_DEPLOYMENT` | GPT-4o deployment name | `gpt-4o` |
| `AZURE_OPENAI_GPT5_DEPLOYMENT` | GPT-5 deployment name | `gpt-5.1` |
| **Database** | | |
| `POSTGRES_HOST` | Database host | `localhost` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_DB` | Database name | `geofaham` |
| `POSTGRES_USER` | Database user | (required) |
| `POSTGRES_PASSWORD` | Database password | (required) |
| **Paths** | | |
| `GEOFAHAM_BASE_DIR` | Runtime artifacts directory | `./runtime` |
| `GEOFAHAM_DATA_DIR` | Static data directory | `./data` |
| **Models** | | |
| `GEOFAHAM_DEFAULT_MODEL` | Model for simple agents | `gpt-4o` |
| `GEOFAHAM_REASONING_MODEL` | Model for complex agents | `gpt-5.1` |
| `GEOFAHAM_VECTOR_AGENT_MODEL` | Override for vector agent | - |
| `GEOFAHAM_MAPS_AGENT_MODEL` | Override for maps agent | - |
| `GEOFAHAM_STAC_AGENT_MODEL` | Override for STAC agent | - |
| `GEOFAHAM_RASTER_AGENT_MODEL` | Override for raster agent | - |

### Usage

```python
from agents.core.config import get_config

config = get_config()

# Azure OpenAI
config.azure_openai.endpoint
config.azure_openai.gpt4o_deployment

# Database
config.database.host
config.database.connection_string

# Paths
config.paths.export_dir      # Runtime artifacts
config.paths.data_dir        # Static data

# Model selection
config.get_agent_model("VECTOR_AGENT")  # Returns model name
config.get_model_spec("gpt-5.1")        # Returns ModelSpec with deployment, endpoint, api_version
```

---

## Related Documentation

- [TOOL_RESPONSE_SCHEMAS.md](TOOL_RESPONSE_SCHEMAS.md) - Complete JSON schemas for all tool responses
- [DATA_DIRECTORY_STRUCTURE.md](DATA_DIRECTORY_STRUCTURE.md) - File organization and artifact storage
- [README.md](../README.md) - Project overview and quick start
