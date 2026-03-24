# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
UnivEARTH Benchmark Test Script

Processes questions from data_with_geojson.json, sends them to the agent team,
and saves chat history, state, and response store for each question.

Usage:
    python -m tests.test_univearth_benchmark                    # Process all questions
    python -m tests.test_univearth_benchmark --id Q005          # Process specific question by ID
    python -m tests.test_univearth_benchmark --start 10         # Start from index 10
    python -m tests.test_univearth_benchmark --end 20           # Process up to index 20
    python -m tests.test_univearth_benchmark --force            # Reprocess existing
    python -m tests.test_univearth_benchmark --no-reset         # Don't reset before processing (for followup)
"""

import asyncio
import argparse
import json
import os
import sys
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, Any, Dict

# Auto-load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from autogen_core.models import RequestUsage

from agents import get_team
from agents.core.config import get_config
from agents.core.response_store import get_response_store, reset_response_store
from agents.shared.geojson import results_to_geojson, generate_response_id
from agents.core.types import GeoFahamToolResponse
from backend.routes.config import (
    TEAM_STATE_PATH,
    CONVERSATION_HISTORY_PATH,
    ARTIFACTS_LEDGER_PATH,
    RESPONSE_STORE_PATH
)


# Constants
BENCHMARK_DATA_DIR = Path(__file__).parent.parent / "data" / "benchmarks" / "UnivEARTH"
INPUT_FILE = BENCHMARK_DATA_DIR / "data_with_geojson.json"
OUTPUT_DIR = BENCHMARK_DATA_DIR / "benchmark_results"


def load_benchmark_data() -> list:
    """Load benchmark questions from JSON file."""
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_question_output_dir(question_id: str) -> Path:
    """Get output directory for a specific question ID."""
    return OUTPUT_DIR / question_id


def is_question_processed(question_id: str) -> bool:
    """Check if a question has already been processed."""
    output_dir = get_question_output_dir(question_id)
    return output_dir.exists() and (output_dir / "chat_history.json").exists()


def reset_application_state():
    """
    Reset the application by clearing conversation history, team state,
    artifacts ledger, and response store. Same as backend/routes/benchmark.py reset.
    """
    print("  Resetting application state...")
    
    # Clear conversation history
    if os.path.exists(CONVERSATION_HISTORY_PATH):
        with open(CONVERSATION_HISTORY_PATH, 'w') as f:
            f.write('[]')
    
    # Clear team state
    if os.path.exists(TEAM_STATE_PATH):
        with open(TEAM_STATE_PATH, 'w') as f:
            f.write('{}')
    
    # Clear artifacts ledger
    if os.path.exists(ARTIFACTS_LEDGER_PATH):
        with open(ARTIFACTS_LEDGER_PATH, 'w') as f:
            f.write('')
    
    # Clear response store
    if os.path.exists(RESPONSE_STORE_PATH):
        with open(RESPONSE_STORE_PATH, 'w') as f:
            f.write('')
    
    # Also reset the in-memory response store
    reset_response_store()


async def save_user_geojson(geojson: dict) -> str:
    """
    Save user GeoJSON using the same method as websocket.py.
    Uses results_to_geojson to save the file and create artifact.
    Returns the GeoFahamToolResponse JSON string.
    """
    artifact = await results_to_geojson(geojson)
    response_id = generate_response_id()
    response = GeoFahamToolResponse(
        source="user",
        response_id=response_id,
        type="layer",
        data_type="vector",
        summary="uploaded by user",
        artifact=artifact
    )
    # Store in response store so agents can access it via get_available_responses()
    get_response_store().store(response)
    return response.model_dump_json()


async def dummy_user_input(prompt: str, cancellation_token: Optional[CancellationToken] = None) -> str:
    """Dummy user input function - not used in benchmark."""
    return ""


async def process_question(
    item: dict,
    force: bool = False,
    reset: bool = True
) -> dict:
    """
    Process a single benchmark question.
    
    Args:
        item: Question item dict from benchmark data
        force: Force reprocess even if already completed
        reset: Reset application state before processing (default True)
    
    Returns:
        Dict with processing results
    """
    question_id = item.get("question_id")
    output_dir = get_question_output_dir(question_id)
    
    # Check if already processed
    if not force and is_question_processed(question_id):
        print(f"  Skipping - already processed (use --force to reprocess)")
        return {"status": "skipped", "question_id": question_id}
    
    # Reset application state if requested (default behavior)
    if reset:
        reset_application_state()
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get the question text
    question = item.get("modified_question") or item.get("question")
    geojson = item.get("geojson")
    
    # Prepare the task message
    task_content = question
    
    # If there's a GeoJSON, save it using results_to_geojson (same as websocket.py)
    if geojson:
        geojson_msg = await save_user_geojson(geojson)
        task_content += f"\n\n User_JSON_START {geojson_msg} User_JSON_END"
    
    # Create team
    team = await get_team(dummy_user_input)
    
    # Track metrics
    start_time = time.time()
    total_usage = RequestUsage(prompt_tokens=0, completion_tokens=0)
    history = []
    
    print(f"  Running agent team...")
    
    try:
        # Run the team
        async for message in team.run_stream(task=task_content):
            if not isinstance(message, TaskResult):
                print(message)
                history.append(message.model_dump(mode='json'))
                if hasattr(message, 'models_usage') and message.models_usage:
                    total_usage.prompt_tokens += message.models_usage.prompt_tokens
                    total_usage.completion_tokens += message.models_usage.completion_tokens
        
        duration = time.time() - start_time
        
        # Save team state
        state = await team.save_state()
        with open(output_dir / "team_state.json", 'w') as f:
            json.dump(state, f, indent=2)
        
        # Save chat history
        with open(output_dir / "chat_history.json", 'w') as f:
            json.dump(history, f, indent=2)
        
        # Save response store
        response_store = get_response_store()
        with open(output_dir / "response_store.json", 'w') as f:
            json.dump(response_store.to_dict(), f, indent=2)
        
        # Save metadata
        metadata = {
            "question_id": question_id,
            "original_question": item.get("question"),
            "modified_question": item.get("modified_question"),
            "has_geojson": geojson is not None,
            "expected_answer": item.get("answer"),
            "tag": item.get("tag"),
            "url": item.get("url"),
            "duration_seconds": duration,
            "prompt_tokens": total_usage.prompt_tokens,
            "completion_tokens": total_usage.completion_tokens,
            "message_count": len(history)
        }
        with open(output_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"  Completed in {duration:.1f}s ({len(history)} messages)")
        return {"status": "success", "question_id": question_id, "duration": duration}
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        print(f"  Error: {error_msg}")
        
        # Save error info
        with open(output_dir / "error.json", 'w') as f:
            json.dump({
                "error": error_msg,
                "question_id": question_id,
                "duration_seconds": duration
            }, f, indent=2)
        
        return {"status": "error", "question_id": question_id, "error": error_msg}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="UnivEARTH Benchmark Test - Process questions through agent team"
    )
    parser.add_argument(
        "--id",
        type=str,
        help="Process specific question by ID (e.g., Q005)",
        default="Q003"
    )
    parser.add_argument(
        "--start", "-s",
        type=int,
        default=0,
        help="Start processing from this index (default: 0)"
    )
    parser.add_argument(
        "--end", "-e",
        type=int,
        help="Stop processing at this index (exclusive)"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reprocess already completed questions"
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset application state before processing (for followup questions)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all questions and their status"
    )
    
    args = parser.parse_args()
    
    # Load data
    print(f"Loading benchmark data from {INPUT_FILE}")
    data = load_benchmark_data()
    print(f"Loaded {len(data)} questions")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build question_id to item mapping
    id_to_item = {item.get("question_id"): item for item in data}
    
    # List mode
    if args.list:
        print("\n" + "=" * 70)
        print("Question Status")
        print("=" * 70)
        for item in data:
            qid = item.get("question_id")
            status = "✓" if is_question_processed(qid) else "○"
            has_geo = "📍" if item.get("geojson") else "  "
            q = item.get("question", "")[:50]
            print(f"{status} {has_geo} [{qid}] {q}...")
        
        processed = sum(1 for item in data if is_question_processed(item.get("question_id")))
        print(f"\nProcessed: {processed}/{len(data)}")
        return
    
    # Determine items to process
    if args.id:
        # Process specific question by ID
        if args.id not in id_to_item:
            print(f"Error: Question ID '{args.id}' not found")
            return
        items_to_process = [id_to_item[args.id]]
    else:
        # Process by index range
        end = args.end if args.end else len(data)
        items_to_process = data[args.start:min(end, len(data))]
    
    # Determine reset behavior (default: reset, unless --no-reset specified)
    should_reset = not args.no_reset
    
    print(f"\nProcessing {len(items_to_process)} question(s)")
    if not should_reset:
        print("  (--no-reset: keeping existing application state)")
    print("=" * 70)
    
    results = {"success": 0, "skipped": 0, "error": 0}
    
    for item in items_to_process:
        qid = item.get("question_id")
        q = item.get("question", "")[:60]
        has_geo = "📍" if item.get("geojson") else ""
        print(f"\n[{qid}] {has_geo} {q}...")
        
        result = await process_question(item, force=args.force, reset=should_reset)
        results[result["status"]] += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Success: {results['success']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Errors:  {results['error']}")


if __name__ == "__main__":
    asyncio.run(main())
