# GeoFaham Workflow Example: Multi-Agent Disaster Response

This document illustrates a complete end-to-end workflow where all four specialized agents collaborate to answer a complex geospatial query about the 2023 Lahaina, Hawaii wildfire.

---

## User Query

> **"For the Lahaina fire on 2023-08-08, identify hospitals within 500 meters of severely burned areas and estimate how many people each serves based on nearby population."**

This query requires:
- **Vector Agent**: Retrieve the disaster AOI from the database
- **Maps Agent**: Extract hospital locations and population data from OpenStreetMap
- **STAC Agent**: Fetch pre- and post-fire satellite imagery
- **Raster Ops Agent**: Compute burn severity index and identify severe burn zones
- **Vector Agent** (again): Perform spatial join to find hospitals near burned areas

---

## Phase 1: Orchestrator Planning

### 1.1 Initial Team Assembly

The orchestrator receives the user query and assembles the agent team with their capabilities:

```
We are working to address the following user request:

For the Lahaina fire on 2023-08-08, identify hospitals within 500 meters of 
severely burned areas and estimate how many people each serves based on 
nearby population.

To answer this request we have assembled the following team:

• postgis_agent: Queries PostGIS disaster database for damage assessments, 
  flood maps, and disaster AOI boundaries. Outputs GeoJSON layers and statistics.

• osm_agent: Extracts OpenStreetMap features (buildings, roads, POIs) within 
  a given boundary. 14 specialized tools for different feature types.

• stac_agent: Searches Planetary Computer STAC catalog for satellite imagery. 
  Supports Sentinel-2, Landsat, and static datasets with temporal filtering.

• raster_ops_agent: Generates and executes Python code for raster analysis. 
  Computes indices (NDVI, dNBR), classifications, and zonal statistics.

Available Disasters in Database:
- fire | 2023-08-08 | Lahaina, Maui, Hawaii, USA | has_building_damage_assessment
- flood | 2024-10-31 | Valencia, Spain | has_flood_maps
- cyclone | 2025-11-30 | Colombo, Sri Lanka | has_flood_maps
```

### 1.2 Facts Extraction and Plan Generation

The orchestrator extracts structured facts from the query and generates a multi-step plan:

```json
{
  "facts_extracted": {
    "disaster_type": "fire",
    "disaster_date": "2023-08-08",
    "location": {
      "city": "Lahaina",
      "county": "Maui",
      "state": "Hawaii",
      "country": "USA"
    },
    "analysis_type": "exposure_assessment",
    "target_features": ["hospitals"],
    "buffer_distance_meters": 500,
    "additional_requirements": ["population_estimation"]
  },
  "plan": [
    {
      "step": 1,
      "agent": "postgis_agent",
      "action": "Retrieve Lahaina fire AOI/extent from disaster database",
      "purpose": "Establish spatial boundary for all subsequent analysis"
    },
    {
      "step": 2,
      "agent": "osm_agent",
      "action": "Extract hospital locations within the fire AOI",
      "purpose": "Identify healthcare facilities in the affected area"
    },
    {
      "step": 3,
      "agent": "osm_agent",
      "action": "Extract population density or residential buildings",
      "purpose": "Estimate service population for each hospital"
    },
    {
      "step": 4,
      "agent": "stac_agent",
      "action": "Fetch pre- and post-fire Sentinel-2 imagery",
      "purpose": "Obtain multispectral data for burn severity calculation"
    },
    {
      "step": 5,
      "agent": "raster_ops_agent",
      "action": "Compute dNBR burn severity index and classify severe burns",
      "purpose": "Identify areas with high burn intensity (dNBR > 0.44)"
    },
    {
      "step": 6,
      "agent": "postgis_agent",
      "action": "Spatial join: hospitals within 500m of severe burn polygons",
      "purpose": "Final answer: at-risk hospitals with population estimates"
    }
  ]
}
```

---

## Phase 2: Step-by-Step Execution

