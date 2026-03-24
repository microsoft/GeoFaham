# Context-Efficient Data Sharing: Artifacts & Placeholders

This document explains two complementary design patterns in GeoFaham that enable efficient multi-agent collaboration while keeping LLM context clean and focused.

---

## The Core Problem

Geospatial workflows involve **large, complex data**:
- GeoJSON files: 10KB to 100MB+ (thousands of features)
- Raster files: 100MB to several GB
- Property schemas: dozens of columns with varying types

**Challenge**: How do agents share this data without:
1. Exceeding LLM token limits
2. Degrading reasoning quality with noise
3. Losing critical metadata needed for downstream processing

---

## Solution 1: Artifact Metadata Sharing

### Approach

Instead of passing raw data, we share:
1. **File path** → Pointer to actual data
2. **Property keys** → Column names and types by geometry
3. **Statistics** → Feature counts, geometry types, bounds
4. **Metadata** → CRS, temporal range, resolution

```python
artifact = SavedArtifact(
    path="/runtime/artifacts/buildings.geojson",
    features_count=15420,
    geom_types=["Polygon", "MultiPolygon"],
    property_keys={
        "polygons": {
            "building_id": {"type": "int", "fill_pct": 100},
            "height_m": {"type": "float", "fill_pct": 78},
            "building_type": {"type": "str", "fill_pct": 92},
            "damage_level": {"type": "str", "fill_pct": 45}
        }
    },
    stats={
        "total_area_km2": 12.5,
        "bounds": [-156.68, 20.87, -156.65, 20.89]
    }
)
```

### Why This Works

| What We Share | Size | What It Enables |
|--------------|------|-----------------|
| File path | ~50 chars | Data access without transfer |
| Property keys | ~200 chars | SQL column names, filtering options |
| Statistics | ~100 chars | Validation, planning decisions |
| Metadata | ~150 chars | CRS matching, temporal alignment |
| **Total** | **~500 chars** | Full context for decision-making |

vs. Raw GeoJSON: **500KB - 100MB** (1000x - 200,000x larger)

### Research Insight

> **Artifact metadata provides sufficient semantic context for LLM reasoning without the noise of raw data.** Property keys tell the agent *what* data exists; statistics tell *how much*; metadata tells *where/when*. This separation enables agents to plan operations on arbitrarily large datasets while keeping prompts under token limits.

---

## Solution 2: Placeholder-Based Query Generation

### The Problem

Vector Agent needs to query PostGIS with user-uploaded or agent-generated GeoJSON files. The LLM must write SQL that:
- References correct column names
- Uses proper geometry functions
- Joins with the temporary GeoJSON table

**Naive approach**: Send raw GeoJSON to LLM → token explosion, hallucinated columns

### The Solution: Placeholders

LLM generates SQL **templates** with placeholders:

```sql
-- LLM writes this (no raw data needed)
SELECT 
    b.building_id,
    b.building_type,
    b.damage_level,
    ST_Area(b.geometry) as area_m2
FROM {geojson_path} AS b
WHERE b.damage_level IN ('destroyed', 'major')
  AND ST_Intersects(b.geometry, ST_MakeEnvelope(-156.68, 20.87, -156.65, 20.89, 4326))
```

**At runtime**, the executor:
1. Loads GeoJSON into temporary PostGIS table
2. Replaces `{geojson_path}` with actual table name
3. Executes the resolved query

### How Property Keys Enable This

The LLM receives property keys in its context:

```
Available columns for buildings.geojson:
- building_id (int): Unique identifier
- height_m (float): Building height in meters  
- building_type (str): residential, commercial, industrial
- damage_level (str): none, minor, major, destroyed
```

**This is enough for the LLM to:**
- Know valid column names (no hallucination)
- Understand data types (correct comparisons)
- Write meaningful WHERE clauses

