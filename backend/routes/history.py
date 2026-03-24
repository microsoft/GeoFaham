# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Chat history routes - getting and managing conversation history.
"""
import json
import logging
import os
from typing import Any
import aiofiles
from fastapi import APIRouter

from backend.routes.config import CONVERSATION_HISTORY_PATH

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_history() -> list[dict[str, Any]]:
    """Get chat history from file."""
    if not os.path.exists(CONVERSATION_HISTORY_PATH):
        return []
    async with aiofiles.open(CONVERSATION_HISTORY_PATH, "r") as file:
        try:
            content = await file.read()
            history = json.loads(content)
            return history
        except Exception as e:
            logger.error(f"Error reading conversation history: {str(e)}")
            return []


@router.get("/history")
async def history() -> list[dict[str, Any]]:
    """API endpoint to get chat history."""
    try:
        return await get_history()
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        return []
