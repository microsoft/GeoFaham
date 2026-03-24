# Benchmark Design and Question Generation

This document describes the methodology used to design and generate the GeoFaham benchmark dataset, including disaster selection, question categories, difficulty levels, and user personas.

## Overview

The GeoFaham benchmark is designed to evaluate multi-agent geospatial AI systems on realistic disaster assessment tasks. The benchmark consists of **88 questions** across **17 real-world disasters** spanning different disaster types, geographic regions, and analytical complexity levels.

## Disaster Selection

### Criteria

Disasters were selected to ensure:

1. **Diversity of disaster types**: Tornados, hurricanes, cyclones, floods, fires, earthquakes
2. **Geographic coverage**: North America, South America, Europe, Africa, Asia, Oceania
3. **Data availability**: Either building damage assessments OR flood maps (or both)
4. **Recency**: Events from 2023-2025 with available satellite imagery

### Disaster Database Summary

| ID | Disaster Type | Location | Country | Date | Data Available |
|----|---------------|----------|---------|------|----------------|
| 1 | Tornado | Saint Louis, Missouri | USA | 2025-05-16 | Building damage (78,777 buildings) |
| 2 | Hurricane (Melissa) | Black River | Jamaica | 2025-10-29 | Building damage (107,133 buildings) |
| 3 | Hurricane (Melissa) | Montego Bay | Jamaica | 2025-10-31 | Building damage (61,161 buildings) |
| 4 | Flood | Porto Alegre | Brazil | 2024-05-09 | Building damage (88,541 buildings) |
| 5 | Cyclone (Chido) | Mamoudzou, Mayotte | France | 2024-12-18 | Building damage (6,355 buildings) |
| 6 | Flood | Valencia | Spain | 2024-10-31 | Flood map (130.19 km²) |
| 7 | Hurricane (Beryl) | Grenada | Grenada | 2024-07-02 | Building damage (3,647 buildings) |
| 8 | Cyclone (Senyar) | Aceh, North Sumatra | Indonesia | 2025-11-29 | Building damage + Flood map |
| 9 | Flood | Nairobi (Embakasi East) | Kenya | 2024-05-01 | Flood map (96.39 km²) |
| 10 | Flood | Busia (Alego Usonga) | Kenya | 2024-05-06 | Flood map (12.3 km²) |
| 11 | Fire (Eaton) | Pasadena | USA | 2025-01-10 | Building damage (156,102 buildings) |
| 12-14 | Fire (Palisades) | Los Angeles | USA | 2025-01-08-10 | Building damage (multi-day) |
| 15 | Earthquake | Mandalay | Myanmar | 2025-03-29 | Building damage (182,043 buildings) |
| 16 | Fire | Lahaina, Maui | USA | 2023-08-08 | Building damage (2,810 buildings) |
| 17 | Cyclone (Ditwah) | Colombo | Sri Lanka | 2025-11-30 | Building damage + Flood map |

### Data Extraction Pipeline

For each disaster, we extracted:

1. **AOI (Area of Interest)**: Administrative boundaries from database
2. **POI Features**: Schools, hospitals, roads, shelters from OpenStreetMap
3. **Detailed Overview**: LLM-generated summary for question grounding

See `data/benchmarks/geofaham/benchmark_data/disaster_*/` for per-disaster data.

## User Personas

Questions are designed from three distinct user perspectives to ensure practical relevance:

### 1. GIS Analyst (Technical)
- **Background**: Professional with GIS/spatial analysis expertise
- **Tasks**: Precise spatial queries, damage quantification, technical analysis
- **Language**: Comfortable with technical terms (buffers, spatial joins, damage percentages)
- **Example**: "Show damaged buildings within 1km of hospitals and calculate damage density"

### 2. Humanitarian Aid Worker (Operational)
- **Background**: Field coordinator or logistics specialist
- **Tasks**: Resource allocation, shelter planning, accessibility assessment
- **Language**: Practical, action-oriented, non-technical
- **Example**: "Which shelters can still accommodate evacuees near the flood zone?"

### 3. Government Official (Decision-Maker)
- **Background**: Policy maker, emergency manager, or city administrator
- **Tasks**: High-level summaries, priority rankings, situational awareness
- **Language**: Executive summaries, rankings, key statistics
- **Example**: "Which neighborhoods have the highest damage and need immediate attention?"

## Question Categories

Questions are organized into **11 analytical categories**:

| Category | Count | Description |
|----------|-------|-------------|
| `poi_impact_analysis` | 20 | Impact on points of interest (hospitals, schools, shelters) |
| `clustering_aggregation` | 19 | Spatial aggregation and ranking by area |
| `infrastructure` | 17 | Roads, utilities, and critical infrastructure |
| `building_damage_assessment` | 8 | Direct damage queries by location/level |
| `comparative_analysis` | 7 | Before/after or cross-disaster comparisons |
| `flood_analysis` | 5 | Flood extent and intersection queries |
| `satellite_imagery` | 5 | STAC catalog searches for imagery |
| `population_humanitarian` | 4 | Population estimates and humanitarian needs |
| `burn_intensity` | 1 | Fire-specific burn severity analysis |

### Sub-Categories

Each category has sub-categories for finer granularity:

```
building_damage_assessment/
├── damage_levels_by_neighborhood
├── damage_by_poi_proximity
└── damage_statistics

poi_impact_analysis/
├── healthcare_proximity_to_damage
├── education_facility_impact
├── shelter_availability
└── critical_infrastructure

clustering_aggregation/
├── neighborhood_damage_ranking
├── regional_comparison
└── hotspot_identification
```

## Difficulty Levels

Questions are classified into three difficulty levels based on:

1. **Number of agents required**
2. **Complexity of spatial operations**
3. **Need for multi-step reasoning**
4. **Data integration requirements**

| Difficulty | Count | Criteria |
|------------|-------|----------|
| `simple` | 6 | Single agent, straightforward query |
| `medium` | 33 | 2 agents or spatial join required |
| `hard` | 47 | 3+ agents, complex reasoning, or multi-turn |
| `High` | 2 | Most complex scenarios |

### Difficulty Examples

**Simple** (1 agent):
> "For the Saint Louis tornado on 2025-05-16, show damaged buildings in Skinker DeBaliviere and summarize counts by damage level."

**Medium** (2 agents, spatial join):
> "For the Saint Louis tornado on 2025-05-16, show hospitals and clinics in Central West End and their damage status."

**Hard** (3+ agents, complex reasoning):
> "For the Los Angeles Palisades fire, find pre-fire and post-fire satellite imagery within 2 weeks of the event, calculate NDVI difference, and identify areas with significant vegetation loss."

## Question Structure

Each question follows a standardized schema:

```json
{
  "id": "Q001",
  "persona": "GIS Analyst",
  "question": "For the Saint Louis tornado on 2025-05-16, show damaged buildings in {NEIGHBORHOOD} and summarize counts by damage level.",
  "placeholders": {
    "NEIGHBORHOOD": {
      "value": "Skinker DeBaliviere",
      "alternatives": ["DeBaliviere Place", "Baden", "The Ville"]
    }
  },
  "disaster_id": 1,
  "category": "building_damage_assessment",
  "sub_category": "damage_levels_by_neighborhood",
  "difficulty": "simple",
  "requires_geometry_input": false,
  "is_multi_turn": false,
  "follow_ups": [],
  "variants": [
    "For the Saint Louis tornado on 2025-05-16, show damaged buildings in Skinker DeBaliviere and summarize counts by damage level.",
    "For the Saint Louis tornado on 2025-05-16, show damaged buildings in DeBaliviere Place and summarize counts by damage level."
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (Q001-Q088) |
| `persona` | Target user persona |
| `question` | Template with placeholders |
| `placeholders` | Variable values with alternatives |
| `disaster_id` | Links to disaster in database |
| `category` | Analytical category |
| `sub_category` | Fine-grained classification |
| `difficulty` | simple/medium/hard |
| `requires_geometry_input` | User-drawn AOI needed? |
| `is_multi_turn` | Requires conversation context? |
| `follow_ups` | Related follow-up questions |
| `variants` | Pre-compiled question variations |

## Placeholder System

Placeholders allow question variation without changing the underlying task:

```json
"placeholders": {
  "NEIGHBORHOOD": {
    "value": "Skinker DeBaliviere",      // Default value
    "alternatives": ["Baden", "The Ville"]  // For variant generation
  },
  "TOP_N": {
    "value": 10,
    "alternatives": [5, 15]
  }
}
```

The `variants` array contains pre-compiled questions with placeholders replaced by each possible value.

## Design Principles

### 1. User-Facing Language
Questions are written as end-users would ask them—no internal system details:

✅ "Show damaged buildings in the neighborhood"
❌ "Query the building_damage_assessment table with ST_Intersects"

### 2. Grounded in Real Data
Place names and POIs come from actual database/OSM data:

```
disaster_*/overview_for_llm.txt  →  Available neighborhood names
disaster_*/features_*.json       →  Available POI types
```

### 3. Layer Availability Awareness
Questions only reference data that exists:
- Building damage only for disasters with `has_building_damage_assessment: true`
- Flood footprints only for disasters with `has_flood_map: true`

### 4. No Implementation Leakage
Questions don't reveal:
- Database schema or table names
- Agent names or tool names
- Internal response IDs

## Question Distribution

### By Disaster Type

| Type | Disasters | Questions |
|------|-----------|-----------|
| Fire | 5 | 25 |
| Flood | 4 | 23 |
| Hurricane | 3 | 18 |
| Cyclone | 3 | 19 |
| Tornado | 1 | 6 |
| Earthquake | 1 | 6 |

### By Region

| Region | Countries | Questions |
|--------|-----------|-----------|
| North America | USA | 39 |
| Caribbean | Jamaica, Grenada | 18 |
| South America | Brazil | 4 |
| Europe | Spain, France (Mayotte) | 13 |
| Africa | Kenya | 12 |
| Asia | Indonesia, Myanmar, Sri Lanka | 19 |

### By Difficulty

```
Simple:  █████░░░░░░░░░░░░░░░░░░░░░  6  (7%)
Medium:  ████████████████░░░░░░░░░░  33 (38%)
Hard:    ██████████████████████████  47 (53%)
High:    █░░░░░░░░░░░░░░░░░░░░░░░░░  2  (2%)
```

## Ground Truth Generation

For each benchmark question, ground truth is generated from expert runs:

```
benchmark_gt/
└── Q001/
    ├── ground_truth.json     # Expected orchestration and agent behavior
    ├── run_1/                # First expert run
    │   ├── conversation_history.json
    │   └── response_store.jsonl
    ├── run_2/                # Second expert run
    └── token_usage.json      # Combined token stats
