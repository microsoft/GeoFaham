# GeoFaham Tool Response Schemas

This document defines the JSON response schemas for all agent tools in the GeoFaham system.

---

## Quick Reference for Frontend Developers

### Defaults
| Field | Default Value | Notes |
|-------|---------------|-------|
| `type` | `"layer"` | Most tools return map layers |
| `data_type` | `"vector"` | GeoJSON is the default format |
| `data` | `[]` | Empty array if no inline data |
| `artifact.format` | `"geojson"` | Default file format |
| `artifact.content_type` | `"application/geo+json"` | Default MIME type |

### Response Handling Decision Tree

```
if (response.type === "error") {
    → Show error: response.error_message
}
else if (response.type === "empty") {
    → Show info: response.summary (no results found)
}
else if (response.type === "layer") {
    → Check response.data_type:
        "vector"  → Load GeoJSON from response.artifact.path
        "raster"  → Load GeoTIFF from response.artifact.path
        "timeline"→ Load GeoJSON + use response.data for time slider
}
else if (response.type === "data") {
    → Check response.data_type:
        "tabular" → Render as table from response.data
        "json"    → Display structured data from response.data
        "stats"   → Display statistics from response.data
        "stac_items" → (Internal) Pass to raster agent
}
```

### Key Fields by Response Type

| Response Type | Required Fields | Optional Fields |
|--------------|-----------------|-----------------|
| `layer` | `artifact.path`, `summary` | `data`, `metadata` |
| `data` | `data`, `summary` | `artifact`, `metadata` |
| `error` | `error_message` | `summary`, `metadata` |
| `empty` | `summary` | `metadata` |

### Common Patterns

```javascript
// Check if response is successful
const isSuccess = response.type !== "error";

// Check if response has a map layer to render
const hasMapLayer = response.type === "layer" && response.artifact?.path;

// Check if response has tabular data
const hasTableData = response.type === "data" && response.data?.length > 0;

// Get artifact path safely
const layerPath = response.artifact?.path ?? null;

// Get feature count
const featureCount = response.artifact?.features_count ?? 0;
```

### Data Type to Renderer Mapping

| data_type | Renderer | File Type | Notes |
|-----------|----------|-----------|-------|
| `vector` | Map (GeoJSON layer) | `.geojson` | Points, lines, polygons |
| `raster` | Map (raster layer) | `.tif` | Single-band or RGB |
| `raster_multi` | Map (multiple layers) | `.tif` | Multiple outputs |
| `timeline` | Map + Time slider | `.geojson` | Has `datetime` in data |
| `tabular` | Table component | - | Rows in `data` array |
| `json` | JSON viewer | - | Structured in `data` |
| `stats` | Stats card | - | Statistics in `data` |
| `stac_items` | (Internal use) | `.geojson` | For raster agent |
| `message` | Toast/Alert | - | Info in `summary` |

---

## Base Response Schema

All tools return a `GeoFahamToolResponse` as a JSON string:

