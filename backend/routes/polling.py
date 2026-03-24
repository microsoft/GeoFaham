# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
HTTP Polling routes - fallback transport when WebSocket is unavailable.

Provides session-based request/response polling as an alternative to the
WebSocket chat endpoint.  The frontend tries WebSocket first and falls back
to these endpoints automatically.

Endpoints
---------
POST /api/polling/init   – create a polling session, returns session_id
POST /api/polling/send   – submit a user message to the agent
GET  /api/polling/poll   – retrieve queued agent responses
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Any

import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    TextMessage,
    UserInputRequestedEvent,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
)
from autogen_core import CancellationToken
from autogen_core.models import RequestUsage

from agents import get_team, create_single_agent
from agents.core.types import GeoFahamToolResponse
from agents.core.response_store import get_response_store
from agents.shared.geojson import generate_response_id, results_to_geojson
from backend.routes.config import TEAM_STATE_PATH, CONVERSATION_HISTORY_PATH
from backend.routes.history import get_history
from backend.routes.websocket import APIResponse, MessageProcessor, save_user_raw_geojson

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/polling", tags=["polling"])

VALID_MODES = ["multi-agent", "postgis", "map_search", "stac", "raster_ops"]

# ---------------------------------------------------------------------------
# In-memory session store  (sufficient for single-process deployments)
# ---------------------------------------------------------------------------
_sessions: dict[str, "PollingSession"] = {}


class PollingSession:
    """Manages agent state and a message queue for one polling client."""

    def __init__(self, mode: str):
        self.mode = mode if mode in VALID_MODES else "multi-agent"
        self.team = None
        self.history: list = []
        self.outbox: asyncio.Queue[dict] = asyncio.Queue()
        self.busy = False  # True while an agent run is in progress

    async def initialize(self):
        self.history = await get_history()
        if self.mode == "multi-agent":
            self.team = await get_team(self._user_input)
        else:
            self.team = create_single_agent(self.mode)

    async def _user_input(self, prompt: str, cancellation_token: CancellationToken | None) -> str:
        """Placeholder – polling mode does not support mid-run user prompts."""
        raise NotImplementedError("Interactive user input is not supported in polling mode.")

    async def enqueue(self, response: APIResponse):
        await self.outbox.put(jsonable_encoder(response.model_dump()))

    async def drain(self) -> list[dict]:
        msgs: list[dict] = []
        while not self.outbox.empty():
            msgs.append(self.outbox.get_nowait())
        return msgs

    async def process_message(self, data: dict):
        """Run the agent stream in the background, pushing responses to the outbox."""
        self.busy = True
        try:
            # Handle user raw JSON upload
            if data.get("user_raw_json", ""):
                user_raw_geojson_path = await save_user_raw_geojson(data.get("user_raw_json"))
                data.pop("user_raw_json")
                data["content"] += f"\n\n User_JSON_START {user_raw_geojson_path} User_JSON_END"

            request = TextMessage.model_validate(data)
            start_time = time.time()
            total_usage = RequestUsage(prompt_tokens=0, completion_tokens=0)

            async for message in self.team.run_stream(task=request):
                if not isinstance(message, TaskResult):
                    self.history.append(message.model_dump(mode="json"))
                    if hasattr(message, "models_usage") and message.models_usage:
                        total_usage.prompt_tokens += message.models_usage.prompt_tokens
                        total_usage.completion_tokens += message.models_usage.completion_tokens

                response = await self._process_stream_message(message, start_time, total_usage)
                if response:
                    await self.enqueue(response)

            await self._save_state()
        except Exception as e:
            logger.error(f"Polling process_message error: {e}")
            await self.enqueue(APIResponse(type="error", error_message=str(e), source="system"))
        finally:
            self.busy = False

    async def _process_stream_message(
        self, message: Any, start_time: float, total_usage: RequestUsage
    ) -> APIResponse | None:
        if isinstance(message, ToolCallRequestEvent):
            return await MessageProcessor.process_tool_call_request(message)
        elif isinstance(message, UserInputRequestedEvent):
            return await MessageProcessor.process_user_input_requested(message)
        elif isinstance(message, ToolCallExecutionEvent):
            return await MessageProcessor.process_tool_execution(message)
        elif isinstance(message, TextMessage):
            return await MessageProcessor.process_text_message(message)
        elif isinstance(message, TaskResult):
            duration = time.time() - start_time
            resp = MessageProcessor.process_task_result(message, duration, total_usage)
            self.history.append({"type": "TextMessage", "source": "system", "content": resp.data})
            return resp
        else:
            return APIResponse(type="data", data=getattr(message, "content", str(message)))

    async def _save_state(self):
        try:
            async with aiofiles.open(TEAM_STATE_PATH, "w") as f:
                state = await self.team.save_state()
                await f.write(json.dumps(state))
            async with aiofiles.open(CONVERSATION_HISTORY_PATH, "w") as f:
                await f.write(json.dumps(self.history, indent=2))
        except Exception as e:
            logger.error(f"Error saving polling session state: {e}")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class InitRequest(BaseModel):
    mode: str = "multi-agent"


class InitResponse(BaseModel):
    session_id: str


class SendRequest(BaseModel):
    session_id: str
    content: str
    user_raw_json: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/init", response_model=InitResponse)
async def polling_init(req: InitRequest):
    """Create a new polling session and initialize the agent team."""
    session_id = str(uuid.uuid4())
    session = PollingSession(req.mode)
    _sessions[session_id] = session

    try:
        await session.initialize()
    except Exception as e:
        _sessions.pop(session_id, None)
        raise HTTPException(status_code=500, detail=f"Failed to initialize session: {e}")

    logger.info(f"Polling session created: {session_id} mode={req.mode}")
    return InitResponse(session_id=session_id)


@router.post("/send")
async def polling_send(req: SendRequest):
    """Submit a user message. Processing runs in the background."""
    session = _sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.busy:
        raise HTTPException(status_code=429, detail="Agent is still processing a previous message")

    data: dict[str, Any] = {"content": req.content, "source": "user"}
    if req.user_raw_json:
        data["user_raw_json"] = req.user_raw_json

    # Fire-and-forget the agent run so we can return immediately
    asyncio.create_task(session.process_message(data))
    return {"status": "accepted"}


@router.get("/poll")
async def polling_poll(session_id: str):
    """Return all queued messages for the given session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await session.drain()
    return {"messages": messages}
