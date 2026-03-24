# GeoFaham Benchmark Annotation Methodology

This document describes the benchmark annotation process used to create ground truth (GT) data for evaluating multi-agent geospatial systems. The methodology is designed for evaluating orchestration quality, agent execution correctness, and end-to-end task completion in complex, multi-step geospatial workflows.

## 1. Overview

Traditional benchmarks for LLM evaluation often rely on rigid, single-answer ground truths. However, multi-agent orchestration systems present unique challenges:

1. **Multiple valid execution paths**: Different agent sequences may achieve the same result
2. **Dynamic intermediate outputs**: Statistics and feature counts may vary slightly between runs
3. **Semantic correctness vs. exact match**: Instructions and code can be correct without being identical

Our annotation methodology addresses these challenges through a **human-validated, LLM-extracted, non-rigid ground truth** approach.

## 2. Annotation Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ANNOTATION PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  Oracle Run  │───▶│   Human      │───▶│  Validated   │              │
│  │  (GPT-5.1)   │    │  Validation  │    │    Runs      │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                                       │                       │
│         │              Multiple                 │                       │
│         └──────────── Runs (n≥5) ──────────────┘                       │
│                                                 │                       │
│                                                 ▼                       │
│                                    ┌──────────────────┐                │
│                                    │  LLM Extraction  │                │
│                                    │    (GPT-5.1)     │                │
│                                    └────────┬─────────┘                │
│                                             │                          │
│                                             ▼                          │
│                                    ┌──────────────────┐                │
│                                    │  Structured GT   │                │
│                                    │  (Non-Rigid)     │                │
│                                    └──────────────────┘                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Phase 1: Oracle Execution

We execute benchmark questions using GPT-5.1 (the most capable model available) for **all agents** in the system:

| Component | Model |
|-----------|-------|
| Orchestrator Planner | GPT-5.1 |
| Orchestrator Progress Tracker | GPT-5.1 |
| PostGIS Agent | GPT-5.1 |
| Maps Agent | GPT-5.1 |
| STAC Agent | GPT-5.1 |
| Raster Ops Agent | GPT-5.1 |

This "oracle configuration" establishes an upper bound on system performance and ensures high-quality reference executions.

**Multiple Runs**: Each question is executed 2-3 times to capture natural variation in:
- Agent execution order (when dependencies allow flexibility)
- SQL query formulation (different but equivalent queries)
- Parameter choices (e.g., clustering thresholds, date ranges)
- Intermediate statistics (feature counts, areas)

### 2.2 Phase 2: Human Validation

A domain expert reviews each run against the following evaluation dimensions:

#### Orchestration Quality
- **Spatial Constraint Mode**: Is the correct mode selected?
  - `database_extent`: Query references disaster by type/date → use stored AOI
  - `fetch_boundary`: Query mentions sub-area → fetch boundary first
  - `user_provided_aoi`: User uploaded geometry → use that
- **Agent Sequence**: Is the sequence logically correct with proper dependencies?
- **Instruction Quality**: Are instructions semantic (high-level) rather than implementation-specific (no SQL/code)?
- **Artifact Flow**: Are previous outputs correctly referenced in subsequent steps?

#### Agent Execution Correctness
- **Tool Selection**: Did each agent select the appropriate tool for the task?
- **Parameter Correctness**: Are critical parameters correct?
  - PostGIS: Correct disaster_id, proper GeoJSON placeholders, damage status CASE statement
  - Maps Agent: Full place name hierarchy, correct category enums
  - STAC Agent: Appropriate collection for task, correct date ranges for disaster
  - Raster Ops: Proper code structure, CRS preservation, result variable assignment
- **Query Optimization**: Are queries efficient (e.g., avoiding `ST_Union` on large tables)?

#### Result Quality
- **Output Type**: Correct format (vector/raster/statistics/mixed)?
- **Completeness**: Does the result answer the user's question?
- **Statistics**: Are computed statistics reasonable?

**Validation Outcome**: Runs that pass all validation criteria are saved to the benchmark ground truth repository.

### 2.3 Phase 3: Automated GT Extraction

Validated runs are processed by an LLM (GPT-5.1) to extract structured ground truth. The extraction prompt includes:

1. **System Architecture Documentation**: Agent roles, tools, capabilities
2. **Evaluation Dimensions**: What aspects to extract for each dimension
3. **Output JSON Schema**: Precise structure for the GT document
4. **Agent Capabilities Reference**: Loaded dynamically from the actual system source code

#### Key Extraction Principle: Non-Rigid Ground Truth

Since multiple validated runs exist, the LLM identifies:

| Category | Description | Example |
|----------|-------------|---------|
| **Invariants** | Must be identical across all correct runs | `disaster_id = 2`, agent sequence `[maps, postgis]` |
| **Acceptable Variations** | Can differ but still be correct | Road category `MAJOR` vs `ALL`, exact feature counts |
| **Quality Indicators** | Distinguish better runs from acceptable ones | Completeness of final answer, efficiency of queries |

## 3. Ground Truth Schema

The extracted GT follows a comprehensive schema designed for automated evaluation:

```json
{
  "question_id": "Q009",
  "question_text": "...",
  "runs_analyzed": ["run_1", "run_2", "run_3"],
  
  "orchestration_gt": {
    "spatial_mode": "fetch_boundary",
    "spatial_mode_reasoning": "...",
    "expected_agent_sequence": ["osm_map_agent", "postgis_agent"],
    "acceptable_sequence_variations": [...],
    "plan_invariants": {
      "must_fetch_boundary": true,
      "must_query_damage": true,
      "must_use_spatial_join": true
    },
    "plan_reasoning": {
      "why_this_sequence": "...",
      "why_not_alternatives": "..."
    },
    "instruction_quality_gt": {
      "step_1": {
        "target_agent": "osm_map_agent",
        "instruction_must_contain": ["boundary", "neighborhood"],
        "instruction_must_NOT_contain": ["SQL", "coordinates"],
        "should_pass_inputs": false
      }
    }
  },
  
  "agent_execution_gt": {
    "postgis_agent": {
      "was_used": true,
      "invocations": [{
        "purpose": "Find damaged buildings in AOI",
        "tool_name": "execute_query_with_geojson",
        "sql_required_elements": ["{{GEOJSON_POLYGONS_CTE}}", "damage_status"],
        "sql_forbidden_elements": ["INSERT", "UPDATE"],
        "expected_output_results": {
          "feature_count_range": [100, 150],
          "required_properties": ["damage_status", "damage_pct"]
        }
      }]
    },
    "stac_agent": {
      "collection_selection": {
        "selected": "sentinel-1-grd",
        "correct_alternatives": ["sentinel-1-rtc"],
        "incorrect_alternatives": ["sentinel-2-l2a"],
        "selection_reasoning": "SAR for flood detection under cloud cover"
      },
      "date_logic": {
        "event_date": "2025-05-16",
        "daterange1_purpose": "during-event flood extent"
      }
    }
  },
  
  "result_gt": {
    "output_type": "vector",
    "evaluation_mode": "statistical",
    "structural_checks": {
      "required_properties": ["damage_status"],
      "geometry_type": "Polygon"
    },
    "statistical_checks": {
      "expected_stats": {
        "total_buildings": {"consensus_range": [100, 150]}
      },
      "tolerance_percent": 10
    }
  },
  
  "cross_run_analysis": {
    "runs_succeeded": ["run_1", "run_2", "run_3"],
    "consistency_notes": "...",
    "best_run": "run_2",
    "best_run_reason": "..."
  }
}
```

## 4. Evaluation Dimensions

### 4.1 Orchestration Evaluation

| Metric | Description | Measurement |
|--------|-------------|-------------|
| Spatial Mode Accuracy | Correct constraint mode selected | Exact match |
| Agent Sequence Correctness | Valid execution path | Match to expected or acceptable variations |
| Plan Completeness | All necessary steps included | Boolean per required step |
| Instruction Semantics | High-level, not implementation-specific | Keyword presence/absence checks |
| Artifact Flow | Correct references to previous outputs | Response ID validation |

### 4.2 Agent Execution Evaluation

| Agent | Key Metrics |
|-------|-------------|
| **PostGIS** | SQL required elements, forbidden elements, disaster_id correctness, GeoJSON placeholder usage, query optimization |
| **Maps** | Tool selection, place name format, category enum correctness, feature type appropriateness |
| **STAC** | Collection selection (with reasoning), date range logic, mode selection (fetch vs show) |
| **Raster Ops** | Code structure, CRS preservation, output type correctness, statistics extraction |