```typescript
// Response type categories
enum ResponseType {
  LAYER = "layer",           // GeoJSON/raster layer for map visualization
  DATA = "data",             // Tabular data or structured results  
  ERROR = "error",           // Error occurred
  EMPTY = "empty"            // Query succeeded but no results found
}

// Data content types
enum DataType {
  // Vector types
  VECTOR = "vector",                    // GeoJSON vector layer
  
  // Raster types
  RASTER = "raster",                    // Final raster output (GeoTIFF)
  RASTER_INTERMEDIATE = "raster_intermediate",  // Intermediate raster for chaining
  RASTER_MULTI = "raster_multi",        // Multiple raster layers
  
  // Data types
  STAC_ITEMS = "stac_items",            // STAC item references for raster processing
  TIMELINE = "timeline",                // Time-series data with dates
  TABULAR = "tabular",                  // Table/row data
  JSON = "json",                        // Generic JSON data
  STATS = "stats",                      // Statistical results
  
  // Message types
  MESSAGE = "message"                   // Text message (info/warning)
}

// Artifact file formats
enum ArtifactFormat {
  GEOJSON = "geojson",
  GEOTIFF = "geotiff", 
  JSON = "json",
  COG = "cog"                           // Cloud Optimized GeoTIFF
}

interface GeoFahamToolResponse {
  response_id: string;          // Unique ID (e.g., "vec_a1b2c3d4")
  source: string;               // Agent name (e.g., "vector_agent", "osm_map_agent")
  type: ResponseType;           // Response category
  data_type: DataType;          // Type of data content
  data: object[];               // Array of result objects
  summary: string;              // Human-readable description
  error_message?: string;       // Error details (when type="error")
  artifact?: SavedArtifact;     // File metadata (when layer saved)
  metadata?: object;            // Additional context
}

interface SavedArtifact {
  path: string;                 // File path (e.g., "/runtime/artifacts/query_jsons/roads_abc123.geojson")
  content_type: string;         // MIME type (default: "application/geo+json")
  format: ArtifactFormat;       // File format
  bytes?: number;               // File size
  features_count?: number;      // Number of GeoJSON features
  stats?: object;               // Geometry statistics
  property_keys?: object;       // Property schema by geometry type
  geom_types?: string[];        // Geometry types present
  metadata?: object;            // Additional file metadata
}
```

## Response Builder Functions

All agents should use the response builder functions in `agents/shared/responses.py`:

```python
from agents.shared.responses import (
    build_layer_response,        # For map layers (GeoJSON/GeoTIFF)
    build_raster_layer_response, # For raster outputs with CRS/bounds
    build_data_response,         # For tabular/structured data
    build_stac_items_response,   # For STAC search results
    build_timeline_response,     # For time-series data
    build_empty_response,        # For no results found
    build_error_response,        # For errors
    build_intermediate_response, # For raster chaining
)
```

---

## Response Type Categories

### 1. LAYER Response (type="layer")
Used when tool returns a GeoJSON layer for map visualization.

```json
{
  "response_id": "map_a1b2c3d4",
  "source": "osm_map_agent",
  "type": "layer",
  "data_type": "vector",
  "data": [],
  "summary": "Fetched 245 major roads from OSM. File: /runtime/artifacts/query_jsons/roads_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/roads_abc123.geojson",
    "content_type": "application/geo+json",
    "format": "geojson",
    "features_count": 245,
    "stats": {
      "total_features": 245,
      "geometry_types": ["LineString", "MultiLineString"],
      "total_length_km": 156.7
    },
    "property_keys": {
      "lines": {
        "name": {"type": "str", "fill_pct": 85},
        "highway": {"type": "str", "fill_pct": 100},
        "lanes": {"type": "int", "fill_pct": 45}
      }
    },
    "geom_types": ["LineString", "MultiLineString"]
  }
}
```

### 2. DATA Response (type="data")
Used when tool returns tabular data or messages without map layer.

```json
{
  "response_id": "vec_b2c3d4e5",
  "source": "vector_agent",
  "type": "data",
  "data_type": "json",
  "data": [
    {"id": 1, "name": "Hurricane Maria", "disaster_type": "hurricane", "date": "2017-09-20"},
    {"id": 2, "name": "Lahaina Fire", "disaster_type": "wildfire", "date": "2023-08-08"}
  ],
  "summary": "Found 2 disasters matching criteria (showing 2 of 2 rows)"
}
```

### 3. ERROR Response (type="error")
Used when tool encounters an error.

```json
{
  "response_id": "vec_c3d4e5f6",
  "source": "vector_agent",
  "type": "error",
  "data_type": "msg",
  "data": [],
  "summary": "",
  "error_message": "Database error: relation 'nonexistent_table' does not exist"
}
```

### 4. LAYER_WITH_DATA Response (type="layer_with_data")
Used when tool returns both a layer AND tabular data (e.g., aggregated queries).

