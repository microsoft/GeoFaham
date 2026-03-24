# Benchmark Evaluation Runner

This document details the implementation of the GeoFaham benchmark evaluation pipeline, covering how experiments are executed, configured, and managed.

## Overview

The benchmark evaluation runner (`runtime/eval_scripts/run_benchmark_eval_v2.py`) executes GeoFaham against benchmark questions with configurable LLM setups. It supports:

- Running individual questions or batch evaluation
- Multiple LLM configurations for ablation studies
- Multiple runs per question for reproducibility analysis
- Automatic state management and artifact collection
- Timeout handling and resume capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    run_benchmark_eval_v2.py                         │
├─────────────────────────────────────────────────────────────────────┤
│  CLI Arguments                                                       │
│  ├── --question Q001        (single question)                       │
│  ├── --with-gt              (all questions with ground truth)       │
│  ├── --config all-gpt4o     (LLM configuration)                     │
│  ├── --run 1                (specific run number)                   │
│  ├── --resume               (skip completed runs)                   │
│  └── --timeout 10           (minutes per question)                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LLM Configuration Layer                          │
├─────────────────────────────────────────────────────────────────────┤
│  LLMConfig Dataclass:                                               │
│  ├── default_model          (base model for simple agents)         │
│  ├── reasoning_model        (model for complex reasoning)          │
│  ├── vector_agent           (override for PostGIS agent)           │
│  ├── maps_agent             (override for Maps agent)              │
│  ├── stac_agent             (override for STAC agent)              │
│  ├── raster_agent           (override for Raster ops agent)        │
│  ├── orchestrator_planner   (override for planning LLM)            │
│  └── orchestrator_progress  (override for progress tracking)       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Team Creation                                  │
├─────────────────────────────────────────────────────────────────────┤
│  GeoFahamGroupChat orchestrator with:                               │
│  ├── postgis_agent      (Vector queries)                            │
│  ├── map_search_agent   (OSM features)                              │
│  ├── stac_agent         (Satellite imagery)                         │
│  ├── raster_ops_agent   (Raster analysis)                           │
│  └── user_proxy         (No-op for benchmark)                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Question Execution                             │
├─────────────────────────────────────────────────────────────────────┤
│  1. Reset state (response store, team state, history)               │
│  2. Stream messages from team.run_stream()                          │
│  3. Track tokens, check timeout                                     │
│  4. Save results incrementally                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Pre-defined LLM Configurations

The runner includes several pre-defined configurations for ablation studies:

| Config Name | Description | Use Case |
|-------------|-------------|----------|
| `current` | Use environment defaults | Development testing |
| `all-gpt4o` | All agents use GPT-4o | Cost-effective baseline |
| `all-gpt5` | All agents use GPT-5.1 | Oracle/upper-bound |
| `gpt4o-with-gpt5-planner` | GPT-4o agents, GPT-5.1 planner | Test if planning quality matters |
| `gpt4o-planner-gpt5-agents` | GPT-4o planner, GPT-5.1 agents | Inverse test |
| `mixed-default` | GPT-4o simple, GPT-5.1 complex | Balanced cost/quality |

### Configuration Application

Configurations are applied via environment variables before team creation:

```python
def apply_llm_config(llm_config: LLMConfig):
    os.environ["GEOFAHAM_DEFAULT_MODEL"] = llm_config.default_model
    os.environ["GEOFAHAM_REASONING_MODEL"] = llm_config.reasoning_model
    os.environ["GEOFAHAM_VECTOR_AGENT_MODEL"] = llm_config.vector_agent
    # ... etc
    reset_config()  # Reload config to pick up new values
```

## Usage Examples

### Basic Usage

```bash
# Run single question with current environment config
python runtime/eval_scripts/run_benchmark_eval_v2.py --question Q001

# Run all questions that have ground truth
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt

# Run with specific LLM configuration
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --config all-gpt4o

# List available questions and configs
python runtime/eval_scripts/run_benchmark_eval_v2.py --list
python runtime/eval_scripts/run_benchmark_eval_v2.py --list-configs
```

### Multi-Run Experiments

```bash
# Run all GT questions as run_1
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --config all-gpt4o --run 1

# Run again as run_2 for reproducibility analysis
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --config all-gpt4o --run 2

# Resume interrupted run (skips successful runs)
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --config all-gpt4o --run 1 --resume

# Skip specific problematic questions
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --config all-gpt4o --run 1 --skip Q008,Q009
```

### Timeout Control

```bash
# 10-minute timeout per question (default)
python runtime/eval_scripts/run_benchmark_eval_v2.py --with-gt --timeout 10

# Quick testing with 30-second timeout
python runtime/eval_scripts/run_benchmark_eval_v2.py --question Q001 --timeout-seconds 30
```

## Output Structure

Each run produces a structured output directory:

```
data/benchmarks/geofaham/benchmark_eval/
└── {config_name}/                    # e.g., all-gpt4o
    └── {question_id}/                # e.g., Q001
        └── run_{n}/                  # e.g., run_1
            ├── conversation_history.json   # Full message stream
            ├── team_state.json             # Final orchestrator state
            ├── run_metadata.json           # Execution metadata
            ├── response_store.jsonl        # Agent responses
            └── artifacts/                  # Generated files (GeoJSON, etc.)
```