### Step 1: Vector Agent — Retrieve Disaster AOI

#### Orchestrator Validation & Handoff

```json
{
  "validation_checks": {
    "plan_adherence": {
      "current_step": "Step 1: Retrieve Lahaina fire AOI from disaster database",
      "all_previous_steps_completed": false,
      "required_artifacts_present": false,
      "can_skip_step": false
    },
    "input_validation": {
      "next_agent_needs": [
        "Disaster type: fire",
        "Disaster date: 2023-08-08",
        "Location: Lahaina, Maui, Hawaii, USA"
      ],
      "available_in_ledger": [],
      "missing_inputs": ["AOI geometry not yet retrieved"]
    }
  }
}
```

#### Orchestrator Message to Agent

```
**Question**: Retrieve the official AOI/extent geometry for the Lahaina fire 
that occurred on 2023-08-08.

**Context**: The user needs a burn severity analysis for the Lahaina fire 
(disaster type: fire) in Lahaina, Maui, Hawaii, USA. This AOI will define 
the spatial boundary for subsequent OSM queries, satellite imagery search, 
and raster analysis. Return as a single polygon.
```

#### Vector Agent Tool Call

```json
{
  "tool": "execute_query",
  "arguments": {
    "query": "SELECT id, disaster_type, disaster_date, description, area, city, county, state, country, ST_AsGeoJSON(geom) AS geom FROM disasters WHERE disaster_type = 'fire' AND disaster_date = '2023-08-08' AND city = 'Lahaina' AND county = 'Maui' AND state = 'Hawaii' AND country = 'USA' LIMIT 1;",
    "return_layer": true,
    "results_description": "Official single-polygon AOI for Lahaina fire on 2023-08-08"
  }
}
```

#### Vector Agent Response

```json
{
  "response_id": "vec_a1b2c3d4",
  "source": "postgis_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Official single-polygon AOI for the Lahaina fire on 2023-08-08",
  "artifact": {
    "path": "/runtime/artifacts/lahaina_fire_aoi.geojson",
    "format": "geojson",
    "features_count": 1,
    "stats": {
      "geometry_types": {"Polygon": 1},
      "bounding_box": [-156.6876, 20.8555, -156.6546, 20.9030],
      "poly_total_area_m2": 11894479.77
    }
  }
}
```

#### Progress Ledger Update

```json
{
  "completed_steps": [
    {
      "step": 1,
      "agent": "postgis_agent",
      "response_id": "vec_a1b2c3d4",
      "artifact_path": "/runtime/artifacts/lahaina_fire_aoi.geojson",
      "key_output": "Single polygon AOI, 11.89 km², bbox: [-156.69, 20.86, -156.65, 20.90]"
    }
  ],
  "next_step": 2,
  "status": "in_progress"
}
```

---

### Step 2: Maps Agent — Extract Hospitals

#### Orchestrator Validation & Handoff

```json
{
  "validation_checks": {
    "plan_adherence": {
      "current_step": "Step 2: Extract hospital locations within the fire AOI",
      "all_previous_steps_completed": true,
      "required_artifacts_present": true
    },
    "input_validation": {
      "next_agent_needs": [
        "AOI polygon for spatial constraint",
        "Feature type: hospitals/healthcare"
      ],
      "available_in_ledger": [
        "vec_a1b2c3d4: Lahaina fire AOI GeoJSON"
      ],
      "missing_inputs": []
    }
  }
}
```

#### Orchestrator Message to Agent

```
**Question**: Extract all hospital and healthcare facility locations within 
the Lahaina fire AOI.

**Context**: Use the AOI from response vec_a1b2c3d4 as your spatial boundary. 
We need point locations of hospitals with attributes (name, capacity if available). 
These will later be checked for proximity to severely burned areas.
```

#### Maps Agent Tool Call

```json
{
  "tool": "get_healthcare_features",
  "arguments": {
    "boundary_source": "vec_a1b2c3d4",
    "healthcare_types": ["hospital", "clinic"],
    "include_attributes": ["name", "beds", "emergency"]
  }
}
```

