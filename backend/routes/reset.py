# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Reset application state.
"""
import logging
import os
import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from agents.core.response_store import get_response_store
from backend.services.chat_tasks import stop_chat_tasks

from backend.routes.config import (
    TEAM_STATE_PATH,
    CONVERSATION_HISTORY_PATH,
    ARTIFACTS_LEDGER_PATH,
    RESPONSE_STORE_PATH
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
        # Stop writers before clearing their state, including polling jobs.
        await stop_chat_tasks()
        from backend.routes.polling import _sessions
        _sessions.clear()
        get_response_store().clear()
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
