# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Orchestrator Prompts V3 - Two-Stage Architecture
=================================================

Separates fact extraction from plan generation for:
- Cleaner logic and easier debugging
- Smaller context per LLM call
- Better artifact reuse detection
- Cheaper plan revisions (no re-extraction)

Stage 1: Extract structured facts from user query + context
Stage 2: Generate executable workflow plan from facts
"""

from typing import Dict
from agents.orchestrator_agent._agent_capabilities import AGENT_CAPABILITIES_DOC, AGENT_NAMES

# =============================================================================
# AGENT NAME PLACEHOLDERS
# =============================================================================

# Use centralized agent names from _agent_capabilities module
AGENT_PLACEHOLDERS = {
    "STAC_AGENT": AGENT_NAMES["STAC_AGENT"],
    "MAPS_AGENT": AGENT_NAMES["MAPS_AGENT"], 
    "POSTGIS_AGENT": AGENT_NAMES["VECTOR_AGENT"],
    "RASTER_AGENT": AGENT_NAMES["RASTER_AGENT"],
    "agent_capabilities": AGENT_CAPABILITIES_DOC,  # Inject detailed capabilities
}


# =============================================================================
# STAGE 1: FACT EXTRACTION PROMPT
# =============================================================================


# A shorter, stricter Stage 1 prompt (keeps extraction lightweight; planning happens in Stage 2)
ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT = """
You are a query analysis specialist. Extract structured facts from the user's request. Do not generate a plan.

**User Query:** {task}
---

## OUTPUT

Produce the fact sheet using the exact headings below. Use short bullet points. If unknown, write "Not specified". Do not invent artifacts, response IDs, disasters, dates, or places.

### 1. QUERY INTENT

**Task Type:** `visualization` | `statistics`
- Use `statistics` only if the user explicitly requests counts/percentages/tables; otherwise `visualization`.

**User Goal:**
- [1 short sentence describing what the user wants to understand or see]

**Requested Output (if stated):**
- [layer | table | comparison | timeline | Not specified]

Note: By default, assume `visualization` and expect a layer output unless user explicitly stated otherwise. Even if the user says "show me numbers" default is visualization unless explicitly stated otherwise.

---

### 2. DISASTER & TIME CONTEXT

**Disaster Mention (as written):**
- [type/name + date/year + location, exactly as user/context states, or "Not applicable"]

**Temporal Window (if any):**
- [before/after dates, ranges, or "Not specified"]

---

### 3. AREA OF INTEREST (AOI)

**Named Places:**
- [smallest → largest; or "Not applicable"]

**AOI Artifacts (reuse if relevant):**
- [file paths from ledger that represent the AOI boundary/geometry; or "Not applicable"]

**Spatial Phrases (quote from query):**
- [e.g., "in Central West End", "near Forest Park"; or "Not applicable"]

**Spatial Parameters:**
- Radius/distance: [e.g., "2km" | "Not specified"]
- Other constraints: [e.g., "within city limits" | "None"]

---

### 4. REQUIRED ENTITIES & FILTERS

**Entities to Analyze:**
- POIs: [hospitals/schools/etc | "Not applicable"]
- Features: [buildings/roads/flood zones/etc | "Not applicable"]

**Filters / Thresholds:**
- Damage criteria: ["moderate+" / "significant" / "Not specified"]
- Temporal: [before/after intent or dates | "Not specified"]
- Spatial relationship: [within/intersect/near/around | "Not specified"]

---

### 5. ARTIFACT REUSE & GAPS

**Reusable Artifacts (from ledger):**
- Response ID: ... | File: ... | Represents: ... | Created by: ...
- [or "None"]

**User-Provided Data (already saved):**
- [uploads/drawings with file paths; or "None"]

**Missing Information / Clarifications (only if plan would fail):**
- [questions that must be answered; or "None"]
"""


# =============================================================================
# STAGE 2: PLAN GENERATION PROMPT
# =============================================================================

ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT = """
You are a workflow orchestration expert. Generate an executable multi-agent plan from the provided fact sheet and team.

**Task:**
{task}

**Fact Sheet**
{facts}

**Team:**
{team}

---

{agent_capabilities}

---


## YOUR TASK

Generate a step-by-step workflow plan that:
1. Respects agent capabilities and constraints
2. Minimizes redundant data fetching (reuse artifacts when possible)
3. Establishes clear dependencies between steps
4. Provides complete, unambiguous instructions for each agent

---

## PLAN FORMAT

### STEP-BY-STEP WORKFLOW

For each step, use this structure:

```
**Step N: AGENT_NAME** (depends on: [Step X, Step Y] or "None")

**Objective:** [One sentence: what user-visible outcome this achieves]

**Task:** [Natural language instruction describing what to accomplish, in semantic terms]

**Inputs:**
- [Semantic references: disaster names, disaster dates, place names, artifact file paths]
- [User intent context: what the user is trying to understand or visualize]
- [Dependencies: outputs from previous steps using exact file paths]

**Context:** [Full semantic context - place names, disaster details, spatial relationships, user goal]
- Example: "Central West End neighborhood, Saint Louis, Missouri"
- Example: "Saint Louis tornado disaster of January 5, 2025"
- Example: "User wants to see which hospitals are inside flooded areas"

**Expected Output:** [What artifact(s) will be produced with descriptive names]

**Success Criteria:** [How to verify this step accomplished its objective]
```

---


## SPATIAL CONSTRAINT MODE (Choose ONE)

Select a single spatial constraint mode for the overall plan. This choice must be reflected in your steps and inputs.

**Mode:**

- `database_extent` — Use the disaster's stored footprint/AOI from the database
- `fetch_boundary` — Use a specific place / AOI boundary to constrain the analysis
- `user_provided_aoi` — Use a user-provided AOI geometry or boundary artifact

**Trigger Check (follow this order):**

1. **Check for user-provided AOI first:**
   - Choose `user_provided_aoi` if the fact sheet lists an AOI geometry/boundary artifact provided by the user (upload, drawn AOI, saved AOI) and it matches the query.

2. **Check if disaster is explicitly referenced:**
   - Choose `database_extent` if the query references a known disaster by its identifying metadata (type + date + location) that matches a disaster record in the database.
   - Key insight: When a user references a disaster by its metadata (e.g., "DISASTER_LOCATION DISASTER_TYPE DISASTER_DATE"), the disaster's stored AOI IS the spatial constraint. Do not fetch external boundaries unless it is lower order in administrative boundaries hierarchy.
   - Applies when: The place name in the query is the disaster's location context (where the disaster occurred), NOT an additional spatial filter.

3. **Check for place-constrained wording (additional spatial filter):**
   - Choose `fetch_boundary` ONLY if the query implies a sub-area filter WITHIN the disaster extent, such as:
     - Spatial prepositions indicating containment: "in [neighborhood]", "within [district]", "around [landmark]"
     - Nested geography indicating a sub-region: "[neighborhood], [city]" when the neighborhood is smaller than the disaster extent
     - Area qualifiers: "downtown area", "[facility] vicinity"
     - Explicit spatial parameters: "within Xkm of", "near [landmark]"
   - The key distinction: Is the place name the disaster location, or an additional sub-area filter?

4. **Default:**
   - If none of the above apply clearly, choose `database_extent`.