```

### Ground Truth Schema

```json
{
  "question_id": "Q001",
  "orchestration_gt": {
    "spatial_mode": "fetch_boundary",
    "expected_agent_sequence": ["map_search_agent", "postgis_agent"],
    "plan_invariants": {
      "must_fetch_boundary": true,
      "must_query_damage": true,
      "must_use_spatial_join": true
    }
  },
  "agent_execution_gt": {
    "map_search_agent": {
      "tool_name": "get_admin_boundary",
      "expected_output_type": "Polygon"
    },
    "postgis_agent": {
      "tool_name": "execute_query_with_geojson",
      "expected_output_results": {
        "feature_count_range": [10, 500]
      }
    }
  },
  "final_answer_gt": {
    "expected_content": "Damage counts by level with map layer"
  }
}
```

## File Organization

```
data/benchmarks/geofaham/
├── benchmark_data/
│   ├── disasters_summary.json              # All 17 disasters with stats
│   ├── all_disasters_overview.json         # Detailed disaster info
│   ├── benchmark_questions_v2.json         # Questions with placeholders
│   ├── benchmark_questions_v2_compiled.json # Final with variants
│   └── disaster_*/                         # Per-disaster data
│       ├── aoi.geojson
│       ├── overview_for_llm.txt
│       └── features_*.json
├── benchmark_gt/                           # Ground truth per question
│   └── Q*/
├── benchmark_eval/                         # Evaluation runs
│   └── {config}/Q*/run_*/
└── eval_results/                           # LLM judge results
    └── {config}/Q*/run_*/judgement.json
```

## Adding New Questions

1. **Identify disaster**: Choose from existing 17 or add new disaster data
2. **Define question**: Write user-facing question with placeholders
3. **Classify**: Assign category, sub_category, difficulty, persona
4. **Generate variants**: Run compilation script
5. **Create ground truth**: Execute with expert model, save runs
6. **Validate**: Run LLM judge to ensure ground truth is coherent

### Example: Adding a New Question

```json
{
  "id": "Q089",
  "persona": "Humanitarian Aid Worker",
  "question": "For the {DISASTER} in {LOCATION}, which shelters can accommodate at least {MIN_CAPACITY} people and are not in the flood zone?",
  "placeholders": {
    "DISASTER": {"value": "Valencia flood"},
    "LOCATION": {"value": "Valencia, Spain"},
    "MIN_CAPACITY": {"value": 100, "alternatives": [50, 200]}
  },
  "disaster_id": 6,
  "category": "poi_impact_analysis",
  "sub_category": "shelter_availability",
  "difficulty": "hard"
}
```

## Compilation Process

The compilation script (`add_compiled_questions2benc.py`) transforms template questions into concrete variants:

```
benchmark_questions_v2.json (templates)
         ↓
    Compilation
         ↓
benchmark_questions_v2_compiled.json (88 questions with variants)
```

Each placeholder value and its alternatives produce a variant, ensuring diverse test cases while maintaining consistent task structure.
