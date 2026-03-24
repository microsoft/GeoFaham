# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Benchmark routes - save ground truth and reset application state.
"""
import json
import logging
import os
import shutil
import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.routes.config import (
    TEAM_STATE_PATH, 
    CONVERSATION_HISTORY_PATH,
    ARTIFACTS_LEDGER_PATH,
    RESPONSE_STORE_PATH,
    BENCHMARK_GT_PATH
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/reset")
async def reset_application():
    """
    Reset the application by clearing conversation history and team state.
    This allows the team to start fresh without any previous context.
    """
    try:
        # Clear conversation history
        if os.path.exists(CONVERSATION_HISTORY_PATH):
            async with aiofiles.open(CONVERSATION_HISTORY_PATH, 'w') as f:
                await f.write('[]')
            logger.info(f"Cleared conversation history: {CONVERSATION_HISTORY_PATH}")
        
        # Clear team state
        if os.path.exists(TEAM_STATE_PATH):
            async with aiofiles.open(TEAM_STATE_PATH, 'w') as f:
                await f.write('{}')
            logger.info(f"Cleared team state: {TEAM_STATE_PATH}")

        if os.path.exists(ARTIFACTS_LEDGER_PATH):
            async with aiofiles.open(ARTIFACTS_LEDGER_PATH, 'w') as f:
                await f.write('')
            logger.info(f"Cleared artifacts ledger: {ARTIFACTS_LEDGER_PATH}")

        # Clear response store
        if os.path.exists(RESPONSE_STORE_PATH):
            async with aiofiles.open(RESPONSE_STORE_PATH, 'w') as f:
                await f.write('')
            logger.info(f"Cleared response store: {RESPONSE_STORE_PATH}")

        return JSONResponse(content={
            "success": True,
            "message": "Application reset successfully. Conversation history and team state cleared."
        })
        
    except Exception as e:
        logger.error(f"Error resetting application: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset application: {str(e)}")


class SaveBenchmarkRequest(BaseModel):
    question_number: str  # e.g., "Q001"


@router.post("/api/save-benchmark-gt")
async def save_benchmark_ground_truth(request: SaveBenchmarkRequest):
    """
    Save current conversation state as benchmark ground truth.
    Creates a folder structure: benchmark_gt/{question_number}/run_X/
    and copies conversation_history.json, team_state.json, and response_store.jsonl.
    """
    try:
        question_number = request.question_number.strip().upper()
        if not question_number:
            raise HTTPException(status_code=400, detail="Question number is required")
        
        # Create benchmark_gt directory if not exists
        os.makedirs(BENCHMARK_GT_PATH, exist_ok=True)
        
        # Create question folder
        question_folder = os.path.join(BENCHMARK_GT_PATH, question_number)
        os.makedirs(question_folder, exist_ok=True)
        
        # Determine run number by checking existing run folders
        existing_runs = [d for d in os.listdir(question_folder) 
                        if os.path.isdir(os.path.join(question_folder, d)) and d.startswith('run_')]
        if existing_runs:
            run_numbers = [int(d.replace('run_', '')) for d in existing_runs if d.replace('run_', '').isdigit()]
            next_run = max(run_numbers) + 1 if run_numbers else 1
        else:
            next_run = 1
        
        # Create run folder
        run_folder = os.path.join(question_folder, f'run_{next_run}')
        os.makedirs(run_folder, exist_ok=True)

        # create a artifacts folder in run folder
        artifacts_folder = os.path.join(run_folder, "artifacts")
        os.makedirs(artifacts_folder, exist_ok=True)
        
        files_copied = []
        
        # Copy conversation_history.json
        if os.path.exists(CONVERSATION_HISTORY_PATH):
            dest = os.path.join(run_folder, 'conversation_history.json')
            shutil.copy2(CONVERSATION_HISTORY_PATH, dest)
            files_copied.append('conversation_history.json')
            logger.info(f"Copied conversation history to {dest}")
        
        # Copy team_state.json
        if os.path.exists(TEAM_STATE_PATH):
            dest = os.path.join(run_folder, 'team_state.json')
            shutil.copy2(TEAM_STATE_PATH, dest)
            files_copied.append('team_state.json')
            logger.info(f"Copied team state to {dest}")
        
        # Copy response_store.jsonl
        if os.path.exists(RESPONSE_STORE_PATH):
            dest = os.path.join(run_folder, 'response_store.jsonl')
            shutil.copy2(RESPONSE_STORE_PATH, dest)
            files_copied.append('response_store.jsonl')
            logger.info(f"Copied response store to {dest}")
            # open and copy artifacts to artifacts folder
            with open(RESPONSE_STORE_PATH, "r") as f:
                response_store = [json.loads(line) for line in f]
                for resp in response_store:
                    try:
                        if resp['response']['artifact']['path']:
                            shutil.copy2(resp['response']['artifact']['path'], artifacts_folder)
                    except Exception as e:
                        logger.error(f"Error copying artifact from response store in benchmark GT: {str(e)}")
        
        return JSONResponse(content={
            "success": True,
            "message": f"Benchmark GT saved successfully",
            "question_number": question_number,
            "run_number": next_run,
            "path": run_folder,
            "files_copied": files_copied
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving benchmark GT: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save benchmark GT: {str(e)}")