```json
{
  "response_id": "vec_d4e5f6g7",
  "source": "vector_agent",
  "type": "layer",
  "data_type": "vector",
  "data": [
    {"neighborhood": "Downtown", "building_count": 1523, "total_area_sqm": 456789},
    {"neighborhood": "Midtown", "building_count": 892, "total_area_sqm": 234567}
  ],
  "summary": "Building counts by neighborhood (showing 50 of 120 rows; full data in artifact file)",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/buildings_by_neighborhood.geojson",
    "features_count": 120
  }
}
```

---

## Agent-Specific Response Schemas

### Vector Agent (`vector_agent`)

#### execute_query / execute_query_with_geojson

**Layer Response (return_layer=true, has geometry):**
```json
{
  "response_id": "vec_xxx",
  "source": "vector_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Buildings damaged by flood in Lahaina",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/damaged_buildings_abc123.geojson",
    "features_count": 342,
    "property_keys": {
      "polygons": {
        "id": {"type": "int"},
        "damage_level": {"type": "str"},
        "area_sqm": {"type": "float"}
      }
    }
  }
}
```

**Data Response (return_layer=false or no geometry):**
```json
{
  "response_id": "vec_xxx",
  "source": "vector_agent",
  "type": "data",
  "data_type": "json",
  "data": [
    {"disaster_id": 5, "name": "Lahaina Fire", "total_damaged": 2207},
    {"disaster_id": 3, "name": "Hurricane Maria", "total_damaged": 15432}
  ],
  "summary": "Damage counts by disaster (showing 50 of 50 rows)"
}
```

**Empty Result:**
```json
{
  "response_id": "vec_xxx",
  "source": "vector_agent",
  "type": "data",
  "data_type": "msg",
  "data": [],
  "summary": "No data found."
}
```

---

### Maps Agent (`osm_map_agent`)

All OSM feature tools share the same response schema.

#### get_roads / get_buildings / get_waterways / get_bridges / get_pois / get_landuse / get_natural_features / get_infrastructure / get_features_by_tags / get_neighborhoods

**Success Response:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Fetched 1,245 residential buildings from OSM. File: /runtime/artifacts/query_jsons/buildings_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/buildings_abc123.geojson",
    "features_count": 1245,
    "property_keys": {
      "polygons": {
        "name": {"type": "str"},
        "building": {"type": "str"},
        "levels": {"type": "int"},
        "height": {"type": "float"}
      }
    },
    "geom_types": ["Polygon", "MultiPolygon"]
  }
}
```

**Empty Result:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "data",
  "data_type": "msg",
  "summary": "No buildings found for the specified area and filters."
}
```

#### get_admin_boundary

**Success Response:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "layer",
  "summary": "Fetched administrative boundary for Lahaina, Hawaii. File: /runtime/artifacts/query_jsons/boundary_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/boundary_abc123.geojson",
    "features_count": 1,
    "property_keys": {
      "polygons": {
        "name": {"type": "str"},
        "matched_query": {"type": "str"},
        "search_method": {"type": "str"}
      }
    }
  }
}
```

#### get_address_coordinates

**Success Response:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "layer",
  "summary": "Geocoded 'Seattle, WA'. Saved as Point in /runtime/artifacts/query_jsons/geocode_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/geocode_abc123.geojson",
    "features_count": 1,
    "property_keys": {
      "points": {
        "name": {"type": "str"},
        "display_name": {"type": "str"},
        "matched_query": {"type": "str"}
      }
    },
    "geom_types": ["Point"]
  }
}
```

#### get_place_bounding_box