#### Maps Agent Response

```json
{
  "response_id": "osm_e5f6g7h8",
  "source": "osm_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Found 3 healthcare facilities within Lahaina fire AOI",
  "artifact": {
    "path": "/runtime/artifacts/lahaina_hospitals.geojson",
    "format": "geojson",
    "features_count": 3,
    "stats": {
      "geometry_types": {"Point": 3},
      "attribute_summary": {
        "name": ["Maui Memorial Medical Center", "Lahaina Urgent Care", "West Maui Hospital"],
        "healthcare_type": {"hospital": 2, "clinic": 1}
      }
    }
  }
}
```

---

### Step 3: Maps Agent — Extract Residential Buildings

#### Orchestrator Message to Agent

```
**Question**: Extract residential building footprints within the Lahaina fire 
AOI for population estimation.

**Context**: Use the AOI from vec_a1b2c3d4. We need building polygons classified 
as residential to estimate population served by each hospital based on building 
density and proximity.
```

#### Maps Agent Tool Call

```json
{
  "tool": "get_building_footprints",
  "arguments": {
    "boundary_source": "vec_a1b2c3d4",
    "building_types": ["residential", "apartments", "house"],
    "include_attributes": ["levels", "building:levels"]
  }
}
```

#### Maps Agent Response

```json
{
  "response_id": "osm_i9j0k1l2",
  "source": "osm_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Extracted 2,847 residential buildings in Lahaina fire AOI",
  "artifact": {
    "path": "/runtime/artifacts/lahaina_residential.geojson",
    "format": "geojson",
    "features_count": 2847,
    "stats": {
      "geometry_types": {"Polygon": 2847},
      "total_area_m2": 523456.78,
      "attribute_summary": {
        "building_type": {"house": 2134, "apartments": 456, "residential": 257}
      }
    }
  }
}
```

---

### Step 4: STAC Agent — Fetch Satellite Imagery

#### Orchestrator Validation & Handoff

```json
{
  "validation_checks": {
    "plan_adherence": {
      "current_step": "Step 4: Fetch pre- and post-fire Sentinel-2 imagery",
      "all_previous_steps_completed": true,
      "required_artifacts_present": true
    },
    "input_validation": {
      "next_agent_needs": [
        "AOI polygon for spatial search",
        "Disaster date to define temporal windows",
        "Collection type: optical with NIR and SWIR bands"
      ],
      "available_in_ledger": [
        "vec_a1b2c3d4: Lahaina fire AOI",
        "osm_e5f6g7h8: Hospitals",
        "osm_i9j0k1l2: Residential buildings"
      ]
    }
  }
}
```

#### Orchestrator Message to Agent

```
**Question**: Fetch low-cloud pre- and post-fire Sentinel-2 imagery for the 
Lahaina fire AOI, suitable for burn severity (dNBR) computation.

**Context**: Disaster date is 2023-08-08. Use AOI from vec_a1b2c3d4. We need 
NIR (B08), SWIR2 (B12), and SCL bands for NBR calculation and cloud masking. 
Pre-fire window: 2023-07-01 to 2023-08-07. Post-fire window: 2023-08-09 to 
2023-09-15.
```

#### STAC Agent Tool Calls

```json
[
  {
    "tool": "get_collection_details",
    "arguments": {
      "collection_ids": ["sentinel-2-l2a"]
    }
  }
]
```

Then:

```json
{
  "tool": "execute_stac_search",
  "arguments": {
    "geojson_path": "/runtime/artifacts/lahaina_fire_aoi.geojson",
    "limit": 50,
    "mode": "fetch",
    "min_coverage_percent": 80.0,
    "reasoning": {
      "collection_selection": "Sentinel-2 L2A selected for 10-20m resolution optical imagery with NIR and SWIR bands required for NBR calculation",
      "datetime_logic": "Pre-fire: July 1 to Aug 7, 2023. Post-fire: Aug 9 to Sep 15, 2023. Windows avoid the fire date to ensure clean imagery."
    },
    "collections": {
      "pre_fire": {
        "collection_ids": ["sentinel-2-l2a"],
        "query": {"eo:cloud_cover": {"lt": 20}},
        "daterange1": "2023-07-01/2023-08-07"
      },
      "post_fire": {
        "collection_ids": ["sentinel-2-l2a"],
        "query": {"eo:cloud_cover": {"lt": 20}},
        "daterange1": "2023-08-09/2023-09-15"
      }
    }
  }
}
```

#### STAC Agent Response

```json
{
  "response_id": "stac_m3n4o5p6",
  "source": "stac_agent",
  "type": "data",
  "data_type": "stac_items",
  "summary": "Found 15 Sentinel-2 scenes: 9 pre-fire, 6 post-fire, all with >80% AOI coverage",
  "data": [
    {
      "collection_group": "pre_fire",
      "items_json_path": "/runtime/artifacts/stac_pre_fire.geojson",
      "search_params": {
        "collection": "sentinel-2-l2a",
        "scenes_found": 9,
        "coverage_percent": 100.0,
        "bands": ["B08", "B12", "SCL", "visual"],
        "temporal_coverage": {
          "date_groups": {
            "2023-07-04": {"count": 2, "coverage_percent": 100.0},
            "2023-07-14": {"count": 2, "coverage_percent": 100.0},
            "2023-07-24": {"count": 1, "coverage_percent": 100.0},
            "2023-07-29": {"count": 2, "coverage_percent": 100.0},
            "2023-08-03": {"count": 2, "coverage_percent": 100.0}
          },
          "coverage_summary": "5/5 dates with >80% coverage"
        }
      }
    },
    {
      "collection_group": "post_fire",
      "items_json_path": "/runtime/artifacts/stac_post_fire.geojson",
      "search_params": {
        "collection": "sentinel-2-l2a",
        "scenes_found": 6,
        "coverage_percent": 100.0,
        "temporal_coverage": {
          "date_groups": {
            "2023-08-13": {"count": 1, "coverage_percent": 100.0},
            "2023-08-18": {"count": 1, "coverage_percent": 100.0},
            "2023-08-23": {"count": 1, "coverage_percent": 100.0}
          },
          "coverage_summary": "3/3 dates with >80% coverage"
        }
      }
    }
  ]
}
```

---

### Step 5: Raster Ops Agent — Compute Burn Severity

#### Orchestrator Message to Agent

```
**Question**: Compute a burn severity (dNBR) map and classify severely burned 
areas (dNBR > 0.44) as polygons.

**Context**: 
- AOI: vec_a1b2c3d4 (Lahaina fire footprint)
- Pre-fire imagery: stac_m3n4o5p6 pre_fire group
- Post-fire imagery: stac_m3n4o5p6 post_fire group
- Output needed: (1) dNBR raster clipped to AOI, (2) vectorized polygons of 
  severely burned areas (dNBR > 0.44) for spatial join with hospitals.
```

#### Raster Ops Agent Tool Call

The agent generates Python code for execution:

