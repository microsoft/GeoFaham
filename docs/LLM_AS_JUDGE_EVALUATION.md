# LLM-as-Judge Evaluation System

This document describes GeoFaham's evaluation methodology using LLM-as-Judge to assess multi-agent system performance against ground truth.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Evaluation Dimensions](#evaluation-dimensions)
4. [Scoring Methodology](#scoring-methodology)
5. [Input Data](#input-data)
6. [Running Evaluations](#running-evaluations)
7. [Output Interpretation](#output-interpretation)
8. [Design Decisions](#design-decisions)

---

## Overview

### What is LLM-as-Judge?

LLM-as-Judge is an evaluation paradigm where a powerful language model (the "judge") assesses the quality of outputs from another system by comparing predictions against ground truth. This approach is particularly suited for complex, multi-step AI systems where:

- **Exact matching is insufficient**: Multiple valid solutions may exist
- **Semantic equivalence matters**: Different code/queries can produce identical results
- **Qualitative assessment needed**: Instruction quality, summarization clarity, etc.

### Why LLM-as-Judge for GeoFaham?

GeoFaham is a multi-agent system with complex workflows:

```
User Query → Orchestrator → [Maps | STAC | Vector | Raster] Agents → Final Answer
```

Traditional metrics fail because:
- **Plan paths vary**: `maps→stac→raster` and `maps→vector→raster` may both be valid
- **Code varies**: Different SQL achieving same spatial operation
- **Answers vary**: Slightly different thresholds produce different but reasonable results

LLM-as-Judge can assess **semantic correctness** across all these dimensions.

---

## Architecture

### Two-Layer Evaluation

```
┌─────────────────────────────────────────────────────────────────┐
│                     LAYER 1: LLM JUDGE                          │
│                                                                 │
│   For each (question, config, run):                            │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │ Ground Truth│ +  │ Prediction  │ +  │Run Metadata │        │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘        │
│          │                  │                  │                │
│          └──────────────────┼──────────────────┘                │
│                             ▼                                   │
│                    ┌────────────────┐                           │
│                    │   Judge LLM    │                           │
│                    │   (GPT-5.1)    │                           │
│                    └────────┬───────┘                           │
│                             │                                   │
│                             ▼                                   │
│                    ┌────────────────┐                           │
│                    │  JSON Scores   │                           │
│                    │  per dimension │                           │
│                    └────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  LAYER 2: PROGRAMMATIC AGGREGATION              │
│                                                                 │
│   ┌─────────────────────────────────────────────────────┐       │
│   │ Collect scores from all questions                   │       │
│   │ Compute averages per dimension                      │       │
│   │ Compute category scores (planning, execution, etc.) │       │
│   │ Compute overall weighted score                      │       │
│   │ Aggregate flags (error rates, replan rates)         │       │
│   └─────────────────────────────────────────────────────┘       │
│                             │                                   │
│                             ▼                                   │
│                    ┌────────────────┐                           │
│                    │ Final Metrics  │                           │
│                    │ per Config     │                           │
│                    └────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| Judge Prompts | `runtime/eval_scripts/judge_prompts.py` | Prompt templates, weights, dimension definitions |
| Evaluation Runner | `runtime/eval_scripts/run_llm_judge.py` | Main script to run evaluations |
| Ground Truth | `data/benchmarks/geofaham/benchmark_gt/` | Reference answers per question |
| Predictions | `data/benchmarks/geofaham/benchmark_runs/` | Model outputs to evaluate |
| Results | `data/benchmarks/geofaham/eval_results/` | Evaluation outputs |

---

## Evaluation Dimensions

The judge evaluates **11 dimensions** organized into **4 categories**:

### A. Planning & Orchestration (27% weight)

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `plan_correctness` | 11% | Is the agent sequence correct? Are the right agents selected for each subtask? |
| `plan_completeness` | 8% | Are all necessary steps included? No critical steps missing? |
| `instruction_quality` | 8% | Are instructions semantic (WHAT not HOW)? Is context provided? Are artifact references correct? |

**Example Assessment:**

```
GT Plan: [maps_agent, stac_agent, raster_ops_agent]
Predicted: [maps_agent, vector_agent, raster_ops_agent]

Score: 0.66
Reason: "Used vector_agent instead of stac_agent for satellite imagery retrieval. 
         Vector agent cannot access satellite data."
```

### B. Execution (38% weight)

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `tool_selection` | 11% | Did agents choose the correct tools? |
| `parameter_accuracy` | 9% | Are tool parameters correct? (dates, bbox, collection, thresholds) |
| `code_logic` | 11% | Is SQL/Python functionally equivalent to GT? |
| `result_summarization` | 7% | Are agent summaries clear and accurate for the orchestrator? |

**Example Assessment:**

```
GT Tool: search_stac_items(collection="sentinel-2-l2a", datetime="2023-08-01/2023-08-15")
Predicted: search_stac_items(collection="landsat-c2-l2", datetime="2023-08-01/2023-08-30")

tool_selection: 0.5 - "Used Landsat instead of Sentinel-2, lower resolution"
parameter_accuracy: 0.7 - "Date range extended but still reasonable"
```

### C. Compliance (17% weight)

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `prompt_compliance` | 9% | Does execution follow system rules? No anti-patterns? |
| `error_recovery` | 8% | If errors occurred, were they handled gracefully? |

**Prompt Compliance Checks:**
- Vector agent: No `ST_Union` on large unfiltered tables
- Raster agent: No using own output as external GeoJSON input
- STAC agent: Appropriate collection and date selection
- All agents: Proper artifact passing via response_id

**Error Recovery Scoring:**
- 1.0 = No errors occurred
- 0.75-0.9 = Errors occurred but recovered successfully
- 0.5 = Partial recovery
- 0.0-0.25 = Errors caused complete failure

### D. Output (18% weight)

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| `final_answer_accuracy` | 8% | Does the final answer align with GT expected findings and metrics (within acceptable tolerance)? |
| `final_answer_completeness` | 10% | Does it address all parts of the question? |

**Note:** Output category has lower weight (18%) because **process correctness is more valuable than final answer match** in multi-agent evaluation. If the process is correct, the answer should follow. Different valid approaches may produce different but correct answers.

---

## Scoring Methodology

### Per-Dimension Scores

Each dimension receives a score from **0.0 to 1.0**:

| Score | Meaning |
|-------|---------|
| 1.0 | Perfect or equivalent to GT |
| 0.75 | Minor issues but mostly correct |
| 0.5 | Partially correct, some significant issues |
| 0.25 | Major issues but some correct elements |
| 0.0 | Completely wrong or missing |

### Category Scores

Categories are **simple averages** of their dimensions:

```python
planning = avg(plan_correctness, plan_completeness, instruction_quality)
execution = avg(tool_selection, parameter_accuracy, code_logic, result_summarization)
compliance = avg(prompt_compliance, error_recovery)
output = avg(final_answer_accuracy, final_answer_completeness)
```

### Overall Score

Overall score is a **weighted average** of categories:

```python
overall = (
    planning * 0.27 +
    execution * 0.38 +
    compliance * 0.17 +
    output * 0.18
)
```

**Rationale for weights:**
- **Execution (38%)**: Core competency - can agents do their jobs correctly?
- **Planning (27%)**: Critical starting point - right plan leads to right execution
- **Output (18%)**: Lower weight because process correctness is more valuable than final answer match
- **Compliance (17%)**: Important for robustness and following system rules

**Process vs Outcome:** Process metrics (planning + execution + compliance) account for **82%** of the overall score, while outcome metrics (output) account for only **18%**. This reflects the research consensus that evaluating multi-agent systems should focus on whether the system makes correct decisions, not just whether it produces the expected final answer.

**Rationale for weights:**
- **Execution (35%)**: Core competency - can agents do their jobs?
- **Planning & Output (25% each)**: Critical endpoints - right plan + right answer
- **Compliance (15%)**: Important but secondary to correctness

### Handling Failed Runs

When a run fails (timeout, error), the judge still evaluates work done:

```
Run Metadata:
- Status: failed
- Error: Timeout fetching roads for multiple provinces
- Duration: 180.5s

Judge Guidance:
"If run failed due to timeout or error, still evaluate the work done up to that point.
A run that made correct decisions but timed out should score well on planning/tool 
selection but may score lower on final answer completeness."
```

This distinguishes:
- **Bad decisions** → Low scores across all dimensions
- **Good decisions, execution failed** → High planning, low output

---

## Input Data

### Ground Truth Structure

```
data/benchmarks/geofaham/benchmark_gt/
└── Q039/
    └── run_1/
        ├── conversation_history.json  # Oracle run conversation
        └── ground_truth.json          # Extracted GT
```

**ground_truth.json schema:**

```json
{
  "question_id": "Q039",
  "question_text": "What roads in Lahaina were flooded during the August 2023 fires?",
  
  "plan_gt": {
    "execution_sequence": [
      {"step": 1, "agent": "maps_agent", "task": "Get road network for Lahaina"},
      {"step": 2, "agent": "stac_agent", "task": "Find satellite imagery"},
      {"step": 3, "agent": "raster_ops_agent", "task": "Detect flood extent"}
    ],
    "plan_reasoning": "Maps provides roads, STAC provides imagery, Raster does analysis",
    "alternative_valid_paths": [
      ["maps_agent", "vector_agent", "raster_ops_agent"]
    ]
  },
  
  "agent_specific_gt": {
    "maps_agent": {
      "tool_calls_gt": [
        {"tool_name": "get_roads", "key_parameters": {"place_name": "Lahaina, Hawaii"}}
      ]
    },
    "stac_agent": {
      "tool_calls_gt": [
        {"tool_name": "search_stac_items", "key_parameters": {
          "collection": "sentinel-2-l2a",
          "datetime": "2023-08-08/2023-08-15"
        }}
      ],
      "constraints": {
        "collection_selection": "Must use optical imagery for flood detection",
        "date_logic": "Must be after fire event (Aug 8, 2023)"
      }
    }
  },
  
  "final_answer_gt": {
    "expected_findings": ["Flooded road segments identified", "Area quantified"],
    "key_metrics": {"flooded_roads_km": 12.5},
    "acceptable_variation": {"flooded_roads_km": "±15%"}
  }
}
```

### Prediction Structure

```
data/benchmarks/geofaham/benchmark_runs/
└── Q039/
    └── all-gpt4o/           # Config name
        └── run_1/
            ├── conversation_history.json
            └── run_metadata.json
```

**run_metadata.json:**

```json
{
  "status": "success",
  "success": true,
  "duration_seconds": 45.2,
  "total_turns": 12,
  "replans": 0
}
```

Or for failed runs:

```json
{
  "status": "failed",
  "success": false,
  "error": "Timeout: OSM query exceeded 180s limit",
  "failure_reason": "Attempted to fetch roads for entire province",
  "duration_seconds": 180.0,
  "timeout": true
}
```

---

## Running Evaluations

### Basic Usage

```bash
# Evaluate single question, single config, default run (run_1)
python runtime/eval_scripts/run_llm_judge.py \
    --question Q039 \
    --config all-gpt4o

# Evaluate specific run
python runtime/eval_scripts/run_llm_judge.py \
    -q Q039 \
    -c all-gpt4o \
    --run run_2

# Evaluate all questions with GT
python runtime/eval_scripts/run_llm_judge.py \
    --all \
    --config all-gpt4o

# Multiple configs
python runtime/eval_scripts/run_llm_judge.py \
    --all \
    --config all-gpt4o all-gpt5 gpt4o-with-gpt5-planner

# Lightweight evaluation (faster, 3 dimensions only)
python runtime/eval_scripts/run_llm_judge.py \
    --all \
    --config all-gpt4o \
    --lightweight

# Custom judge model
python runtime/eval_scripts/run_llm_judge.py \
    --all \
    --config all-gpt4o \
    --judge-model gpt-4o

# Verbose output (show per-dimension scores)
python runtime/eval_scripts/run_llm_judge.py \
    --all \
    --config all-gpt4o \
    --verbose
```

### Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--question` | `-q` | - | Single question ID (e.g., Q039) |
| `--all` | `-a` | - | Evaluate all questions with GT |
| `--config` | `-c` | Required | Config(s) to evaluate |
| `--run` | `-r` | `run_1` | Run ID to evaluate |
| `--lightweight` | `-l` | False | Use 3-dimension quick eval |
| `--output-dir` | `-o` | `eval_results/` | Output directory |
| `--judge-model` | - | `gpt-5.1` | Model to use as judge |
| `--verbose` | `-v` | False | Print detailed scores |

---

## Output Interpretation

### Console Output

```
🔍 Evaluating config: all-gpt4o

  📝 Question: Q038 (run_1) ✅ score: 0.847
  📝 Question: Q039 (run_1) ✅ score: 0.923
  📝 Question: Q040 (run_1) ⚠️ No prediction found for run_1, skipping
  📝 Question: Q041 (run_1) ✅ score: 0.756

💾 Results saved to: eval_results/eval_all-gpt4o_all_run_1_20260204_133500.json

============================================================
EVALUATION SUMMARY - Config: all-gpt4o
============================================================

Evaluations: 3 successful, 0 failed

📊 Overall Score: 0.842 (±0.068)

📈 Category Scores:
  planning    : ████████████████░░░░ 0.867
  execution   : ████████████████░░░░ 0.823
  compliance  : ██████████████████░░ 0.912
  output      : ████████████████░░░░ 0.789

📋 Dimension Scores:
  plan_correctness         : █████████░ 0.889
  plan_completeness        : ████████░░ 0.833
  instruction_quality      : █████████░ 0.878
  tool_selection           : ████████░░ 0.844
  parameter_accuracy       : ████████░░ 0.800
  code_logic               : ████████░░ 0.811
  result_summarization     : ████████░░ 0.833
  prompt_compliance        : █████████░ 0.922
  error_recovery           : █████████░ 0.900
  final_answer_accuracy    : ████████░░ 0.811
  final_answer_completeness: ████████░░ 0.767

🚩 Flags (rate):
  had_errors               : 33.3%
  recovered_from_errors    : 33.3%
  had_replan               : 0.0%
  replan_successful        : 0.0%
  slow_but_correct         : 0.0%
  redundant_steps          : 0.0%

============================================================
```

### JSON Output Structure

```json
{
  "config": "all-gpt4o",
  "run": "run_1",
  "judge_model": "gpt-5.1",
  "lightweight": false,
  "timestamp": "2026-02-04T13:35:00.123456",
  
  "questions": {
    "Q038": {
      "question_id": "Q038",
      "config": "all-gpt4o",
      "run": "run_1",
      "run_status": "success",
      
      "scores": {
        "plan_correctness": {
          "score": 0.9,
          "reason": "Correct agent sequence, appropriate delegation"
        },
        "plan_completeness": {
          "score": 0.85,
          "reason": "All major steps present, minor optimization possible"
        },
        "instruction_quality": {
          "score": 0.88,
          "reason": "Clear semantic instructions, proper artifact passing"
        },
        "tool_selection": {
          "score": 0.95,
          "reason": "Correct tools selected for each task"
        },
        "parameter_accuracy": {
          "score": 0.8,
          "reason": "Date range slightly broader than optimal"
        },
        "code_logic": {
          "score": 0.85,
          "reason": "SQL logic correct, uses spatial index properly"
        },
        "result_summarization": {
          "score": 0.9,
          "reason": "Clear summaries with key metrics"
        },
        "prompt_compliance": {
          "score": 0.95,
          "reason": "Follows all system rules, no anti-patterns"
        },
        "error_recovery": {
          "score": 1.0,
          "reason": "No errors occurred"
        },
        "final_answer_accuracy": {
          "score": 0.82,
          "reason": "Flood extent within acceptable range"
        },
        "final_answer_completeness": {
          "score": 0.78,
          "reason": "Missing breakdown by road type"
        }
      },
      
      "flags": {
        "had_errors": false,
        "recovered_from_errors": false,
        "had_replan": false,
        "replan_was_necessary": false,
        "replan_successful": false,
        "slow_but_correct": false,
        "redundant_steps": false
      },
      
      "category_scores": {
        "planning": 0.877,
        "execution": 0.875,
        "compliance": 0.975,
        "output": 0.800
      },
      
      "overall_score": 0.875,
      "summary": "Strong performance with correct planning and execution. Minor gaps in final answer completeness."
    }
  },
  
  "aggregate": {
    "num_evaluations": 3,
    "num_errors": 0,
    
    "dimension_averages": {
      "plan_correctness": 0.889,
      "plan_completeness": 0.833,
      "instruction_quality": 0.878,
      "tool_selection": 0.844,
      "parameter_accuracy": 0.800,
      "code_logic": 0.811,
      "result_summarization": 0.833,
      "prompt_compliance": 0.922,
      "error_recovery": 0.900,
      "final_answer_accuracy": 0.811,
      "final_answer_completeness": 0.767
    },
    
    "category_averages": {
      "planning": 0.867,
      "execution": 0.823,
      "compliance": 0.912,
      "output": 0.789
    },
    
    "overall_average": 0.842,
    "overall_std": 0.068,
    
    "flag_rates": {
      "had_errors": 0.333,
      "recovered_from_errors": 0.333,
      "had_replan": 0.0,
      "replan_successful": 0.0,
      "slow_but_correct": 0.0,
      "redundant_steps": 0.0
    }
  }
}
```

### Interpreting Results

#### Overall Score Interpretation

| Score Range | Interpretation |
|-------------|----------------|
| 0.9 - 1.0 | Excellent - Near-perfect performance |
| 0.8 - 0.9 | Good - Minor issues, production-ready |
| 0.7 - 0.8 | Acceptable - Some gaps, needs improvement |
| 0.5 - 0.7 | Poor - Significant issues |
| < 0.5 | Failed - Major problems |

#### Category Interpretation

- **High Planning, Low Output**: System understands the task but fails in execution details
- **High Execution, Low Planning**: Individual agents work but orchestration is poor
- **Low Compliance**: System works but uses anti-patterns or ignores rules
- **High Compliance, Low Output**: Follows rules but doesn't achieve goals

#### Flag Interpretation

| Flag | What It Indicates |
|------|-------------------|
| `had_errors` > 30% | System reliability issues |
| `recovered_from_errors` low vs `had_errors` | Poor error handling |
| `had_replan` high | Initial plans frequently fail |
| `replan_successful` low vs `had_replan` | Replanning doesn't help |
| `slow_but_correct` high | Optimization opportunities |
| `redundant_steps` high | Efficiency issues |

---

## Design Decisions

### Why GPT-5.1 as Default Judge?

- **Consistency**: Same model used for GT generation → fair comparison
- **Capability**: Understands complex multi-agent interactions
- **Cost**: Single call per question (not per dimension)

### Why Not Exact Matching?

Consider SQL evaluation:

```sql
-- GT
SELECT name FROM roads r 
JOIN floods f ON ST_Intersects(r.geom, f.geom)
WHERE f.event_date = '2023-08-08'

-- Prediction (functionally equivalent)
SELECT r.name FROM roads r, floods f 
WHERE ST_Intersects(r.geom, f.geom) 
  AND f.event_date = '2023-08-08'
```

String matching: 0% match
LLM Judge: 1.0 (semantically equivalent)

### Why Include Run Metadata?

Without metadata, a timeout looks like complete failure. With metadata:

```
Run failed due to timeout (180s) fetching roads for large AOI.
Planning was correct, tool selection was correct.
Failure was due to AOI size, not agent decisions.
```

Judge can award appropriate partial credit.

### Why Separate Dimensions vs Single Score?

Granular dimensions enable:
- **Diagnosis**: Where exactly does the model fail?
- **Comparison**: Model A better at planning, Model B better at execution
- **Improvement**: Focus efforts on weakest dimensions

---

## Appendix: Judge Prompt

The full judge prompt includes:

1. **System Context**: Agent capabilities, key rules
2. **Ground Truth**: Plan, tools, code, expected answer
3. **Run Metadata**: Success/failure info, errors, timing
4. **Prediction**: Full conversation history
5. **Evaluation Criteria**: Per-dimension guidelines
6. **Output Format**: JSON schema

See `runtime/eval_scripts/judge_prompts.py` for complete prompt templates.