**Decision Output (state explicitly):**
- **Priority order:** `user_provided_aoi` → `database_extent` (if disaster explicitly referenced) → `fetch_boundary` → `database_extent` (default)
- If AOI artifact exists → `user_provided_aoi` (state the exact AOI artifact file path)
- Else if disaster is explicitly referenced by type+date+location → `database_extent` (the disaster's stored AOI is the spatial extent)
- Else if place-constrained wording implies sub-area filter → `fetch_boundary` (state the exact place/AOI string to use)
- Else → `database_extent` (default)

**Sub-Area Boundaries (important):**
When the query mentions BOTH a disaster AND a sub-area (neighborhood, district, vicinity of a place), the plan needs BOTH:
- The disaster AOI/data from database (for damage/flood assessment)
- The sub-area boundary (for filtering POIs or constraining the analysis area)

In such cases, add a step to fetch the sub-area boundary using {MAPS_AGENT} BEFORE searching for POIs or features within that sub-area. The sub-area boundary is used for POI extraction; the disaster data is used for impact assessment.

**Planning Implications (must follow):**
- If `user_provided_aoi`: do not fetch a boundary; use the AOI artifact as the spatial filter input for downstream steps.
- If `database_extent`:
  - **Step 1 Rule:** When the workflow involves multiple agents (not just {POSTGIS_AGENT}), add Step 1 to fetch the disaster's AOI geometry from {POSTGIS_AGENT}. This provides the spatial extent for all downstream agents.
  - **Dependency Rule:** All subsequent steps requiring spatial constraints MUST depend on this AOI fetch step and use the returned GeoJSON file as input.
  - **No Place-Name Fallback:** Do NOT use place-name geocoding for agents when the disaster AOI geometry is available—always pass the AOI GeoJSON file instead.
  - If only {POSTGIS_AGENT} is needed, skip the AOI fetch step since it can query directly using disaster metadata.
  - **Sub-Area Rule:** If a sub-area is mentioned (neighborhood, district, etc.), add a step to fetch that boundary BEFORE extracting POIs/features within it.
- If `fetch_boundary`: include an early step to obtain the boundary (reuse an existing boundary artifact if available or in context; otherwise fetch it) and ensure downstream steps use that boundary for spatial filtering.

**Examples:**
- "Show damage from Saint Louis tornado 2025-05-16" → `database_extent` (disaster explicitly referenced; Saint Louis is the disaster location, not a filter)
- "Which neighborhoods were most affected by the tornado?" → `database_extent` (disaster referenced; neighborhood aggregation happens within disaster extent)
- "Show hospitals in [neighborhood] and their damage status from [disaster]" → `database_extent` + fetch sub-area boundary (need neighborhood boundary for POI search, disaster data for damage)
- "What's affected in Forest Park area?" → `fetch_boundary` (AOI = "Forest Park area")
- "Analyze damage in this uploaded AOI" → `user_provided_aoi` (AOI = [use the uploaded AOI artifact file path from fact sheet])


## CRITICAL RULES

### Orchestrator Owns Summarization & Synthesis
- The orchestrator is responsible for final summarization, interpretation, and presentation of results to the user.
- Do NOT delegate text generation, narrative summaries, or result formatting to sub-agents.
- Sub-agents return data artifacts (GeoJSON layers, tables, statistics); the orchestrator synthesizes these into user-facing responses.
- If the user asks for "a summary" or "interpretation", plan to retrieve the necessary data, then the orchestrator will generate the summary from the results.

### Keep Instructions Semantic, Not Technical
- Use natural language to describe WHAT needs to happen, not HOW
- Let agents decide implementation details (tables, columns, algorithms, parameters)
- Example: ✅ "Get buildings with moderate or higher damage" ❌ "SELECT * WHERE damage_pct > 30"
- Example: ✅ "Group nearby damaged buildings into clusters" ❌ "Use ST_ClusterDBSCAN with eps=500"

### Agent Constraints
- ⚠️ **CRITICAL: ONE task per agent step** - Never combine multiple independent analyses in a single step
- Always keep agent constraints and capabilities in mind (see "AGENT CAPABILITIES & CONSTRAINTS" section above)
- Population queries: stac_agent returns complete statistics - do NOT add raster_ops_agent for population totals


### Dependency Management
- Mark dependencies explicitly: "depends on: Step 1, Step 2"
- Never reference an artifact before the step that creates it
- Use exact file paths when referencing outputs: "boundary.geojson" from Step 1

### Semantic Context
- Always include full place names: "Central West End, Saint Louis, Missouri" (not just "Central West End")
- Always include full disaster context: "Saint Louis tornado of January 5, 2025" (not just "tornado")
- Clarify spatial relationships: "hospitals within flood boundary" not "hospitals in Kenya"
- Include user goal: "User wants to visualize main damage pockets"

### Artifact / Response Reuse
- If fact sheet lists reusable artifacts or responses, use them directly (don't re-fetch)
- Reference artifacts by their exact file paths from ledger
- Note when reusing: "Using existing artifact: central_west_end_boundary.geojson ( e.g from response_8a2b5573)"


## Best Practices

### Agent Specific Guidelines
- For the {STAC_AGENT} , include your possible pre-, during- and post-disaster date ranges when querying satellite imagery.

---

## COMMON WORKFLOW PATTERNS
Note: These are few of the cases, but do not limit yourself to these examples. 

### Pattern 1: Hazard Exposure Analysis
**When:** User asks "which X POIs are affected by Y disaster"

```
Step 1: {POSTGIS_AGENT} - Get disaster boundary/AOI from disasters database
  Task: "Retrieve the AOI of [disaster name] to use for spatial filtering"
  → Output: hazard_boundary.geojson

Step 2: {MAPS_AGENT} - Find entities within the hazard area
  Task: "Find all [POI type] within the hazard boundary area"
  Input: hazard_boundary.geojson from Step 1
  → Output: entities.geojson

Step 3: {POSTGIS_AGENT} - Determine which entities are affected by the hazard
  Task: "Intersect the [POI type] with [disaster type] data to show exposure/impact"
  Input: entities.geojson from Step 2, disaster context
  → Output: affected_entities.geojson
```

**Key:** Step 2 uses boundary for spatial filtering. Step 3 joins with actual hazard data (flood depth, damage level, etc.) from database.

---

### Pattern 2: Satellite Change Detection
**When:** User asks for pre/post comparison, damage mapping, vegetation change, etc.

```
Step 1: {MAPS_AGENT} or reuse artifact - Get area boundary
  Task: "Get boundary for [place name]" OR "Use existing boundary from ledger"
  → Output: aoi_boundary.geojson

Step 2: {STAC_AGENT} - Get satellite imagery for the area
  Task: "Retrieve satellite imagery for [area] for [analysis type], Disaster context: [disaster details]" 
  Input: aoi_boundary.geojson from Step 1, disaster details, temporal context
  → Output: stac_items_date1.json, stac_items_date2.json

Step 3: {RASTER_AGENT} - Analyze change between time periods
  Task: "Compare imagery from [before] vs [after] to detect [what user wants to see]"
  Input: STAC items from Step 2, analysis objective
  → Output: change_map.tif (COG) or change_polygons.geojson
```
Note: The {STAC_AGENT} can decide the dates rages on it's own.
---

### Pattern 3: Multi-Location Comparison
**When:** User asks "compare X across [Location1, Location2, ...]" (`fetch_boundary` mode)

```
Step 1: {MAPS_AGENT} - Get boundary for first location
  Task: "Get boundary for [Location1 full name]"
  → Output: boundary1.geojson

Step 2: {MAPS_AGENT} - Get boundary for second location
  Task: "Get boundary for [Location2 full name]"
  → Output: boundary2.geojson

Step 3: {POSTGIS_AGENT} - Compare [metric] across all locations
  Task: "Compare [what user wants to compare] between the locations for [disaster]"
  Input: boundary1.geojson, boundary2.geojson, disaster context
  → Output: comparison_layer.geojson (with comparative statistics)
```

---

### Pattern 4: POI + Disaster Intersection (Boundary Constrained)
**When:** Spatial constraint mode is `fetch_boundary`

```
Step 1: {MAPS_AGENT} - Get specific place boundary
  Task: "Get boundary for [neighborhood], [city], [state]"
  → Output: place_boundary.geojson

Step 2: {MAPS_AGENT} - Find POIs within that place
  Task: "Find all [POI category] within [place name]"
  Input: place_boundary.geojson from Step 1
  → Output: pois.geojson

Step 3: {POSTGIS_AGENT} - Determine which POIs are affected by disaster
  Task: "Show impact of [disaster] on the [POI type] in [place]"
  Input: pois.geojson from Step 2, disaster context
  → Output: affected_pois.geojson
```

---

### Pattern 5: Disaster Analysis (Database Extent Only)
**When:** Spatial constraint mode is `database_extent`

```
Step 1: {POSTGIS_AGENT} - Analyze disaster data using disaster's stored extent
  Task: "[User's analysis request] for [disaster name, date, location]"
  Context: User wants to analyze entire disaster footprint as stored in database
  → Output: result_layer.geojson

(No boundary fetch needed - disaster's spatial extent already in database)
```

### Pattern 6: Flood Extent prediction from satellite imagery with cropland affected, buildings footprint affected, and population affected

```
step 1: {STAC_AGENT} - Retrieve satellite imagery with cropland map, building footprint map, and population data
  Task: "Retrieve satellite imagery to detect flood extent along with cropland, building footprints, and population data for [area]"
  Input: aoi_boundary.geojson from previous step, disaster context
  → Output: flood_extent_stac_items.json, cropland_map.geojson, building_footprint_map.geojson, population_data.tiff
step 2: {RASTER_AGENT} - Analyze the satellite imagery to determine flood extent and quantify affected cropland, buildings, and population
  Input: flood_extent_stac_items.json, cropland_map.geojson, building_footprint_map.geojson, population_data.tiff
  → Output: flood_extent.tif (COG), affected_cropland.geojson, affected_buildings.geojson, affected_population.geojson
```

---

### Pattern 7: Sub-Region Statistics (Database Extent + External Sub-Regions)
**When:** User asks for rankings, comparisons, or stats across sub-regions (neighborhoods, districts, etc.) for a known disaster

```
Step 1: {POSTGIS_AGENT} - Get disaster AOI from database
  Task: "Retrieve the AOI/boundary for [disaster name, date, location]"
  → Output: disaster_aoi.geojson

Step 2: {MAPS_AGENT} - Fetch sub-regions within the disaster AOI
  Task: "Find all [neighborhoods/districts] within the disaster area"
  Input: disaster_aoi.geojson from Step 1
  → Output: subregions.geojson

Step 3: {POSTGIS_AGENT} - Calculate statistics per sub-region
  Task: "Calculate [metric] per [sub-region type] for [disaster] using the sub-region boundaries"
  Input: subregions.geojson from Step 2, disaster context
  → Output: subregion_stats.geojson (with attributes: name, count, percentage, etc.)

(Orchestrator synthesizes the returned statistics into user-facing summary)
```

---

### Pattern 8: Radius/Distance-Based Queries
**When:** User specifies "within X km/miles of [point/location]" or provides a point with distance constraint

```
Step 1: {POSTGIS_AGENT} - Create buffer geometry from point
  Task: "Create a [distance] buffer around the provided point/location"
  Input: User-provided point geometry or geocoded location
  → Output: buffer_aoi.geojson (polygon)

Step 2: [Appropriate agent based on data need] - Query within buffer
  Task: "[User's analysis request] within the buffer area"
  Input: buffer_aoi.geojson from Step 1
  → Output: results.geojson
```

**Key rule:** map_search_agent CANNOT create buffers—it can only extract features within an existing AOI. Always use {POSTGIS_AGENT} first to create the buffer geometry.

---

### Pattern 9: Date-Specific Feature Detection from Imagery
**When:** User asks about physical/natural features (water bodies, vegetation, built-up areas) at a specific historical date

```
Step 1: [Get AOI] - Obtain area of interest boundary
  (Use existing artifact, user-provided AOI, or fetch boundary)
  → Output: aoi_boundary.geojson

Step 2: {STAC_AGENT} - Fetch satellite imagery for the target date
  Task: "Retrieve satellite imagery for [date] to analyze [feature type]"
  Input: aoi_boundary.geojson, target date
  → Output: stac_items.json

Step 3: {RASTER_AGENT} - Derive features from imagery
  Task: "Detect/classify [feature type] from the imagery"
  Input: stac_items.json from Step 2
  → Output: detected_features.tif or detected_features.geojson
```

**Key rule:** map_search_agent provides CURRENT/STATIC features only. For date-specific analysis of natural features, use stac_agent → raster_ops_agent pipeline.

---


## VALIDATION CHECKLIST

Before finalizing your plan, verify:

- [ ] Instructions are semantic (WHAT to do), not technical (HOW to do it)
- [ ] No table names, column names, SQL syntax, or algorithm names in instructions
- [ ] All agent constraints respected (one boundary/POI per maps call, etc.)
- [ ] Dependencies are valid (no circular refs, no orphaned steps)
- [ ] Full semantic context provided (place names, disaster details, user goals)
- [ ] Reusable artifacts from fact sheet are leveraged (exact file paths)
- [ ] Spatial constraint mode selected above is followed (`user_provided_aoi` vs `fetch_boundary` vs `database_extent`)
- [ ] Success criteria are clear and verifiable

---

Generate the plan now.
"""


# =============================================================================
# ADDITIONAL ORCHESTRATOR PROMPTS
# =============================================================================

ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT = """
We are working to address the following user request:

{task}


To answer this request we have assembled the following team:

{team}


Here is an initial fact sheet to consider:

{facts}


Here is the plan to follow as best as possible:

{plan}
"""


ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT = """As a reminder, we are working to solve the following task:

{task}

It's clear we aren't making as much progress as we would like, but we may have learned something new. Please rewrite the following fact sheet, updating it to include anything new we have learned that may be helpful. Example edits can include (but are not limited to) adding new guesses, moving educated guesses to verified facts if appropriate, etc. Updates may be made to any section of the fact sheet, and more than one section of the fact sheet can be edited. This is an especially good time to update educated guesses, so please at least add or update one educated guess or hunch, and explain your reasoning.

Here is the old fact sheet:

{facts}
"""


ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT = """## REPLAN REQUEST

Something went wrong in the previous execution. Please:
1. **Briefly explain the root cause** of the failure (1-2 sentences)
2. **Create a revised plan** that overcomes the issues and avoids repeating mistakes

---

## TASK REMINDER

{task}

---

## TEAM COMPOSITION

{team}

---

## UPDATED FACTS

{facts}

---

{planning_guidance}

---

## INSTRUCTIONS

Based on the conversation history (which shows what failed), the updated facts above, and the planning guidance:

1. Identify what went wrong and why
2. Generate a new plan following the same format and rules as the original planning prompt
3. Ensure the new plan:
   - Addresses the root cause of failure
   - Follows all agent constraints and capabilities
   - Uses semantic instructions (WHAT not HOW)
   - Has proper dependencies
   - Reuses any successful artifacts from previous attempts

Generate the revised plan now.
"""


ORCHESTRATOR_FINAL_ANSWER_PROMPT = """
We are working on the following task:
{task}

We have completed the task.

The above messages contain the conversation that took place to complete the task.

Based on the information gathered, provide the final answer to the original request.
The answer should be phrased as if you were speaking to the user.
"""