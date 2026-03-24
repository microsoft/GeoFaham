# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
WebSocket routes - main chat handler and user GeoJSON processing.
"""
import json
import logging
import time
from dataclasses import asdict
from typing import AsyncIterator, Any

import aiofiles
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import TextMessage, UserInputRequestedEvent, ToolCallExecutionEvent, ToolCallRequestEvent
from autogen_core import CancellationToken
from autogen_core.models import RequestUsage

from agents import get_team, create_single_agent
from agents.core.types import GeoFahamToolResponse
from agents.core.response_store import get_response_store
from agents.shared.geojson import generate_response_id, results_to_geojson
from backend.routes.config import TEAM_STATE_PATH, CONVERSATION_HISTORY_PATH
from backend.routes.history import get_history
from backend.routes.utils import clusters2bounds

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_MODES = ["multi-agent", "postgis", "map_search", "stac", "raster_ops"]


class APIResponse(BaseModel):
    """
    Standard API response format for WebSocket messages.
    
    This model aligns with GeoFahamToolResponse schema to ensure frontend
    receives consistent structure regardless of response type.
    """
    finished: bool = False
    source: str | None = None
    type: str | None = None          # "layer", "data", "error", "empty"
    data_type: str | None = None     # "vector", "raster", "timeline", etc.
    data: dict | list | str | None = None
    metadata: dict | None = None     # Additional context (bbox, visualization_hints, etc.)
    artifact: dict | None = None     # File artifact info (path, features_count, etc.)
    summary: str | None = None       # Human-readable description
    error_message: str | None = None # Error details when type="error"
    debug_msg: bool = True


# =============================================================================
# MESSAGE PROCESSORS (Single Responsibility)
# =============================================================================

class MessageProcessor:
    """Processes different message types from agent stream."""
    
    @staticmethod
    async def process_tool_call_request(message: ToolCallRequestEvent) -> APIResponse:
        """Process tool call request - shows what tool is being called."""
        content = message.content[0]
        return APIResponse(
            type='data',
            data=asdict(content),
            source=message.source,
            debug_msg=True
        )
    
    @staticmethod
    async def process_user_input_requested(message: UserInputRequestedEvent) -> APIResponse:
        """Process user input request - prompts frontend to enable input."""
        return APIResponse(
            type='UserInputRequestedEvent',
            data=message.to_text(),
            source=message.source,
            debug_msg=False
        )
    
    @staticmethod
    async def process_tool_execution(message: ToolCallExecutionEvent) -> APIResponse:
        """Process tool execution result - the main response handler."""
        content = message.content[0]
        
        try:
            parsed = json.loads(content.content)
        except Exception:
            return APIResponse(
                type='error',
                error_message="Error parsing tool execution json content.",
                data=str(content.content),
                source=message.source
            )
        
        response = APIResponse(
            type=parsed.get('type', 'data'),
            data_type=parsed.get('data_type'),
            summary=parsed.get('summary'),
            artifact=parsed.get('artifact'),
            metadata=parsed.get('metadata'),
            source=message.source
        )
        
        if response.type == 'error':
            response.error_message = parsed.get('error_message', 'Error occurred during tool execution.')
            response.data = None
        elif response.type == 'layer' and parsed.get('data_type') == 'vector':
            # For vector layers, load GeoJSON file inline
            response.data = await MessageProcessor._load_vector_layer(parsed.get('artifact', {}))
        elif response.type == 'layer' and parsed.get('data_type') == 'timeline':
            # For timeline layers, load GeoJSON file inline (same as vector)
            response.data = await MessageProcessor._load_vector_layer(parsed.get('artifact', {}))
        elif response.type == 'layer':
            # For raster layers, pass data through
            response.data = parsed.get('data', [])
        else:
            response.data = parsed.get('data', {})
        
        return response
    
    @staticmethod
    async def _load_vector_layer(artifact: dict) -> dict | None:
        """Load GeoJSON from artifact path."""
        path = artifact.get('path')
        if not path:
            return None
        
        try:
            async with aiofiles.open(path, 'r') as f:
                return json.loads(await f.read())
        except Exception as e:
            logger.error(f"Error reading vector layer: {e}")
            return None
    
    @staticmethod
    async def process_text_message(message: TextMessage) -> APIResponse | None:
        """Process text message from agent."""
        if message.source == 'user':
            return None  # Skip user messages
        
        is_debug = "validation_checks" in str(message.content)[:100]
        return APIResponse(
            type='data',
            data=message.content,
            source=message.source,
            debug_msg=is_debug
        )
    
    @staticmethod
    def process_task_result(message: TaskResult, duration: float, usage: RequestUsage) -> APIResponse:
        """Process task completion result."""
        output = (
            f"{'-' * 10} Summary {'-' * 10}\n"
            f"Number of messages: {len(message.messages)}\n"
            f"Finish reason: {message.stop_reason}\n"
            f"Total prompt tokens: {usage.prompt_tokens}\n"
            f"Total completion tokens: {usage.completion_tokens}\n"
            f"Duration: {duration:.2f} seconds\n"
        )
        return APIResponse(
            finished=True,
            type='data',
            data=output,
            source='system'
        )


# =============================================================================
# CHAT SESSION MANAGER
# =============================================================================

class ChatSession:
    """Manages a single WebSocket chat session."""
    
    def __init__(self, websocket: WebSocket, mode: str):
        self.websocket = websocket
        self.mode = mode if mode in VALID_MODES else "multi-agent"
        self.team = None
        self.history = []
    
    async def initialize(self):
        """Initialize the chat session - create team once."""
        self.history = await get_history()
        
        if self.mode == "multi-agent":
            self.team = await get_team(self._user_input)
        else:
            self.team = create_single_agent(self.mode)
    
    async def _user_input(self, prompt: str, cancellation_token: CancellationToken | None) -> str:
        """Callback for when agent requests user input."""
        data = await self.websocket.receive_json()
        message = TextMessage.model_validate(data)
        return message.content
    
    async def send_response(self, response: APIResponse):
        """Send response to client."""
        await self.websocket.send_json(jsonable_encoder(response.model_dump()))
    
    async def process_message(self, data: dict) -> AsyncIterator[APIResponse]:
        """Process a single user message and yield responses."""
        # Handle user raw JSON upload
        if data.get("user_raw_json", ""):
            user_raw_geojson_path = await save_user_raw_geojson(data.get("user_raw_json"))
            data.pop("user_raw_json")
            data['content'] += f"\n\n User_JSON_START {user_raw_geojson_path} User_JSON_END"
        
        request = TextMessage.model_validate(data)
        
        start_time = time.time()
        total_usage = RequestUsage(prompt_tokens=0, completion_tokens=0)
        
        async for message in self.team.run_stream(task=request):
            logger.debug(f"Message: {message}")
            
            # Track history and usage
            if not isinstance(message, TaskResult):
                self.history.append(message.model_dump(mode='json'))
                if hasattr(message, 'models_usage') and message.models_usage:
                    total_usage.prompt_tokens += message.models_usage.prompt_tokens
                    total_usage.completion_tokens += message.models_usage.completion_tokens
            
            # Process message by type
            response = await self._process_stream_message(message, start_time, total_usage)
            if response:
                yield response
    
    async def _process_stream_message(
        self, message: Any, start_time: float, total_usage: RequestUsage
    ) -> APIResponse | None:
        """Route message to appropriate processor."""
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
            response = MessageProcessor.process_task_result(message, duration, total_usage)
            # Store summary as system message in history
            self.history.append({
                "type": "TextMessage",
                "source": "system",
                "content": response.data,
            })
            return response
        else:
            return APIResponse(type='data', data=getattr(message, 'content', str(message)))
    
    async def save_state(self):
        """Persist team state and history."""
        try:
            logger.info(f"Saving team state to {TEAM_STATE_PATH}")
            async with aiofiles.open(TEAM_STATE_PATH, "w") as file:
                state = await self.team.save_state()
                await file.write(json.dumps(state))
            
            logger.info(f"Saving conversation history to {CONVERSATION_HISTORY_PATH}")
            async with aiofiles.open(CONVERSATION_HISTORY_PATH, "w") as file:
                await file.write(json.dumps(self.history, indent=2))
        except Exception as e:
            logger.error(f"Error saving state: {e}")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def save_user_raw_geojson(data: str) -> str:
    """Process and save user-uploaded raw GeoJSON data."""
    geojson_result = json.loads(data)
    artifact = await results_to_geojson(geojson_result)
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


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@router.websocket("/ws/chat")
async def chat(websocket: WebSocket, mode: str = "multi-agent"):
    """
    WebSocket endpoint for chat with mode-based agent selection.
    
    Query params:
        mode: Agent mode - "multi-agent", "postgis", "map_search", "stac", or "raster_ops"
    """
    logger.info(f"WebSocket connection request received with mode: {mode}")
    await websocket.accept()
    
    session = ChatSession(websocket, mode)
    
    try:
        # Send immediate status so the connection is not idle during init
        await websocket.send_json({"type": "status", "data": "Initializing agents...", "source": "system", "finished": False, "debug_msg": True})
        await session.initialize()
        await websocket.send_json({"type": "status", "data": "Agents ready.", "source": "system", "finished": False, "debug_msg": True})
        
        while True:
            # Wait for user message
            data = await websocket.receive_json()
            logger.debug(f"Received data: {data}")
            
            try:
                # Process message and send responses
                async for response in session.process_message(data):
                    await session.send_response(response)
                    
                    # Handle special case: user input requested
                    if response.type == 'UserInputRequestedEvent':
                        continue  # Don't save state yet, waiting for input
                
                # Save state after successful message processing
                await session.save_state()
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await session.send_response(APIResponse(
                    type='error',
                    error_message=f"Error: {str(e)}",
                    source='system'
                ))
                # Re-enable input after error
                await session.send_response(APIResponse(
                    type='UserInputRequestedEvent',
                    data="An error occurred. Please try again.",
                    source='system'
                ))
    
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        try:
            await session.send_response(APIResponse(
                type='error',
                error_message=f"Unexpected error: {str(e)}",
                source='system'
            ))
        except Exception:
            pass  # Client already disconnected
