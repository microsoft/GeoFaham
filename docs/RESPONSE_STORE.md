# Response Store: Cross-Agent Communication Architecture

## Overview

The Response Store (`agents/core/response_store.py`) is a **shared memory mechanism** that enables stateful cross-agent communication in the GeoFaham multi-agent system.

> **Research Perspective**: The Response Store enables stateful cross-agent communication by providing a shared memory where agents can reference outputs from previous agents via unique IDs—solving the challenge of passing complex geospatial artifacts (files, metadata, schemas) between autonomous agents without explicit parameter passing.

---

## Problems Solved

### Problem 1: Metadata Preservation (Orchestrator Bottleneck)

In a multi-agent architecture, sub-agents are **not directly connected**—they only communicate through the orchestrator. This creates a bottleneck:

```
Without Response Store:
┌─────────────┐                          ┌─────────────┐
│ STAC Agent  │ ──(full response)──────▶ │ Orchestrator│
│             │   50+ fields per item    │             │
│ bands, CRS, │   temporal ranges        │ summarizes  │
│ cloud cover │   property schemas       │ to fit      │
└─────────────┘                          │ context     │
                                         └──────┬──────┘
                                                │
                                    "found 10 images"
                                       (metadata lost!)
                                                │
                                         ┌──────▼──────┐
                                         │Raster Agent │
                                         │ needs bands,│
                                         │ CRS, dates! │
                                         └─────────────┘
```

**The Problem:**
- Orchestrator has limited context window
- When summarizing responses, **rich metadata gets lost**
- STAC responses contain: band names, CRS, resolution, cloud cover, temporal ranges, asset URLs
- Orchestrator might only pass: "found 10 Sentinel-2 images"
- Raster agent **cannot process** without the full metadata

**The Solution:**
```
With Response Store:
┌─────────────┐                          ┌─────────────┐
│ STAC Agent  │ ──(summary only)───────▶ │ Orchestrator│
│             │   "found 10 images,      │             │
│ writes full │    response_id=stac_abc" │ passes ID   │
│ response    │                          └──────┬──────┘
└──────┬──────┘                                 │
       │                              "process stac_abc"
       │ store(full_response)                   │
       ▼                                 ┌──────▼──────┐
┌─────────────────────────┐              │Raster Agent │
│     RESPONSE STORE      │◀─────────────│ get(stac_abc)│
│ • Full metadata         │  fetch by ID │ has ALL data│
│ • Zero loss             │              └─────────────┘
└─────────────────────────┘
```

Agents write full `GeoFahamToolResponse` objects to the store. Downstream agents fetch by `response_id` with **zero metadata loss**.

---

### Problem 2: Shared Working Memory (Agent Autonomy)

Without shared memory, agents are **completely dependent** on the orchestrator for context:

**The Problem:**
- Orchestrator may forget earlier responses (context window limits)
- Agents must ask "what files are available?" → extra round-trips
- Orchestrator becomes single point of failure for information
- Complex workflows require orchestrator to track all intermediate outputs

**The Solution:**

Agents can **self-serve** by querying the Response Store directly:

```python
# Any agent can call this tool to see all prior outputs
async def get_available_responses(filter_errors: bool = True) -> str:
    """
    Get all available responses from other agents in the current session.
    
    Use this when you need data or artifacts from previous agent responses
    that were not explicitly passed in your instruction.
    """
```

**Benefits:**
- Agents discover relevant data **themselves** before asking orchestrator
- Reduces orchestrator cognitive load
- Enables **emergent collaboration** between agents
- Fault tolerance: if orchestrator forgets, agents can still find data

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                             │
│  • Coordinates agent execution                               │
│  • Passes response_ids (not full data)                       │
│  • Limited context window                                    │
└─────────────────┬───────────────────────┬───────────────────┘
                  │                       │
       ┌──────────▼──────────┐ ┌──────────▼──────────┐
       │    STAC Agent       │ │   Raster Agent      │
       │  store(response)    │ │  get(response_id)   │
       └──────────┬──────────┘ └──────────┬──────────┘
                  │                       │
                  ▼                       ▼
       ┌─────────────────────────────────────────────┐
       │              RESPONSE STORE                  │
       │                                              │
       │  • Full GeoFahamToolResponse objects        │
       │  • All metadata preserved                    │
       │  • File-backed (JSONL) for persistence      │
       │  • Queryable by ID, source, data_type       │
       │  • Agents self-serve via tools              │
       └─────────────────────────────────────────────┘
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Full Response Storage** | Stores complete `GeoFahamToolResponse` objects, not summaries |
| **File-Backed Persistence** | JSONL format survives crashes and enables session recovery |
| **ID-Based Retrieval** | Agents reference data by `response_id` (e.g., `stac_abc123`) |
| **Query by Source** | Get all responses from a specific agent |
| **Query by Data Type** | Get all raster, vector, or STAC responses |
| **Self-Service Tool** | `get_available_responses()` tool for agent autonomy |
| **Thread-Safe** | Append-only writes for concurrent access |

