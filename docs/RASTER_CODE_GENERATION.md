# Raster Agent: Code Generation & Multi-Step Processing

This document explains why the Raster Agent **generates Python code** instead of using predefined tools, and why it uses a **multi-step approach with intermediate results**.

---

## The Design Challenge

Raster processing for geospatial analysis involves:
- **Infinite operation combinations**: NDVI, NDWI, NBR, burn severity, cloud masking, custom indices...
- **Domain-specific thresholds**: "burned" vs "unburned" depends on the specific scene
- **Complex pipelines**: Load → mask → compute → threshold → classify → export

**Problem**: We cannot enumerate every possible raster operation as a predefined tool.

---

## Solution: LLM-Generated Python Code

Instead of:
```python
# Predefined tools (limited)
tools = [
    compute_ndvi(red_band, nir_band),
    compute_burn_severity(nir_band, swir_band),
    apply_threshold(raster, value),
    # ... 100 more tools?
]
```

We use:
```python
# Single tool that executes LLM-generated code
tools = [
    execute_custom_raster_code(code: str)
]
```

The LLM writes Python code using xarray/rioxarray:

```python
# LLM-generated code for burn severity
import xarray as xr

# Load pre and post fire imagery
pre = load_stac_items(pre_fire_items)
post = load_stac_items(post_fire_items)

# Compute NBR (Normalized Burn Ratio)
pre_nbr = (pre['nir'] - pre['swir16']) / (pre['nir'] + pre['swir16'])
post_nbr = (post['nir'] - post['swir16']) / (post['nir'] + post['swir16'])

# Compute dNBR (differenced NBR)
dnbr = pre_nbr - post_nbr

# Classify burn severity
severity = xr.where(dnbr > 0.66, 'high', 
           xr.where(dnbr > 0.27, 'moderate',
           xr.where(dnbr > 0.1, 'low', 'unburned')))
```

> **Research Insight**: Code generation enables **infinite expressivity**—any valid Python/xarray operation can be performed without predefined tool limitations. The LLM's creativity is bounded only by the execution sandbox, not by a finite tool catalog.

---

## Why Multi-Step Processing with Intermediate Results

### The Problem with Single-Step

**Naive approach**: LLM generates complete pipeline, executes once, returns final result.

```python
# Single step - LLM guesses thresholds
dnbr = pre_nbr - post_nbr
burned_area = dnbr > 0.27  # Is 0.27 correct? LLM doesn't know!
```

**Issues**:
1. LLM **cannot see the data** before choosing thresholds
2. Thresholds from literature may not match specific scene
3. If wrong, must regenerate entire pipeline

### The Solution: Intermediate Results

Multi-step approach where LLM **inspects data** between steps:

```
┌─────────────────────────────────────────────────────────────┐
│                     STEP 1: Compute Index                    │
│                                                              │
│  LLM generates:                                              │
│    dnbr = pre_nbr - post_nbr                                │
│    save_intermediate(dnbr, "dnbr_result")                   │
│                                                              │
│  Returns: Statistics of dNBR                                 │
│    min: -0.12, max: 0.89, mean: 0.23                        │
│    histogram: [0-0.1: 45%, 0.1-0.3: 30%, 0.3+: 25%]        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     STEP 2: Informed Threshold               │
│                                                              │
│  LLM sees actual data distribution:                         │
│    "dNBR ranges from -0.12 to 0.89, with 25% above 0.3"    │
│                                                              │
│  LLM generates informed threshold:                          │
│    burned = dnbr > 0.3  # Based on actual histogram!        │
│    high_severity = dnbr > 0.5                               │
└─────────────────────────────────────────────────────────────┘
```

### How Intermediate Results Enable Better Thresholding

**Without intermediate inspection:**
```
LLM context: "Compute burn severity for Lahaina fire"
LLM guess: threshold = 0.27 (from textbook)
Reality: This scene has different atmospheric conditions, threshold should be 0.35
Result: Over-classification of burned areas
```

**With intermediate inspection:**
```
Step 1 - LLM: "Compute dNBR and show me statistics"
System returns: {min: -0.1, max: 0.82, p75: 0.35, p90: 0.52}

Step 2 - LLM sees actual distribution:
"The 75th percentile is 0.35, suggesting a natural break point.
 I'll use 0.35 for moderate burn and 0.52 for high severity."

Result: Scene-specific thresholds based on actual data
```

> **Research Insight**: Intermediate results create a **feedback loop** where the LLM can inspect actual data distributions before making thresholding decisions. This grounds the LLM's reasoning in empirical evidence rather than literature defaults.

---