**Success Response:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "layer",
  "summary": "Got bounding box for 'Lahaina, Hawaii'. Saved to /runtime/artifacts/query_jsons/bbox_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/bbox_abc123.geojson",
    "features_count": 1,
    "property_keys": {
      "polygons": {
        "name": {"type": "str"},
        "bbox": {"type": "list"}
      }
    },
    "geom_types": ["Polygon"]
  }
}
```

#### search_feature_by_name

**Success Response:**
```json
{
  "response_id": "map_xxx",
  "source": "osm_map_agent",
  "type": "layer",
  "summary": "Found 3 segment(s) of road 'Front Street' (LineString). File: /runtime/artifacts/query_jsons/road_search_abc123.geojson",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/road_search_abc123.geojson",
    "features_count": 3,
    "geom_types": ["LineString"]
  }
}
```

---

### STAC Agent (`stac_agent`)

#### get_collection_details

**Success Response:**
```json
{
  "response_id": "stac_xxx",
  "source": "stac_agent",
  "type": "data",
  "data_type": "json",
  "data": [{
    "type": "collection_details",
    "collections": {
      "sentinel-2-l2a": {
        "title": "Sentinel-2 Level-2A",
        "description": "...",
        "temporal_extent": ["2015-06-27", null],
        "spatial_extent": [-180, -90, 180, 90],
        "bands": ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12", "SCL"],
        "gsd": [10, 20, 60],
        "revisit_days": 5
      }
    },
    "unknown_collections": []
  }],
  "summary": "Retrieved details for 1 collections: sentinel-2-l2a"
}
```

#### execute_stac_search (mode="fetch")

**Success Response:**
```json
{
  "response_id": "stac_xxx",
  "source": "stac_agent",
  "type": "data",
  "data_type": "stac_items",
  "data": [
    {
      "type": "stac_items",
      "collection_group": "pre_fire_imagery",
      "items_json_path": "/runtime/artifacts/query_jsons/stac_results_abc123_pre_fire_imagery_date1.geojson",
      "search_params": {
        "collection": "sentinel-2-l2a",
        "collection_group": "pre_fire_imagery",
        "datetime": "2023-08-01T00:00:00Z",
        "scenes_found": 5,
        "coverage_percent": 95.2,
        "bbox": [-156.7, 20.8, -156.6, 20.9],
        "bands": ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"],
        "aoi_path": "/path/to/aoi.geojson"
      }
    },
    {
      "type": "stac_items",
      "collection_group": "post_fire_imagery",
      "items_json_path": "/runtime/artifacts/query_jsons/stac_results_abc123_post_fire_imagery_date1.geojson",
      "search_params": {
        "collection": "sentinel-2-l2a",
        "datetime": "2023-08-10T00:00:00Z",
        "scenes_found": 4,
        "coverage_percent": 92.1,
        "bbox": [-156.7, 20.8, -156.6, 20.9],
        "bands": ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"]
      }
    }
  ],
  "summary": "Found STAC items - Date 1: 5, Date 2: 4 across 2 collection groups: pre_fire_imagery, post_fire_imagery."
}
```

#### execute_stac_search (mode="show")

**Success Response:**
```json
{
  "response_id": "stac_xxx",
  "source": "stac_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Mosaic created for sentinel-2-l2a (5 items) from 2023-08-01 to 2023-08-05. Cloud cover ≤20%.",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/stac_results_abc123.geojson",
    "content_type": "application/geo+json",
    "features_count": 5,
    "metadata": {
      "collections": ["sentinel-2-l2a"],
      "item_count": 5,
      "date_range": "2023-08-01 to 2023-08-05",
      "bbox": [-156.7, 20.8, -156.6, 20.9],
      "visualization_hints": {
        "bands": ["B04", "B03", "B02"],
        "rescale": [[0, 3000], [0, 3000], [0, 3000]],
        "colormap": null
      }
    }
  },
  "metadata": {
    "mosaic_url": "https://planetarycomputer.microsoft.com/api/data/v1/mosaic/...",
    "tiles_url": "https://planetarycomputer.microsoft.com/api/data/v1/mosaic/.../tiles/{z}/{x}/{y}",
    "stac_item_tiles": [
      {"item_id": "S2A_...", "tile_url": "https://..."}
    ]
  }
}
```

---

### Raster Operations Agent (`raster_ops_agent`)

#### execute_custom_raster_code

**Single Raster Layer Response (expected_result_type="raster"):**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "raster",
  "data": [{
    "type": "single_layer",
    "url": "/runtime/artifacts/query_jsons/raster_code_result_abc123.tif",
    "statistics": {
      "shape": [1, 2048, 2048],
      "valid_pixels": 4194304,
      "total_pixels": 4194304,
      "min": -0.45,
      "max": 0.92,
      "mean": 0.34,
      "std": 0.18,
      "percentiles": {
        "p10": 0.12,
        "p25": 0.22,
        "p50": 0.35,
        "p75": 0.45,
        "p90": 0.58
      }
    },
    "bounds": [-156.7, 20.8, -156.6, 20.9],
    "min_scale": -0.45,
    "max_scale": 0.92
  }],
  "metadata": {
    "success": true,
    "result_explanation": "NDVI difference map showing vegetation loss",
    "result_type": "raster"
  }
}
```

