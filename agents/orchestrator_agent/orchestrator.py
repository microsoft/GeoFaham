# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import asyncio
import json
import logging
import os
import re
import textwrap
from typing import Any, Dict, List, Mapping, Sequence

from autogen_core import AgentId, CancellationToken, DefaultTopicId, MessageContext, event, rpc
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    LLMMessage,
    UserMessage,
    FunctionExecutionResult
)
from autogen_core.utils import extract_json_from_str

from autogen_agentchat import TRACE_LOGGER_NAME
from autogen_agentchat.base import Response, TerminationCondition
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    HandoffMessage,
    MessageFactory,
    MultiModalMessage,
    SelectSpeakerEvent,
    StopMessage,
    TextMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    ToolCallSummaryMessage,
)
from autogen_agentchat.state import BaseGroupChatManagerState
from autogen_agentchat.utils import remove_images
from autogen_agentchat.teams._group_chat._base_group_chat_manager import BaseGroupChatManager
from autogen_agentchat.teams._group_chat._events import (
    GroupChatAgentResponse,
    GroupChatMessage,
    GroupChatRequestPublish,
    GroupChatReset,
    GroupChatStart,
    GroupChatTeamResponse,
    GroupChatTermination,
    SerializableException,
)
from agents.orchestrator_agent._prompts import (
    AGENT_PLACEHOLDERS,
    ORCHESTRATOR_FINAL_ANSWER_PROMPT,
    ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT,
    ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT,
    ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT,
    ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT,
    ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT,
)
from ._prompt_progress import ORCHESTRATOR_PROGRESS_LEDGER_PROMPT, LedgerEntry
from pydantic import Field
from agents.core.types import GeoFahamToolResponse
from agents.core.response_store import get_response_store
from agents.core.config import get_config

trace_logger = logging.getLogger(TRACE_LOGGER_NAME)

# Load schema from config path
config = get_config()
schema_path = config.paths.schema_cache_path
if schema_path.exists():
    with open(schema_path, 'r') as f:
        schema = json.load(f)
else:
    schema = []

from agents.orchestrator_agent._agent_capabilities import AGENT_CAPABILITIES_DOC, AGENT_NAMES


AGENT_PLACEHOLDERS = {
    "STAC_AGENT": AGENT_NAMES["STAC_AGENT"],
    "MAPS_AGENT": AGENT_NAMES["MAPS_AGENT"], 
    "POSTGIS_AGENT": AGENT_NAMES["VECTOR_AGENT"],
    "RASTER_AGENT": AGENT_NAMES["RASTER_AGENT"],
    "agent_capabilities": AGENT_CAPABILITIES_DOC
}


class GeoFahamOrchestratorState(BaseGroupChatManagerState):
    """State for GeoFaham orchestrator."""

    task: str = Field(default="")
    facts: str = Field(default="")
    plan: str = Field(default="")
    n_rounds: int = Field(default=0)
    n_stalls: int = Field(default=0)
    response_store_data: Dict[str, Any] = Field(default_factory=dict)
    type: str = Field(default="GeoFahamOrchestratorState")