---

## Usage Examples

### Agent Storing a Response

```python
from agents.core.response_store import get_response_store
from agents.core.types import GeoFahamToolResponse

# After tool execution
response = GeoFahamToolResponse(
    response_id="stac_abc123",
    source="stac_agent",
    type="data",
    data_type="stac_items",
    data=[...],  # Full STAC items with all metadata
    summary="Found 10 Sentinel-2 images",
    artifact=artifact,
    metadata={
        "collections": ["sentinel-2-l2a"],
        "date_range": ("2023-08-01", "2023-08-15"),
        "cloud_cover_max": 20
    }
)

store = get_response_store()
store.store(response)
```

### Agent Retrieving a Response

```python
from agents.core.response_store import get_response_store

store = get_response_store()

# Orchestrator told us to use response_id "stac_abc123"
response = store.get("stac_abc123")

# Now we have FULL metadata
print(response.metadata["date_range"])  # ('2023-08-01', '2023-08-15')
print(response.artifact.path)           # /runtime/artifacts/stac_results.geojson
```

### Agent Self-Discovering Available Data

```python
# Raster agent doesn't know what's available
# Instead of asking orchestrator, it queries the store directly

result = await get_available_responses()
# Returns all prior responses with full metadata

# Agent can now decide which data to use
```

---

## Data Flow Example

**Workflow**: Generate burn severity map from Sentinel-2 imagery

```
Step 1: Vector Agent
├── Query: "Get AOI for Lahaina fire"
├── Output: GeoJSON polygon
└── Store: response_id="vec_001" (full artifact metadata)

Step 2: STAC Agent  
├── Input: "Search pre/post fire imagery for vec_001"
├── Fetches vec_001 from store → gets exact bounds
├── Output: STAC items with all bands, dates, URLs
└── Store: response_id="stac_002" (50+ fields preserved)

Step 3: Raster Agent
├── Input: "Compute NBR difference using stac_002"
├── Fetches stac_002 from store → gets band names, CRS, resolution
├── Processes with full metadata (no guessing!)
└── Store: response_id="raster_003"
```

**Without Response Store**: Orchestrator would need to pass all STAC metadata in the prompt → context overflow or metadata loss.

**With Response Store**: Orchestrator passes `"use stac_002"` → Raster agent fetches complete data.

---

## API Reference

### ResponseStore Class

```python
class ResponseStore:
    def store(response: GeoFahamToolResponse, step_number: int = None) -> str
    def get(response_id: str) -> GeoFahamToolResponse
    def get_or_none(response_id: str) -> Optional[GeoFahamToolResponse]
    def get_all() -> List[GeoFahamToolResponse]
    def get_by_source(source_agent: str) -> List[GeoFahamToolResponse]
    def get_by_data_type(data_type: str) -> List[GeoFahamToolResponse]
    def clear() -> None
```

### Global Functions

```python
# Get singleton store instance
get_response_store() -> ResponseStore

# Reset store (new session)
reset_response_store() -> None

# Tool for agents to discover available data
get_available_responses(filter_errors: bool = True) -> str

# Resolve IDs to file paths (for tools needing geojson_path)
resolve_response_ids(response_ids: List[str]) -> tuple[List[str], Dict]
```

---

## Design Decisions

### Why File-Backed (JSONL)?

1. **Persistence**: Survives agent crashes, enables session recovery
2. **Append-Only**: Thread-safe, no locking needed
3. **Human-Readable**: Easy to debug and inspect
4. **Streaming**: Can process large histories without loading all into memory

### Why ID-Based References?

1. **Decoupling**: Agents don't need to know file paths
2. **Indirection**: Artifacts can be moved/renamed without breaking references
3. **Metadata Access**: ID gives access to full response, not just file
4. **Orchestrator Simplicity**: Pass short IDs instead of long paths + metadata

### Why Agent Self-Service?

1. **Reduces Orchestrator Load**: Agents handle their own data discovery
2. **Fault Tolerance**: Works even if orchestrator forgets
3. **Emergent Behavior**: Agents can find relevant data not explicitly mentioned
4. **Simpler Prompts**: "Process available STAC data" instead of listing everything

---

## Related Documentation

- [TOOL_RESPONSE_SCHEMAS.md](TOOL_RESPONSE_SCHEMAS.md) - Response format specification
- [AGENTS_DOCUMENTATION.md](AGENTS_DOCUMENTATION.md) - Agent architecture overview