**Classification Raster Response (integer data):**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "raster",
  "data": [{
    "type": "single_layer",
    "url": "/runtime/artifacts/query_jsons/burn_severity_abc123.tif",
    "statistics": {
      "shape": [1, 2048, 2048],
      "valid_pixels": 4194304,
      "total_pixels": 4194304,
      "min": 0,
      "max": 4,
      "class_distribution": {
        "0": 15.2,
        "1": 25.3,
        "2": 32.1,
        "3": 18.7,
        "4": 8.7
      }
    },
    "bounds": [-156.7, 20.8, -156.6, 20.9],
    "min_scale": 0,
    "max_scale": 4
  }],
  "metadata": {
    "success": true,
    "result_explanation": "Burn severity classification (0=unburned, 1=low, 2=moderate, 3=high, 4=very high)",
    "result_type": "raster"
  }
}
```

**Temporal Sequence Response:**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "raster_mix",
  "summary": "Monthly NDVI timeline from Jan 2023 to Dec 2023",
  "metadata": {
    "success": true,
    "result_explanation": "Monthly NDVI timeline",
    "result_type": "raster",
    "layers": {
      "timeline": {
        "type": "temporal_sequence",
        "temporal_layers": [
          {
            "label": "2023-01",
            "url": "/runtime/artifacts/query_jsons/timeline_202301_abc123.tif",
            "bounds": [-156.7, 20.8, -156.6, 20.9],
            "statistics": {"min": 0.1, "max": 0.8, "mean": 0.45}
          },
          {
            "label": "2023-02",
            "url": "/runtime/artifacts/query_jsons/timeline_202302_def456.tif",
            "bounds": [-156.7, 20.8, -156.6, 20.9],
            "statistics": {"min": 0.15, "max": 0.75, "mean": 0.42}
          }
        ],
        "min_scale": 0.1,
        "max_scale": 0.8
      },
      "dnbr": {
        "type": "single_layer",
        "url": "/path/to/runtime/artifacts/query_jsons/raster_code_result_1b0d9cfe.tif",
        "statistics": {
            "shape": [
                261,
                168
            ],
            "min": -0.1139688948333744,
            "max": 0.6063368473118291,
            "mean": 0.09802395583317876,
            "std": 0.0939892923050895,
            "percentiles": {
                "p10": -0.004568310927586529,
                "p25": 0.01845963870765361,
                "p50": 0.07870059809699176,
                "p75": 0.16210879176455234,
                "p90": 0.2193227573745545
            }
        },
        "bounds": [
            -156.68763677279597,
            20.855562852496423,
            -156.6548277924758,
            20.902946937436923
        ],
        "min_scale": -0.1139688948333744,
        "max_scale": 0.6063368473118291
    }
    }
  }
}
```

**Vector Result Response (expected_result_type="vector"):**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Extracted burn perimeter polygons",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/burn_perimeter_abc123.geojson",
    "features_count": 15,
    "property_keys": {
      "polygons": {
        "severity_class": {"type": "int"},
        "area_sqm": {"type": "float"}
      }
    }
  },
  "metadata": {
    "success": true,
    "result_explanation": "Burn perimeter polygons classified by severity",
    "result_type": "vector"
  }
}
```

**Intermediate Save Response:**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "data",
  "data_type": "raster_intermediate",
  "summary": "Saved pre-fire NDVI as intermediate layer",
  "metadata": {
    "saved_intermediate_paths": {
      "pre_ndvi": "/runtime/artifacts/query_jsons/intermediate_pre_ndvi.tif"
    },
    "count": 1
  }
}
```