```json
{
  "tool": "execute_custom_raster_code",
  "arguments": {
    "code": "# Load AOI and STAC items\naoi_path = '/runtime/artifacts/lahaina_fire_aoi.geojson'\naoi_gdf, aoi_epsg = load_vector_file(aoi_path)\nminx, miny, maxx, maxy = aoi_gdf.total_bounds\nbbox = [float(minx), float(miny), float(maxx), float(maxy)]\n\n# Load pre-fire Sentinel-2 data (B08=NIR, B12=SWIR2, SCL for clouds)\npre_items = '/runtime/artifacts/stac_pre_fire.geojson'\npre_da, pre_epsg = load_stac_items(pre_items, bbox, ['B08', 'B12', 'SCL'], 20)\n\n# Load post-fire Sentinel-2 data\npost_items = '/runtime/artifacts/stac_post_fire.geojson'\npost_da, post_epsg = load_stac_items(post_items, bbox, ['B08', 'B12', 'SCL'], 20)\n\n# Cloud masking using SCL (keep vegetation=4, bare soil=5)\npre_clear = (pre_da.sel(band='SCL') == 4) | (pre_da.sel(band='SCL') == 5)\npost_clear = (post_da.sel(band='SCL') == 4) | (post_da.sel(band='SCL') == 5)\n\n# Compute NBR = (NIR - SWIR2) / (NIR + SWIR2)\npre_nir = pre_da.sel(band='B08').where(pre_clear)\npre_swir = pre_da.sel(band='B12').where(pre_clear)\npre_nbr = (pre_nir - pre_swir) / (pre_nir + pre_swir)\n\npost_nir = post_da.sel(band='B08').where(post_clear)\npost_swir = post_da.sel(band='B12').where(post_clear)\npost_nbr = (post_nir - post_swir) / (post_nir + post_swir)\n\n# Temporal median composites\npre_nbr_med = pre_nbr.median(dim='time').persist()\npost_nbr_med = post_nbr.median(dim='time').persist()\n\n# Clip to AOI\npre_nbr_clip = clip_to_aoi(pre_nbr_med, aoi_gdf).persist()\npost_nbr_clip = clip_to_aoi(post_nbr_med, aoi_gdf).persist()\n\n# Compute dNBR (positive = vegetation loss)\ndnbr = pre_nbr_clip - post_nbr_clip\n\n# Classify severe burns (dNBR > 0.44)\nsevere_mask = dnbr > 0.44\nsevere_polygons = raster_to_polygons(severe_mask, min_area_m2=100)\n\n# Compute statistics\nstats = {\n    'min': float(dnbr.min().compute()),\n    'max': float(dnbr.max().compute()),\n    'mean': float(dnbr.mean().compute()),\n    'severe_area_m2': float(severe_mask.sum().compute() * 400)  # 20m resolution\n}\n\nresult = {'dnbr': dnbr, 'severe_polygons': severe_polygons}\n\nmetadata = {\n    'description': 'dNBR burn severity and classified severe burn polygons',\n    'parameters': {\n        'sensor': 'Sentinel-2 L2A',\n        'resolution_m': 20,\n        'severe_threshold': 0.44,\n        'index': 'dNBR = NBR_pre - NBR_post'\n    },\n    'stats': stats,\n    'save_as_intermediate': True,\n    'intermediate_name': 'lahaina_burn_severity'\n}",
    "result_explanation": "Computed dNBR burn severity raster and extracted severe burn polygons (dNBR > 0.44) for spatial join with hospitals",
    "return_layer": true,
    "expected_result_type": "both"
  }
}
```

#### Raster Ops Agent Response

```json
{
  "response_id": "raster_q7r8s9t0",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "raster",
  "summary": "Computed dNBR burn severity; 2.3 km² classified as severe burns (dNBR > 0.44)",
  "data": [
    {
      "description": "dNBR burn severity and classified severe burn polygons",
      "parameters": {
        "sensor": "Sentinel-2 L2A",
        "resolution_m": 20,
        "severe_threshold": 0.44,
        "index": "dNBR = NBR_pre - NBR_post"
      },
      "stats": {
        "min": -0.152,
        "max": 0.605,
        "mean": 0.095,
        "severe_area_m2": 2300000
      },
      "saved_intermediate_paths": {
        "dnbr": "/runtime/artifacts/lahaina_dnbr.tif",
        "severe_polygons": "/runtime/artifacts/lahaina_severe_burns.geojson"
      }
    }
  ],
  "artifact": {
    "path": "/runtime/artifacts/lahaina_dnbr.tif",
    "format": "geotiff",
    "stats": {
      "value_range": [-0.152, 0.605],
      "crs": "EPSG:32604"
    }
  }
}
```

---

### Step 6: Vector Agent — Spatial Join