### The Complementary Design

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM CONTEXT                               │
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │ Property Keys   │    │ Placeholders    │                 │
│  │                 │    │                 │                 │
│  │ • column names  │    │ {geojson_path}  │                 │
│  │ • data types    │    │ {bounds}        │                 │
│  │ • fill percent  │    │ {date_range}    │                 │
│  └────────┬────────┘    └────────┬────────┘                 │
│           │                      │                          │
│           ▼                      ▼                          │
│  ┌─────────────────────────────────────────┐                │
│  │         LLM Query Generation            │                │
│  │                                          │                │
│  │  "Write SQL to find damaged buildings"  │                │
│  │                                          │                │
│  │  Output: SELECT damage_level, COUNT(*)  │                │
│  │          FROM {geojson_path}            │                │
│  │          GROUP BY damage_level          │                │
│  └─────────────────────────────────────────┘                │
│                                                              │
│  Context size: ~1KB (property keys + query)                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    RUNTIME EXECUTOR                          │
│                                                              │
│  1. Load GeoJSON → temp_table_abc123                        │
│  2. Replace {geojson_path} → temp_table_abc123              │
│  3. Execute resolved SQL                                     │
│  4. Return results                                           │
│                                                              │
│  Data size: 50MB GeoJSON (never enters LLM context)         │
└─────────────────────────────────────────────────────────────┘
```

### Research Insight

> **Placeholders separate query planning (LLM's job) from data binding (system's job).** The LLM focuses on *what* to compute using semantic hints (property keys), while the executor handles *how* to access data. This division reduces hallucination risk, enables the same query pattern to work with any input file, and keeps context focused on reasoning rather than raw data.

---

## Combined Benefits

| Benefit | Artifact Metadata | Placeholders | Combined Effect |
|---------|------------------|--------------|-----------------|
| **Token Efficiency** | 500 chars vs 50MB | Query template vs data dump | 99.99% context reduction |
| **Hallucination Reduction** | Real column names | No fabricated paths | Grounded in actual schema |
| **Scalability** | Works with any file size | Same pattern any data | No architectural limits |
| **Separation of Concerns** | What data exists | How to reference it | Clean LLM ↔ System boundary |
| **Reusability** | Metadata travels with artifact | Templates work across files | Composable workflows |

---

## Practical Example

**User Query**: "How many buildings were destroyed in the Lahaina fire?"

### Without These Patterns (Problematic)

```
LLM Context:
- Full GeoJSON: 15,420 features × 20 properties = ~50MB
- Token count: ~10 million tokens (impossible)
- Result: Context overflow or massive truncation
```

### With These Patterns (Efficient)

```
LLM Context (~800 tokens):
┌────────────────────────────────────────────────────┐
│ Available data:                                     │
│ • buildings.geojson (15,420 features)              │
│   - building_id (int)                              │
│   - damage_level (str): none, minor, major, destroyed │
│   - geometry (Polygon)                             │
│                                                     │
│ Use {geojson_path} placeholder for file reference  │
└────────────────────────────────────────────────────┘

LLM Output:
SELECT damage_level, COUNT(*) as count
FROM {geojson_path}
WHERE damage_level = 'destroyed'
GROUP BY damage_level

Executor resolves → runs on 50MB file → returns "1,827 destroyed"
```

---

## Key Takeaways

1. **Metadata is sufficient for reasoning** — LLMs don't need raw data to write correct queries; they need schema information.

2. **Pointers beat payloads** — File paths + metadata provide full context at 0.001% of the data size.

3. **Separation enables scale** — Query planning and data access are independent; either can scale without affecting the other.

4. **Property keys are the bridge** — They translate raw data schemas into LLM-friendly context, enabling grounded query generation.

5. **Placeholders maintain correctness** — LLM writes syntactically valid templates; runtime binds actual values without re-prompting.

---

## Related Documentation

- [RESPONSE_STORE.md](RESPONSE_STORE.md) - How responses and artifacts are stored
- [TOOL_RESPONSE_SCHEMAS.md](TOOL_RESPONSE_SCHEMAS.md) - Artifact schema specification
- [AGENTS_DOCUMENTATION.md](AGENTS_DOCUMENTATION.md) - Vector agent query workflow
