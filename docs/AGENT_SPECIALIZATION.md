# Agent Specialization: Why Multiple Domain Experts Beat One Generalist

This document explains the architectural decision to use **specialized agents** rather than a single general-purpose geospatial agent.

---

## The Design Question

When building a multi-agent geospatial system, a fundamental choice emerges:

**Option A: Single Generalist Agent**
- One agent with all tools (PostGIS, STAC, OSM, raster processing)
- Single massive prompt with all capabilities
- LLM handles all domain reasoning

**Option B: Multiple Specialist Agents**
- Separate agents for vector, STAC, maps, raster operations
- Each has focused toolset and domain-specific prompts
- Orchestrator coordinates between specialists

**GeoFaham uses Option B.** Here's why.

---

## The Four Specialists

| Agent | Domain | Tools | Complexity |
|-------|--------|-------|------------|
| **Vector Agent** | PostGIS/Database | SQL generation, spatial queries | Medium |
| **STAC Agent** | Satellite Imagery | Collection search, temporal filtering | Medium |
| **Maps Agent** | OpenStreetMap | Feature extraction, geocoding | Low |
| **Raster Agent** | Image Processing | Code generation, band math | High |

---

## Why Specialization Works Better

### 1. Reduced Prompt Complexity

**Generalist approach:**
```
You are a geospatial expert. You can:
- Query PostGIS databases with SQL
- Search STAC catalogs for satellite imagery
- Extract OSM features (roads, buildings, POIs...)
- Process rasters (NDVI, burn severity, cloud masking...)
- Handle 50+ different tools...

[5000+ tokens of instructions]
```

**Specialist approach:**
```
You are the STAC Agent. You search satellite imagery catalogs.
Available collections: Sentinel-2, Landsat, NAIP...
Your tools: search_stac, get_collection_details...

[800 tokens of focused instructions]
```

> **Research Insight**: Smaller, focused prompts reduce cognitive load on the LLM, leading to more accurate tool selection and parameter generation. The specialist doesn't need to "remember" irrelevant capabilities.

### 2. Domain-Specific Reasoning

Each domain has unique reasoning patterns:

| Agent | Reasoning Pattern |
|-------|------------------|
| **Vector** | SQL optimization, spatial joins, index usage |
| **STAC** | Temporal windows, cloud cover thresholds, collection selection |
| **Maps** | OSM tag hierarchies, feature categories, geocoding fallbacks |
| **Raster** | Band math, nodata handling, CRS transformations |

A generalist must context-switch between these patterns. Specialists stay in their domain.

### 3. Tiered Model Assignment

Not all tasks need the same reasoning power:

```python
# From agents/core/config.py
DEFAULT_MODEL_MAPPING = {
    "VECTOR_AGENT": "gpt-4o",      # SQL is well-defined
    "MAPS_AGENT": "gpt-4o",        # OSM queries are structured
    "STAC_AGENT": "gpt-4o",        # Catalog search is bounded
    "RASTER_AGENT": "gpt-5.1",     # Code generation needs reasoning
    "ORCHESTRATOR": "gpt-5.1",     # Planning needs high capability
}
```

> **Research Insight**: Specialization enables **cost-performance optimization**—simple agents use cheaper models, complex agents use powerful ones. A generalist would need the most powerful model for everything.

### 4. Isolated Failure Domains

When something fails:

**Generalist**: Entire system capability affected
**Specialist**: Only one domain affected; others continue working

```
STAC API is down:
├── Generalist: "I cannot help with any geospatial tasks" (confused)
└── Specialist: STAC agent fails gracefully, Vector/Maps still work
```

### 5. Toolset Scoping

Each agent sees only relevant tools:

```python
# Vector Agent tools
tools = [execute_query, execute_query_with_geojson]

# STAC Agent tools  
tools = [search_stac, get_collection_details, get_population_data]

# Maps Agent tools
tools = [get_roads, get_buildings, get_admin_boundary, ...]

# Raster Agent tools
tools = [execute_custom_raster_code]
```

> **Research Insight**: Smaller tool sets reduce selection errors. A generalist with 50 tools might pick the wrong one; a specialist with 5 tools has higher precision.

---

## The Orchestrator's Role

Specialization requires coordination:

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                             │
│                                                              │
│  • Decomposes user query into sub-tasks                     │
│  • Assigns each sub-task to appropriate specialist          │
│  • Manages data flow between agents (via Response Store)    │
│  • Synthesizes final response                               │
└─────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  Vector  │    │   STAC   │    │  Raster  │
    │  Agent   │    │  Agent   │    │  Agent   │
    │          │    │          │    │          │
    │ PostGIS  │    │ Imagery  │    │ Processing│
    └──────────┘    └──────────┘    └──────────┘
```

**Example decomposition:**
```
User: "Show me damaged buildings from the Lahaina fire"

Orchestrator plan:
1. Vector Agent → Get fire AOI from disaster database
2. STAC Agent → Search pre/post fire Sentinel-2 imagery
3. Raster Agent → Compute burn severity index
4. Vector Agent → Join buildings with burn severity
```

---

## Trade-offs

| Aspect | Generalist | Specialist |
|--------|------------|------------|
| **Prompt size** | Large (all capabilities) | Small (focused) |
| **Tool selection** | Error-prone (many options) | Precise (few options) |
| **Model cost** | High (always needs best model) | Optimized (tiered) |
| **Failure isolation** | Poor (all-or-nothing) | Good (independent) |
| **Coordination overhead** | None | Requires orchestrator |
| **Emergent behavior** | Higher (can combine freely) | Lower (bounded by design) |

---

## Key Takeaways

1. **Cognitive load matters** — LLMs perform better with focused instructions than encyclopedic prompts.

2. **Domain expertise enables precision** — Each specialist has deep knowledge of its domain's patterns and edge cases.

3. **Cost optimization is architectural** — Model tiering is only possible with specialization.

4. **Orchestration is the glue** — The value of specialists depends on effective coordination.

5. **Bounded complexity scales** — Adding a new domain means adding a new agent, not expanding a monolithic prompt.

---

## Related Documentation

- [AGENTS_DOCUMENTATION.md](AGENTS_DOCUMENTATION.md) - Detailed agent specifications
- [RESPONSE_STORE.md](RESPONSE_STORE.md) - How agents share data
- [RASTER_CODE_GENERATION.md](RASTER_CODE_GENERATION.md) - Why raster agent generates code