### 4.3 Result Evaluation

| Mode | When Used | Checks |
|------|-----------|--------|
| **Structural** | Schema validation | Required properties exist, geometry types correct |
| **Statistical** | Quantitative comparison | Counts/values within tolerance ranges |
| **Semantic** | Qualitative assessment | Answer addresses user question, actionable information provided |

## 5. Design Rationale

### 5.1 Why Non-Rigid Ground Truth?

Multi-agent systems exhibit legitimate variation:

1. **SQL Equivalence**: `WHERE damage_pct > 0.5` and `WHERE damage_pct >= 0.5001` may both be correct interpretations
2. **Temporal Sensitivity**: Feature counts change as OSM data updates
3. **Stochastic Elements**: LLM sampling introduces variation even with low temperature
4. **Multiple Valid Approaches**: Buffer-then-intersect vs. ST_DWithin are both valid for proximity queries

Rigid GT would incorrectly penalize valid alternative approaches.

### 5.2 Why Human-in-the-Loop?

Fully automated GT generation risks:
- Encoding model-specific biases as ground truth
- Missing domain-specific correctness criteria
- Accepting plausible but incorrect reasoning

Human validation ensures domain correctness while LLM extraction provides scalable structuring.

### 5.3 Why Multiple Runs?

Multiple runs enable:
- Identification of true invariants (consistent across runs) vs. incidental choices
- Statistical range estimation for counts and metrics
- Detection of edge cases and failure modes
- Confidence assessment for the GT itself

## 6. Benchmark Categories

Questions are organized by category to enable targeted evaluation:

| Category | Sub-categories | Example Questions |
|----------|---------------|-------------------|
| Building Damage | By neighborhood, by severity, clustering | "Show damaged buildings in Central West End" |
| Flood Analysis | Extent mapping, infrastructure impact | "Find roads intersecting flood zones" |
| Infrastructure | POI proximity, accessibility | "Hospitals within 5km of damage hotspots" |
| Satellite Imagery | Change detection, indices | "Calculate NDVI change before/after tornado" |
| Multi-step | Complex workflows | "Find flooded cropland area and estimate affected population" |

## 7. Quality Assurance

### 7.1 GT Confidence Levels

Each GT is assigned a confidence level:

| Level | Criteria |
|-------|----------|
| **High** | 3+ consistent runs, clear invariants, no ambiguous cases |
| **Medium** | 2 consistent runs, minor variations in acceptable ranges |
| **Low** | Single run or significant variation, requires manual review during evaluation |

### 7.2 Common Failure Modes

The GT documents expected failure modes for each question:

```json
"common_failure_modes": [
  "Using wrong disaster_id",
  "Forgetting spatial join with AOI",
  "ST_Union on large flood_maps table (performance)",
  "Missing damage_status CASE statement"
]
```

These guide both GT validation and evaluation debugging.

## 8. Usage in Evaluation

The structured GT enables automated evaluation across model configurations:

```bash
# Run benchmark with specific LLM config
python run_benchmark_eval_v2.py --with-gt --config all-gpt4o

# Compare against ground truth
python evaluate_against_gt.py --config all-gpt4o --output results/
```

Evaluation metrics are computed per dimension and aggregated:
- **Orchestration Score**: % of plan invariants satisfied
- **Execution Score**: % of agent invocations with correct tools/params
- **Result Score**: Structural/statistical/semantic checks passed
- **Overall Score**: Weighted combination based on question complexity

## 9. Limitations

1. **Oracle Dependency**: GT quality bounded by GPT-5.1 capabilities
2. **Domain Expertise**: Human validation requires geospatial domain knowledge
3. **Temporal Validity**: GT may become stale as underlying data (OSM, disaster DB) updates
4. **Coverage**: Not all edge cases may be captured in 2-3 runs

## 10. Future Work

- **Automated GT Refresh**: Periodic re-validation with updated data sources
- **Difficulty Calibration**: Empirical difficulty scores based on model performance
- **Error Taxonomy**: Systematic categorization of failure types across models
- **Human Evaluation Correlation**: Correlation studies between automated metrics and human preferences