**Error Response:**
```json
{
  "response_id": "raster_xxx",
  "source": "raster_ops_agent",
  "type": "error",
  "error_message": "Code execution error: name 'undefined_variable' is not defined",
  "metadata": {
    "error_type": "execution",
    "result_explanation": "Attempted burn severity calculation"
  }
}
```

---

## Shared Tool: get_available_responses

Available to all agents. Returns list of all responses in the session.

**Response:**
```json
{
  "responses": [
    {
      "response_id": "map_abc123",
      "source": "osm_map_agent",
      "type": "layer",
      "data_type": "vector",
      "summary": "Fetched administrative boundary for Lahaina",
      "artifact": {
        "path": "/runtime/artifacts/query_jsons/boundary_abc123.geojson",
        "features_count": 1
      }
    },
    {
      "response_id": "stac_def456",
      "source": "stac_agent",
      "type": "data",
      "data_type": "stac_items",
      "summary": "Found STAC items - Date 1: 5, Date 2: 4",
      "data": [...]
    }
  ],
  "count": 2
}
```

---

## STAC Items File Format

When STAC agent saves items (mode="fetch"), the JSON file structure:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "stac_version": "1.0.0",
      "id": "S2A_MSIL2A_20230808T210931_R057_T04QGJ_20230809T041234",
      "geometry": {"type": "Polygon", "coordinates": [...]},
      "bbox": [-156.7, 20.8, -156.6, 20.9],
      "properties": {
        "datetime": "2023-08-08T21:09:31Z",
        "eo:cloud_cover": 5.2,
        "proj:epsg": 32604,
        "proj:code": "EPSG:32604"
      },
      "assets": {
        "B02": {"href": "https://..."},
        "B03": {"href": "https://..."},
        "B04": {"href": "https://..."}
      },
      "links": []
    }
  ],
  "metadata": {
    "collection": "sentinel-2-l2a",
    "collection_group": "pre_fire_imagery",
    "datetime": "2023-08-08T21:09:31Z",
    "scenes_found": 5,
    "coverage_percent": 95.2,
    "bbox": [-156.7, 20.8, -156.6, 20.9],
    "bands": ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"],
    "aoi_path": "/path/to/aoi.geojson"
  }
}
```

---

## Property Keys Schema

The `property_keys` object in artifacts describes the schema of GeoJSON properties:

```json
{
  "points": {
    "name": {"type": "str", "fill_pct": 100, "nullable": false},
    "elevation": {"type": "float", "fill_pct": 85, "nullable": true}
  },
  "lines": {
    "name": {"type": "str"},
    "highway": {"type": "str"},
    "lanes": {"type": "int"}
  },
  "polygons": {
    "name": {"type": "str"},
    "building": {"type": "str"},
    "area_sqm": {"type": "float"}
  }
}
```

**Property Types:**
- `str` - String/text
- `int` - Integer number
- `float` - Decimal number
- `bool` - Boolean (true/false)
- `list` - Array/list
- `dict` - Object/dictionary

---

## Statistics Schema

### Continuous Data Statistics
```json
{
  "shape": [1, 2048, 2048],
  "valid_pixels": 4000000,
  "total_pixels": 4194304,
  "min": -0.45,
  "max": 0.92,
  "mean": 0.34,
  "std": 0.18,
  "percentiles": {
    "p10": 0.12,
    "p25": 0.22,
    "p50": 0.35,
    "p75": 0.45,
    "p90": 0.58
  }
}
```

### Categorical/Classification Data Statistics
```json
{
  "shape": [1, 2048, 2048],
  "valid_pixels": 4000000,
  "total_pixels": 4194304,
  "min": 0,
  "max": 4,
  "class_distribution": {
    "0": 15.2,
    "1": 25.3,
    "2": 32.1,
    "3": 18.7,
    "4": 8.7
  }
}
```

### Empty/No Data Statistics
```json
{
  "count": 0,
  "valid_pixels": 0,
  "total_pixels": 4194304
}
```