## The Multi-Step Workflow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   STEP 1     │     │   STEP 2     │     │   STEP 3     │
│              │     │              │     │              │
│  Load data   │────▶│  Compute     │────▶│  Threshold   │
│  Inspect     │     │  index       │     │  & classify  │
│  bands       │     │  Get stats   │     │  (informed)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
   "4 bands:            "dNBR range:         "Using 0.35
    B02,B03,B04,B8A      -0.1 to 0.82         threshold based
    CRS: EPSG:32604      mean: 0.28"          on p75 value"
    10m resolution"
```

### Implementation: save_intermediate()

The raster executor provides a mechanism for intermediate saves:

```python
# In LLM-generated code
result = compute_some_index(data)
save_intermediate(result, "index_result")  # Doesn't end execution

# System returns statistics to LLM:
# {
#   "saved_as": "index_result",
#   "stats": {"min": 0.1, "max": 0.9, "mean": 0.4, "std": 0.15},
#   "shape": [1024, 1024],
#   "crs": "EPSG:32604"
# }

# LLM uses these stats in next step for threshold selection
```

---

## Benefits of This Approach

### 1. Data-Driven Thresholds

| Approach | Threshold Source | Accuracy |
|----------|-----------------|----------|
| Predefined tools | Hardcoded values | Low (scene-dependent) |
| Single-step code gen | LLM guess from literature | Medium |
| **Multi-step with inspection** | Actual data distribution | High |

### 2. Debugging Visibility

When results are wrong, we can trace:
- Step 1 output: Was data loaded correctly?
- Step 2 output: Was index computed correctly?
- Step 3 output: Was threshold appropriate?

### 3. Adaptive Workflows

LLM can change approach based on intermediate findings:

```
Step 1: Check cloud cover
  → Result: 60% clouds

Step 2: LLM decides
  → "High cloud cover detected. I'll apply cloud mask before computing index."
  
Step 3: Apply mask, recompute
  → Clean result
```

### 4. Human-in-the-Loop Potential

Intermediate results can be shown to users:

```
System: "I computed dNBR. Here's the distribution: [histogram]
        I suggest using 0.35 as threshold. Proceed?"
        
User: "Use 0.4 instead, I know this area has healthy vegetation"

System: Continues with user-specified threshold
```

---

## Code Generation + Multi-Step: The Combination

```
┌─────────────────────────────────────────────────────────────┐
│                     LLM CAPABILITIES                         │
│                                                              │
│  Code Generation          Multi-Step Processing             │
│  ───────────────          ─────────────────────             │
│  • Infinite operations    • Data inspection                 │
│  • Custom indices         • Informed thresholds             │
│  • Complex pipelines      • Adaptive workflows              │
│  • No tool limits         • Debugging visibility            │
│                                                              │
│            Combined: Flexible + Grounded                     │
└─────────────────────────────────────────────────────────────┘
```

> **Research Insight**: Code generation provides **expressivity** (what operations are possible), while multi-step processing provides **grounding** (decisions based on actual data). Together, they enable LLM-driven raster analysis that is both flexible and empirically sound.

---

## Comparison with Alternatives

| Approach | Expressivity | Grounding | Complexity |
|----------|--------------|-----------|------------|
| Predefined tools | Low (finite set) | N/A | Simple |
| Single-step code gen | High | Low (guessing) | Medium |
| **Multi-step code gen** | High | High (data-driven) | Higher |
| Human expert | Highest | Highest | N/A |

---

## Security Considerations

Generated code runs in a **sandboxed executor**:
- Restricted imports (xarray, rioxarray, numpy only)
- No file system access outside artifacts
- No network access
- Timeout limits
- Memory limits

---

## Key Takeaways

1. **Code generation beats tool enumeration** — Raster operations are too diverse to predefine; LLM creativity should not be artificially bounded.

2. **Intermediate results enable data-driven decisions** — LLMs cannot "see" raster data, but they can reason about statistics and distributions.

3. **Multi-step creates feedback loops** — Each step informs the next, grounding LLM decisions in empirical evidence.

4. **Thresholds should be scene-specific** — Literature values are starting points; actual data distributions provide better decision boundaries.

5. **Transparency aids debugging** — Intermediate outputs make the reasoning chain visible and debuggable.

---

## Related Documentation

- [AGENT_SPECIALIZATION.md](AGENT_SPECIALIZATION.md) - Why raster is a separate agent
- [CONTEXT_EFFICIENT_DATA_SHARING.md](CONTEXT_EFFICIENT_DATA_SHARING.md) - How raster results are shared
- [TOOL_RESPONSE_SCHEMAS.md](TOOL_RESPONSE_SCHEMAS.md) - Raster response formats