#### Orchestrator Message to Agent

```
**Question**: Find hospitals within 500 meters of severely burned areas and 
calculate estimated service population based on nearby residential buildings.

**Context**: 
- Hospitals: osm_e5f6g7h8 (3 facilities)
- Severe burn polygons: raster_q7r8s9t0 (severe_polygons)
- Residential buildings: osm_i9j0k1l2 (2,847 buildings)

Perform: 
1. Buffer severe burn polygons by 500m
2. Spatial join with hospitals to find those intersecting the buffer
3. For each affected hospital, count residential buildings within 2km and 
   estimate population (assume 2.5 persons per building)
```

#### Vector Agent Tool Call

```json
{
  "tool": "execute_query",
  "arguments": {
    "query": "WITH severe_burns AS (\n  SELECT ST_Union(geom) AS geom FROM '{{GEOJSON_severe_polygons}}'\n),\nbuffered AS (\n  SELECT ST_Buffer(geom::geography, 500)::geometry AS geom FROM severe_burns\n),\nhospitals AS (\n  SELECT * FROM '{{GEOJSON_hospitals}}'\n),\nresidential AS (\n  SELECT * FROM '{{GEOJSON_residential}}'\n),\nat_risk_hospitals AS (\n  SELECT h.* \n  FROM hospitals h, buffered b\n  WHERE ST_Intersects(h.geom, b.geom)\n)\nSELECT \n  h.name,\n  h.healthcare_type,\n  COUNT(r.geom) AS nearby_buildings,\n  COUNT(r.geom) * 2.5 AS estimated_population,\n  ST_AsGeoJSON(h.geom) AS geom\nFROM at_risk_hospitals h\nLEFT JOIN residential r ON ST_DWithin(h.geom::geography, r.geom::geography, 2000)\nGROUP BY h.name, h.healthcare_type, h.geom",
    "return_layer": true,
    "results_description": "Hospitals within 500m of severe burns with population estimates",
    "placeholder_responses": {
      "severe_polygons": "raster_q7r8s9t0",
      "hospitals": "osm_e5f6g7h8",
      "residential": "osm_i9j0k1l2"
    }
  }
}
```

#### Vector Agent Response

```json
{
  "response_id": "vec_u1v2w3x4",
  "source": "postgis_agent",
  "type": "layer",
  "data_type": "vector",
  "summary": "Found 2 hospitals within 500m of severely burned areas",
  "data": [
    {
      "name": "Maui Memorial Medical Center",
      "healthcare_type": "hospital",
      "nearby_buildings": 834,
      "estimated_population": 2085,
      "distance_to_severe_burn_m": 127
    },
    {
      "name": "Lahaina Urgent Care",
      "healthcare_type": "clinic",
      "nearby_buildings": 456,
      "estimated_population": 1140,
      "distance_to_severe_burn_m": 342
    }
  ],
  "artifact": {
    "path": "/runtime/artifacts/at_risk_hospitals.geojson",
    "format": "geojson",
    "features_count": 2
  }
}
```

---

## Phase 3: Final Answer Synthesis

The orchestrator synthesizes all agent outputs into a coherent final response:

### Final Progress Ledger

```json
{
  "completed_steps": [
    {"step": 1, "agent": "postgis_agent", "response_id": "vec_a1b2c3d4", "summary": "AOI retrieved: 11.89 km²"},
    {"step": 2, "agent": "osm_agent", "response_id": "osm_e5f6g7h8", "summary": "3 hospitals extracted"},
    {"step": 3, "agent": "osm_agent", "response_id": "osm_i9j0k1l2", "summary": "2,847 residential buildings"},
    {"step": 4, "agent": "stac_agent", "response_id": "stac_m3n4o5p6", "summary": "15 Sentinel-2 scenes"},
    {"step": 5, "agent": "raster_ops_agent", "response_id": "raster_q7r8s9t0", "summary": "dNBR computed; 2.3 km² severe"},
    {"step": 6, "agent": "postgis_agent", "response_id": "vec_u1v2w3x4", "summary": "2 hospitals at risk identified"}
  ],
  "status": "completed"
}
```