class GeoFahamOrchestrator(BaseGroupChatManager):
    """The GeoFahamOrchestrator manages a group chat with ledger based orchestration."""

    def __init__(
        self,
        name: str,
        group_topic_type: str,
        output_topic_type: str,
        participant_topic_types: List[str],
        participant_names: List[str],
        participant_descriptions: List[str],
        max_turns: int | None,
        message_factory: MessageFactory,
        model_client: ChatCompletionClient,
        model_client2: ChatCompletionClient,
        max_stalls: int,
        final_answer_prompt: str,
        output_message_queue: asyncio.Queue[BaseAgentEvent | BaseChatMessage | GroupChatTermination],
        termination_condition: TerminationCondition | None,
        emit_team_events: bool,
    ):
        super().__init__(
            name,
            group_topic_type,
            output_topic_type,
            participant_topic_types,
            participant_names,
            participant_descriptions,
            output_message_queue,
            termination_condition,
            max_turns,
            message_factory,
            emit_team_events=emit_team_events,
        )
        self._model_client = model_client
        self._model_client2 = model_client2
        self._max_stalls = max_stalls
        self._final_answer_prompt = final_answer_prompt
        self._max_json_retries = 10
        self._task = ""
        self._facts = ""
        self._plan = ""
        self._n_rounds = 0
        self._n_stalls = 0
        self._user_text_msg = ""
        self._agent_responses = {}
        
        # Initialize the response store (shared across all agents)
        self._response_store = get_response_store()
        
        # Track if this is a continuation of previous conversation
        self._is_continuation = False

        # Produce a team description
        self._team_description = ""
        for topic_type, description in zip(self._participant_names, self._participant_descriptions, strict=True):
            self._team_description += re.sub(r"\s+", " ", f"{topic_type}: {description}").strip() + "\n"
        self._team_description = self._team_description.strip()

    def _get_task_ledger_facts_prompt(self, task: str) -> str:
        return ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT.format(task=task)

    def _get_task_ledger_plan_prompt(self, task: str, team: str, facts: str) -> str:
        return ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT.format(task=task, team=team, facts=facts, **AGENT_PLACEHOLDERS)

    def _get_task_ledger_full_prompt(self, task: str, team: str, facts: str, plan: str) -> str:
        return ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT.format(task=task, team=team, facts=facts, plan=plan)

    def _get_progress_ledger_prompt(self, task: str, team: str, names: List[str], agent_capabilities: str) -> str:
        return ORCHESTRATOR_PROGRESS_LEDGER_PROMPT.format(task=task, team=team, names=", ".join(names), agent_capabilities=agent_capabilities)

    def _get_task_ledger_facts_update_prompt(self, task: str, facts: str) -> str:
        return ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT.format(task=task, facts=facts)

    def _get_task_ledger_plan_update_prompt(self, task: str, team: str, facts: str) -> str:
        # Include the full planning guidance in replanning for consistency
        planning_guidance = ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT.format(
            task=task,
            team=team,
            facts=facts,
            **AGENT_PLACEHOLDERS
        )
        return ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT.format(
            task=task,
            team=team,
            facts=facts,
            planning_guidance=planning_guidance
        )

    def _get_final_answer_prompt(self, task: str) -> str:
        if self._final_answer_prompt == ORCHESTRATOR_FINAL_ANSWER_PROMPT:
            return ORCHESTRATOR_FINAL_ANSWER_PROMPT.format(task=task)
        else:
            return self._final_answer_prompt

    async def _log_message(self, log_message: str) -> None:
        trace_logger.debug(log_message)

    @rpc
    async def handle_start(self, message: GroupChatStart, ctx: MessageContext) -> None:  # type: ignore
        """Handle the start of a task."""

        # Check if the conversation has already terminated.
        if self._termination_condition is not None and self._termination_condition.terminated:
            early_stop_message = StopMessage(content="The group chat has already terminated.", source=self._name)
            # Signal termination.
            await self._signal_termination(early_stop_message)
            # Stop the group chat.
            return
        assert message is not None and message.messages is not None

        # Validate the group state given all the messages.
        await self.validate_group_state(message.messages)

        # Log the message to the output topic.
        await self.publish_message(message, topic_id=DefaultTopicId(type=self._output_topic_type))
        # Log the message to the output queue.
        for msg in message.messages:
            await self._output_message_queue.put(msg)
        
        # Check if this is a continuation (message thread already has content)
        self._is_continuation = len(self._message_thread) > 0 or len(self._response_store.get_all()) > 0
        
        # Outer Loop for first time
        # Create the initial task ledger
        # Combine all message contents for task

        self._task = " ".join([msg.to_model_text() for msg in message.messages])
        self._user_text_msg = self._task.split("User_JSON_START")[0].strip()
        self._extract_user_json()
        planning_conversation = self._thread_to_context()  

        # 1. GATHER FACTS
        planning_conversation.append(
            UserMessage(content=self._get_task_ledger_facts_prompt(self._task), source=self._name)
        )
        response = await self._model_client.create(
            self._get_compatible_context(planning_conversation), cancellation_token=ctx.cancellation_token
        )

        assert isinstance(response.content, str)
        self._facts = response.content
        # self._plan = self._facts
        planning_conversation.append(AssistantMessage(content=self._facts, source=self._name))

        # 2. CREATE A PLAN
        # plan based on available information
        planning_conversation.append(
            UserMessage(content=self._get_task_ledger_plan_prompt(self._task, self._team_description, self._facts), source=self._name)
        )
        response = await self._model_client2.create(
            self._get_compatible_context(planning_conversation), cancellation_token=ctx.cancellation_token
        )

        assert isinstance(response.content, str)
        self._plan = response.content

        # Kick things off
        self._n_stalls = 0
        await self._reenter_outer_loop(ctx.cancellation_token)
    def _extract_user_json(self):
        pattern = r"User_JSON_START\s*(.*?)\s*User_JSON_END"
        matches = re.finditer(pattern, self._task, re.DOTALL)

        for match in matches:
            response_json_str = match.group(1).strip()
            try:
                resp_ = GeoFahamToolResponse.model_validate_json(response_json_str)
                self._agent_responses[resp_.response_id] = resp_
                # Also store user uploads in the shared response store
                self._response_store.store(resp_, step_number=0)
            except Exception:
                print("error decoding JSON", response_json_str)

    @event
    async def handle_agent_response(  # type: ignore
        self, message: GroupChatAgentResponse | GroupChatTeamResponse, ctx: MessageContext
    ) -> None:  # type: ignore
        try:  # message.response.chat_message.content this can be loaded by reponse tool
            if isinstance(message, GroupChatTeamResponse):
                should_stop = await self.handle_graph_agent_response(message)
                if should_stop == "stop":
                    return
            else:
                tool_response = None 
                tool_response_sample = None
                delta: List[BaseAgentEvent | BaseChatMessage] = []
                if not isinstance(message, GroupChatAgentResponse):
                    raise RuntimeError("MagenticOneOrchestrator does not support GroupChatTeamResponse messages.")
                if message.response.inner_messages is not None:
                    for inner_message in message.response.inner_messages:
                        if isinstance(inner_message, ToolCallExecutionEvent):
                            response_content = inner_message.content
                            if isinstance(response_content, list):
                                for item in response_content:
                                    try:
                                        tool_response = GeoFahamToolResponse.model_validate_json(item.content)
                                        tool_response_sample = item.content[:100]
                                    except Exception:
                                        pass
                        delta.append(inner_message)
                if tool_response is not None:
                    self._agent_responses[tool_response.response_id] = tool_response
                    self._response_store.store(tool_response, step_number=self._n_rounds)
                if tool_response is not None and tool_response_sample is not None and tool_response_sample not in message.response.chat_message.content:
                    message.response.chat_message.content = f"Response: {tool_response} \n \n Summary: {message.response.chat_message.content}"
                await self.update_message_thread([message.response.chat_message])
                delta.append(message.response.chat_message)


                if self._termination_condition is not None:
                    stop_message = await self._termination_condition(delta)
                    if stop_message is not None:
                        # Reset the termination conditions.
                        await self._termination_condition.reset()
                        # Signal termination.
                        await self._signal_termination(stop_message)
                        return

            await self._orchestrate_step(ctx.cancellation_token)
        except Exception as e:
            error = SerializableException.from_exception(e)
            await self._signal_termination_with_error(error)
            # Raise the error to the runtime.
            raise
    
    async def handle_graph_agent_response(self,  message: GroupChatTeamResponse) -> None:
        tool_response = None
        tool_response_sample = None
        delta: List[BaseAgentEvent | BaseChatMessage] = []
        if message.result.messages is not None:
            for inner_message in message.result.messages:
                if isinstance(inner_message, ToolCallExecutionEvent):
                    response_content = inner_message.content
                    if isinstance(response_content, list):
                        for item in response_content:
                            try:
                                tool_response = GeoFahamToolResponse.model_validate_json(item.content)
                                tool_response_sample = item.content[:100]
                            except Exception:
                                pass
                delta.append(inner_message)
        if tool_response is not None:
            self._agent_responses[tool_response.response_id] = tool_response
            self._response_store.store(tool_response, step_number=self._n_rounds)
        summary_msg = message.result.messages[-1] if isinstance(message.result.messages[-1], ToolCallSummaryMessage) else None
        if summary_msg is not None:
            if tool_response_sample not in summary_msg.content and tool_response is not None:
                summary_msg = f"Response: {tool_response} \n \n Summary: {summary_msg}"
            await self.update_message_thread([summary_msg])
        elif tool_response is not None:
            await self.update_message_thread([tool_response])
        else:
            await self.update_message_thread(message.result.messages)

        if self._termination_condition is not None:
            stop_message = await self._termination_condition(delta)
            if stop_message is not None:
                await self._termination_condition.reset()
                await self._signal_termination(stop_message)
                return "stop"
        return None

    async def validate_group_state(self, messages: List[BaseChatMessage] | None) -> None:
        pass

    async def save_state(self) -> Mapping[str, Any]:
        state = GeoFahamOrchestratorState(
            message_thread=[msg.dump() for msg in self._message_thread],
            current_turn=self._current_turn,
            task=self._task,
            facts=self._facts,
            plan=self._plan,
            n_rounds=self._n_rounds,
            n_stalls=self._n_stalls,
            response_store_data=self._response_store.to_dict(),
        )
        return state.model_dump()

    async def load_state(self, state: Mapping[str, Any]) -> None:
        orchestrator_state = GeoFahamOrchestratorState.model_validate(state)
        self._message_thread = [self._message_factory.create(message) for message in orchestrator_state.message_thread]
        self._current_turn = orchestrator_state.current_turn
        self._task = orchestrator_state.task
        self._facts = orchestrator_state.facts
        self._plan = orchestrator_state.plan
        self._n_rounds = orchestrator_state.n_rounds
        self._n_stalls = orchestrator_state.n_stalls
        self._response_store.from_dict(orchestrator_state.response_store_data)
        self._agent_responses = {resp.response_id: resp for resp in self._response_store.get_all()}

    async def select_speaker(self, thread: Sequence[BaseAgentEvent | BaseChatMessage]) -> List[str] | str:
        """Not used in this orchestrator, we select next speaker in _orchestrate_step."""
        return [""]

    async def reset(self) -> None:
        """Reset the group chat manager."""
        self._message_thread.clear()
        if self._termination_condition is not None:
            await self._termination_condition.reset()
        self._n_rounds = 0
        self._n_stalls = 0
        self._task = ""
        self._facts = ""
        self._plan = ""
        self._response_store.clear()
        self._is_continuation = False

    async def _reenter_outer_loop(self, cancellation_token: CancellationToken) -> None:
        """Re-enter Outer loop of the orchestrator after creating task ledger."""
        # Only reset agents and clear thread if this is NOT a continuation
        if not self._is_continuation:
            # Reset the agents
            for participant_topic_type in self._participant_name_to_topic_type.values():
                await self._runtime.send_message(
                    GroupChatReset(),
                    recipient=AgentId(type=participant_topic_type, key=self.id.key),
                    cancellation_token=cancellation_token,
                )
            # Reset partially the group chat manager
            self._message_thread.clear()
        else:
            # For continuation, keep message thread and artifacts intact
            # Only reset the round-specific counters if needed
            pass

        # Prepare the ledger
        ledger_message = TextMessage(
            content=self._get_task_ledger_full_prompt(self._task, self._team_description, self._facts, self._plan),
            source=self._name,
        )

        # Save my copy
        await self.update_message_thread([ledger_message])

        # Log it to the output topic.
        await self.publish_message(
            GroupChatMessage(message=ledger_message),
            topic_id=DefaultTopicId(type=self._output_topic_type),
        )
        # Log it to the output queue.
        await self._output_message_queue.put(ledger_message)

        # Broadcast
        await self.publish_message(
            GroupChatAgentResponse(response=Response(chat_message=ledger_message), name=self._name),
            topic_id=DefaultTopicId(type=self._group_topic_type),
        )

        # Restart the inner loop
        await self._orchestrate_step(cancellation_token=cancellation_token)

    async def _orchestrate_step(self, cancellation_token: CancellationToken) -> None:
        """Implements the inner loop of the orchestrator and selects next speaker."""
        # Check if we reached the maximum number of rounds
        if self._max_turns is not None and self._n_rounds > self._max_turns:
            await self._prepare_final_answer("Max rounds reached.", cancellation_token)
            return
        self._n_rounds += 1

        # Update the progress ledger
        context = self._thread_to_context()

        progress_ledger_prompt = self._get_progress_ledger_prompt(
            self._task, self._team_description, self._participant_names, AGENT_CAPABILITIES_DOC
        )
        
        context.append(UserMessage(content=progress_ledger_prompt, source=self._name))
        progress_ledger: Dict[str, Any] = {}
        assert self._max_json_retries > 0
        key_error: bool = False
        schema_error = None
        available_ids = list(self._agent_responses.keys()) if self._agent_responses else []
        for _ in range(self._max_json_retries):
            if schema_error:
                # If there was a schema error, add that to context
                context.append(UserMessage(content=f"Your previous output: {ledger_str} \n \n Error: {schema_error}", source=self._name))
            else:
                context.append(UserMessage(content=f"Available response IDs are: {available_ids if available_ids else 'NONE - no agent responses have been recorded yet'}. ", source=self._name))
            if self._model_client.model_info.get("structured_output", False):
                response = await self._model_client.create(
                    self._get_compatible_context(context), json_output=LedgerEntry
                )
            elif self._model_client.model_info.get("json_output", False):
                response = await self._model_client.create(
                    self._get_compatible_context(context), cancellation_token=cancellation_token, json_output=True
                )
            else:
                response = await self._model_client.create(
                    self._get_compatible_context(context), cancellation_token=cancellation_token
                )
            ledger_str = response.content
            try:
                assert isinstance(ledger_str, str)
                output_json = extract_json_from_str(ledger_str)
                if len(output_json) != 1:
                    raise ValueError(
                        f"Progress ledger should contain a single JSON object, but found: {len(progress_ledger)}"
                    )
                progress_ledger = output_json[0]
                print("progress_ledger:", progress_ledger)
                
                # Send the progress ledger to output topic only (for logging/monitoring)
                ledger_message_output = TextMessage(
                    content=json.dumps(progress_ledger, indent=2),
                    source=self._name,
                )
                await self.publish_message(
                    GroupChatMessage(message=ledger_message_output),
                    topic_id=DefaultTopicId(type=self._output_topic_type),
                )
                await self._output_message_queue.put(ledger_message_output)

                # If the team consists of a single agent, deterministically set the next speaker
                if len(self._participant_names) == 1:
                    progress_ledger["next_speaker"] = {
                        "reason": "The team consists of only one agent.",
                        "answer": self._participant_names[0],
                    }

                # Validate the structure
                required_keys = [
                    # "validation_checks",
                    "is_request_satisfied",
                    "is_progress_being_made",
                    "is_in_loop",
                    "instruction_or_question",
                    "next_speaker",
                ]
                # TODO: do we need this as pydantic is handling this?
                key_error = False
                for key in required_keys:
                    if (
                        key not in progress_ledger
                        or not isinstance(progress_ledger[key], dict)
                        or ("answer" not in progress_ledger[key] and key != "instruction_or_question")
                        or "reason" not in progress_ledger[key]
                    ):
                        key_error = True
                        break
                    
                next_inputs_ids = progress_ledger['instruction_or_question'].get("inputs", [])
                try:
                    next_inputs = [self._agent_responses[x.strip()].model_dump_json() for x in next_inputs_ids]
                except Exception as e:
                    invalid_ids = [x for x in next_inputs_ids if x.strip() not in self._agent_responses]
                    schema_error = (
                        f"Invalid input IDs provided: {invalid_ids}. "
                        f"Available response IDs are: {available_ids if available_ids else 'NONE - no agent responses have been recorded yet'}. "
                        f"If the required input is not available, the previous step may have failed or not been executed. "
                        f"Re-evaluate which step to execute next. Do NOT hallucinate response IDs."
                    )
                    print(schema_error)
                    continue

                # Validate the next speaker if the task is not yet complete
                if (
                    not progress_ledger["is_request_satisfied"]["answer"]
                    and progress_ledger["next_speaker"]["answer"] not in self._participant_names
                ):
                    key_error = True
                    break

                if not key_error:
                    break
                await self._log_message(f"Failed to parse ledger information, retrying: {ledger_str}")
            except (json.JSONDecodeError, TypeError):
                key_error = True
                await self._log_message("Invalid ledger format encountered, retrying...")
                continue
        if key_error:
            raise ValueError("Failed to parse ledger information after multiple retries.")
        await self._log_message(f"Progress Ledger: {progress_ledger}")

        # Check for task completion
        if progress_ledger["is_request_satisfied"]["answer"]:
            await self._log_message("Task completed, preparing final answer...")
            await self._prepare_final_answer(progress_ledger["is_request_satisfied"]["reason"], cancellation_token)
            return

        # Check for stalling
        if not progress_ledger["is_progress_being_made"]["answer"]:
            self._n_stalls += 1
        elif progress_ledger["is_in_loop"]["answer"]:
            self._n_stalls += 1
        else:
            self._n_stalls = max(0, self._n_stalls - 1)

        # Too much stalling
        if self._n_stalls >= self._max_stalls:
            await self._log_message("Stall count exceeded, re-planning with the outer loop...")
            await self._update_task_ledger(cancellation_token)
            await self._reenter_outer_loop(cancellation_token)
            return

        # Broadcast the next step
        next_speaker_message_dict = progress_ledger["instruction_or_question"]
        next_speaker_message = textwrap.dedent(f"""
        **Question**: {next_speaker_message_dict.get("instruction", "")}  NO RAW Geometric Coordinates.
        
        **Context**: {next_speaker_message_dict.get("context", "")}
        
        **User ask (for reference)**: {self._user_text_msg}
        
        **output_soft_requirment**: {next_speaker_message_dict.get("output_requirements", "")}
        
        **Inputs**: {next_inputs}
        """).strip()

        # if artifacts_context:
        #     next_speaker_message += artifacts_context

        next_speaker = progress_ledger["next_speaker"]["answer"]

        message = TextMessage(content=next_speaker_message, source=self._name)
        await self.update_message_thread([message])

        await self._log_message(f"Next Speaker: {progress_ledger['next_speaker']['answer']}")
        # Log it to the output topic.
        await self.publish_message(
            GroupChatMessage(message=message),
            topic_id=DefaultTopicId(type=self._output_topic_type),
        )
        # Log it to the output queue.
        await self._output_message_queue.put(message)

        # Broadcast it to the group
        next_speaker = progress_ledger["next_speaker"]["answer"]
        participant_topic_type = self._participant_name_to_topic_type[next_speaker]
        await self.publish_message(  # Broadcast
            GroupChatAgentResponse(response=Response(chat_message=message), name=self._name),
            # topic_id=DefaultTopicId(type=self._group_topic_type), #msd: testing with not broadcasting
            topic_id=DefaultTopicId(type=participant_topic_type), #msd: testing with not broadcasting
            cancellation_token=cancellation_token,
        )

        # Request that the step be completed
        # Check if the next speaker is valid
        if next_speaker not in self._participant_name_to_topic_type:
            raise ValueError(
                f"Invalid next speaker: {next_speaker} from the ledger, participants are: {self._participant_names}"
            )
        await self.publish_message(
            GroupChatRequestPublish(),
            topic_id=DefaultTopicId(type=participant_topic_type),
            cancellation_token=cancellation_token,
        )

        # Send the message to the next speaker
        if self._emit_team_events:
            select_msg = SelectSpeakerEvent(content=[next_speaker], source=self._name)
            await self.publish_message(
                GroupChatMessage(message=select_msg),
                topic_id=DefaultTopicId(type=self._output_topic_type),
            )
            await self._output_message_queue.put(select_msg)

    async def _update_task_ledger(self, cancellation_token: CancellationToken) -> None:
        """Update the task ledger (outer loop) with the latest facts and plan."""
        context = self._thread_to_context()

        # Update the facts
        update_facts_prompt = self._get_task_ledger_facts_update_prompt(self._task, self._facts)
        context.append(UserMessage(content=update_facts_prompt, source=self._name))

        response = await self._model_client.create(
            self._get_compatible_context(context), cancellation_token=cancellation_token
        )

        assert isinstance(response.content, str)
        self._facts = response.content
        context.append(AssistantMessage(content=self._facts, source=self._name))

        # Update the plan - now includes full planning guidance
        update_plan_prompt = self._get_task_ledger_plan_update_prompt(
            self._task, self._team_description, self._facts
        )
        context.append(UserMessage(content=update_plan_prompt, source=self._name))

        response = await self._model_client2.create(
            self._get_compatible_context(context), cancellation_token=cancellation_token
        )

        assert isinstance(response.content, str)
        self._plan = response.content

    async def _prepare_final_answer(self, reason: str, cancellation_token: CancellationToken) -> None:
        """Prepare the final answer for the task."""
        context = self._thread_to_context()

        # Get the final answer
        final_answer_prompt = self._get_final_answer_prompt(self._task)
        context.append(UserMessage(content=final_answer_prompt, source=self._name))

        response = await self._model_client.create(
            self._get_compatible_context(context), cancellation_token=cancellation_token
        )
        assert isinstance(response.content, str)
        message = TextMessage(content=response.content, source=self._name)

        await self.update_message_thread([message])  # My copy

        # Log it to the output topic.
        await self.publish_message(
            GroupChatMessage(message=message),
            topic_id=DefaultTopicId(type=self._output_topic_type),
        )
        # Log it to the output queue.
        await self._output_message_queue.put(message)

        # Broadcast
        await self.publish_message(
            GroupChatAgentResponse(response=Response(chat_message=message), name=self._name),
            topic_id=DefaultTopicId(type=self._group_topic_type),
            cancellation_token=cancellation_token,
        )

        if self._termination_condition is not None:
            await self._termination_condition.reset()
        # Signal termination
        await self._signal_termination(StopMessage(content=reason, source=self._name))

    def _thread_to_context(self) -> List[LLMMessage]:
        """Convert the message thread to a context for the model."""
        context: List[LLMMessage] = []
        for m in self._message_thread:
            if isinstance(m, ToolCallRequestEvent | ToolCallExecutionEvent):
                continue
            elif isinstance(m, StopMessage | HandoffMessage):
                context.append(UserMessage(content=m.content, source=m.source))
            elif m.source == self._name:
                assert isinstance(m, TextMessage | ToolCallSummaryMessage)
                context.append(AssistantMessage(content=m.content, source=m.source))
            else:
                assert isinstance(m, (TextMessage, MultiModalMessage, ToolCallSummaryMessage))
                context.append(UserMessage(content=m.content, source=m.source))
        return context
    
    def _get_compatible_context(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """Ensure that the messages are compatible with the underlying client, by removing images if needed."""
        if self._model_client.model_info["vision"]:
            return messages
        else:
            return remove_images(messages)