### run_metadata.json Schema

```json
{
  "question_id": "Q001",
  "question_text": "For the Saint Louis tornado...",
  "llm_config": {
    "name": "all-gpt4o",
    "description": "All agents use GPT-4o",
    "models": {
      "default": "gpt-4o",
      "reasoning": "gpt-4o",
      "vector_agent": "gpt-4o",
      "maps_agent": "gpt-4o",
      "stac_agent": "gpt-4o",
      "raster_agent": "gpt-4o",
      "orchestrator_planner": "gpt-4o",
      "orchestrator_progress": "gpt-4o"
    }
  },
  "run_number": 1,
  "started_at": "2026-02-04T10:30:00.000000",
  "completed_at": "2026-02-04T10:32:45.123456",
  "duration_seconds": 165.12,
  "success": true,
  "error": null,
  "num_messages": 15,
  "category": "building_damage_assessment",
  "sub_category": "damage_levels_by_neighborhood",
  "difficulty": "simple",
  "token_usage": {
    "prompt_tokens": 45000,
    "completion_tokens": 1200,
    "total_tokens": 46200
  }
}
```

## State Management

Before each question, the runner resets all state to ensure clean execution:

```python
def reset_state():
    reset_response_store()           # Clear shared response store
    team_state_path.write_text("{}")  # Clear orchestrator state
    history_path.write_text("[]")     # Clear conversation history
```

This ensures each question starts from a clean slate, making runs independent and reproducible.

## Incremental Saving

The runner saves conversation history incrementally after each message:

```python
def save_history_incremental():
    history_file.write_text(json.dumps(history, indent=2))
```

This ensures that even if a run times out or crashes, partial results are preserved for debugging.

## Token Tracking

Tokens are tracked per message and aggregated:

```python
if hasattr(message, 'models_usage') and message.models_usage:
    total_prompt_tokens += message.models_usage.prompt_tokens or 0
    total_completion_tokens += message.models_usage.completion_tokens or 0
```

Token usage is saved in `run_metadata.json` and used by the analysis pipeline for cost comparisons.

## Timeout Handling

Timeouts are checked inside the message stream loop:

```python
async for message in team.run_stream(task=question_text):
    if timeout_seconds and (datetime.now() - start_time).total_seconds() > timeout_seconds:
        timed_out = True
        save_history_incremental()
        break
```

When a timeout occurs:
- `success` is set to `False`
- `error` contains the timeout message
- Partial history is preserved
- The run can be retried with `--resume`

## Resume Logic

The `--resume` flag enables intelligent skipping:

```python
if args.resume and run_number is not None:
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("success"):
        print(f"Skipping {qid} (run_{run_number} succeeded)")
        continue
    else:
        print(f"Retrying {qid} (run_{run_number} failed previously)")
```

Only **successful** runs are skipped; failed or timed-out runs are retried.

## Execution Flow

1. **Parse Arguments**: Determine questions, config, run number
2. **Load Questions**: Read from `benchmark_questions_v2_compiled.json`
3. **Apply Config**: Set environment variables for LLM models
4. **For Each Question**:
   - Check skip/resume conditions
   - Reset state
   - Create team with configured models
   - Execute question with timeout
   - Save results (history, metadata, artifacts)
   - Track tokens and duration
5. **Print Summary**: Success rate, total tokens, durations

## Adding New Configurations

To add a new LLM configuration:

```python
LLM_CONFIGS["my-new-config"] = LLMConfig(
    name="my-new-config",
    description="Description for logging",
    default_model="gpt-4o",
    reasoning_model="gpt-5.1",
    vector_agent="gpt-4o",
    maps_agent="gpt-4o",
    stac_agent="gpt-5.1",  # Use stronger model for STAC
    raster_agent="gpt-5.1",
    orchestrator_planner="gpt-5.1",
    orchestrator_progress="gpt-4o",
)
```

## Integration with Analysis Pipeline

After running evaluations, use the analysis pipeline:

```bash
# Run LLM-as-Judge evaluation
python runtime/eval_scripts/run_llm_judge.py --config all-gpt4o

# Analyze results across runs
python runtime/eval_scripts/analyze_results.py -c all-gpt4o

# Generate figures for paper
python runtime/eval_scripts/generate_figures.py
```

See [LLM_AS_JUDGE_EVALUATION.md](./LLM_AS_JUDGE_EVALUATION.md) for evaluation methodology details.

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Question not found" | Check question exists in `benchmark_questions_v2_compiled.json` |
| Timeout on all questions | Increase `--timeout` or check network/API issues |
| "No valid questions to run" | Ensure ground truths exist in `benchmark_gt/` |
| Resume not skipping | Check `run_metadata.json` has `"success": true` |

### Debugging

```bash
# Quick test with short timeout
python runtime/eval_scripts/run_benchmark_eval_v2.py --question Q001 --timeout-seconds 60

# Check what would run without running
python runtime/eval_scripts/run_benchmark_eval_v2.py --list

# View a specific run's output
cat data/benchmarks/geofaham/benchmark_eval/all-gpt4o/Q001/run_1/run_metadata.json | jq .
```