### Orchestrator Final Answer

```
## Analysis Complete

For the Lahaina fire on 2023-08-08, I identified **2 hospitals within 500 meters 
of severely burned areas**:

| Hospital | Type | Distance to Severe Burn | Est. Service Population |
|----------|------|------------------------|------------------------|
| Maui Memorial Medical Center | Hospital | 127 m | 2,085 |
| Lahaina Urgent Care | Clinic | 342 m | 1,140 |

### Key Findings

1. **Burn Severity Analysis**: Using pre- and post-fire Sentinel-2 imagery, 
   I computed dNBR burn severity. Approximately **2.3 km²** (19% of the fire 
   footprint) experienced severe burns (dNBR > 0.44).

2. **At-Risk Facilities**: Both facilities identified serve a combined 
   estimated population of 3,225 people based on nearby residential density.

3. **West Maui Hospital** (the third facility in the AOI) is **not** within 
   500m of severely burned areas.

### Generated Artifacts

- Fire AOI boundary: `vec_a1b2c3d4`
- dNBR burn severity raster: `raster_q7r8s9t0`
- Severe burn polygons: `raster_q7r8s9t0` (severe_polygons)
- At-risk hospitals layer: `vec_u1v2w3x4`
```

---

## Response Store: Cross-Agent Data Sharing

Throughout execution, all agent responses are registered in the Response Store, enabling agents to reference previous outputs:

```
Response Store Contents (Session: 2023-08-15T10:30:00Z)
─────────────────────────────────────────────────────────
ID                  Source          Type    Summary
─────────────────────────────────────────────────────────
vec_a1b2c3d4       postgis_agent   layer   Lahaina fire AOI (1 polygon)
osm_e5f6g7h8       osm_agent       layer   Hospitals (3 points)
osm_i9j0k1l2       osm_agent       layer   Residential buildings (2,847)
stac_m3n4o5p6      stac_agent      data    Sentinel-2 pre/post items (15)
raster_q7r8s9t0    raster_ops_agent layer  dNBR raster + severe polygons
vec_u1v2w3x4       postgis_agent   layer   At-risk hospitals (2 features)
```

Agents access previous responses using the `get_available_responses` tool:

```python
# Example: STAC agent checking for available AOI
available = get_available_responses(source_filter=["postgis_agent", "osm_agent"])
# Returns: [{"id": "vec_a1b2c3d4", "type": "layer", "has_geometry": true, ...}]
```

---

## Architectural Patterns Demonstrated

This workflow showcases several key GeoFaham architectural patterns:

### 1. Spatial Constraint Routing
The orchestrator identified that the disaster exists in the database (`database_extent` mode) and routed the initial AOI query to the Vector Agent.

### 2. Placeholder-Based Query Composition
Step 6 used `{{GEOJSON_*}}` placeholders in the SQL query, which were resolved at runtime by referencing previous response IDs.

### 3. Coverage Validation & Fallback
The STAC Agent validated 80% AOI coverage for all imagery dates before returning results.

### 4. Tool Reflection
If the Raster Ops Agent's code had failed, it would automatically retry with error feedback up to 3 times.

### 5. Standardized Response Format
All agents returned `GeoFahamToolResponse` objects with consistent structure, enabling seamless cross-agent data sharing.

---

## Summary

This example demonstrates how GeoFaham's multi-agent architecture enables complex geospatial reasoning by:

1. **Decomposing** a complex query into specialized steps
2. **Delegating** each step to the most capable agent
3. **Sharing data** via the Response Store using `response_id` references
4. **Validating** each step before proceeding
5. **Synthesizing** outputs into a coherent answer

The combination of structured orchestration, specialized agents, and standardized data formats enables answering questions that would otherwise require significant GIS expertise and manual tool orchestration.
