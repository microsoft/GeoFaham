"""Required clarifications block planning/dispatch and survive user replies."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from autogen_core import CancellationToken
from autogen_agentchat.base import Response
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams._group_chat._events import GroupChatAgentResponse, GroupChatRequestPublish, GroupChatStart

from agents.core.constants import AGENT_NAMES
from agents.orchestrator_agent.orchestrator import GeoFahamOrchestrator, GeoFahamOrchestratorState, TaskFacts
from tests.test_workflow_contracts import manager


def facts_response(question=''):
    return SimpleNamespace(content=json.dumps({'facts':'Preserve the user constraints.',
                                               'clarification_question':question}))


class ClarificationFlowTests(unittest.IsolatedAsyncioTestCase):
    def facts_manager(self, responses):
        obj = manager([{}])
        obj._facts = ''
        obj._plan = ''
        obj._max_json_retries = len(responses)
        obj._planner_client = SimpleNamespace(model_info={'structured_output':True},
                                              create=AsyncMock(side_effect=responses))
        obj._read_task_facts = lambda *args: GeoFahamOrchestrator._read_task_facts(obj,*args)
        return obj

    async def test_invalid_fact_response_cannot_erase_a_required_question(self):
        obj = self.facts_manager([SimpleNamespace(content='{"facts":"Incomplete envelope"}')])
        obj._clarification_question = 'Which date?'
        with self.assertRaisesRegex(ValueError,'no workflow was dispatched'):
            await obj._read_task_facts([],CancellationToken())
        self.assertEqual(obj._clarification_question,'Which date?')
        obj.publish_message.assert_not_awaited()

    async def test_pending_facts_skip_the_plan_generation_call(self):
        obj = self.facts_manager([facts_response('Which acquisition date should I use?')])
        obj._termination_condition = None
        obj.validate_group_state = AsyncMock()
        obj._message_thread = []
        obj._response_store = SimpleNamespace(get_all=lambda: [])
        obj._extract_user_json = Mock()
        obj._get_task_ledger_facts_prompt = lambda task: 'Extract facts'
        obj._get_task_ledger_plan_prompt = Mock(return_value='Generate a plan')
        obj._reenter_outer_loop = AsyncMock()
        request = GroupChatStart(messages=[TextMessage(content='Use both dates in one single scene.',source='user')])
        await GeoFahamOrchestrator.handle_start(obj,request,SimpleNamespace(cancellation_token=CancellationToken()))
        self.assertEqual(obj._planner_client.create.await_count,1)
        self.assertIs(obj._planner_client.create.call_args.kwargs['json_output'],TaskFacts)
        obj._get_task_ledger_plan_prompt.assert_not_called()
        self.assertEqual(obj._clarification_question,'Which acquisition date should I use?')
        obj._reenter_outer_loop.assert_awaited_once()

    async def test_pending_question_dispatches_only_user_proxy_without_a_progress_call(self):
        obj = manager([{}])
        obj._clarification_question = 'Which date should I use?'
        obj._participant_name_to_topic_type[AGENT_NAMES['USER_PROXY']] = 'user_topic'
        obj._request_user_clarification = lambda *args: GeoFahamOrchestrator._request_user_clarification(obj,*args)
        await GeoFahamOrchestrator._orchestrate_step(obj,CancellationToken())
        obj._progress_client.create.assert_not_awaited()
        obj._planner_client.create.assert_not_awaited()
        requests = [call for call in obj.publish_message.call_args_list
                    if isinstance(call.args[0],GroupChatRequestPublish)]
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0].kwargs['topic_id'].type,'user_topic')
        self.assertEqual(obj.update_message_thread.call_args.args[0][0].content,'Which date should I use?')

    async def test_answer_is_reassessed_before_a_plan_is_created(self):
        for remaining_question in ('','Please choose one specific date.'):
            with self.subTest(remaining_question=remaining_question):
                outputs = [facts_response(remaining_question)]
                if not remaining_question: outputs.append(SimpleNamespace(content='Plan using the confirmed date'))
                obj = self.facts_manager(outputs)
                obj._clarification_question = 'Which date?'
                obj._task = 'Use both dates in one single scene.'
                obj._user_text_msg = obj._task
                obj._termination_condition = None
                obj._get_task_ledger_facts_update_prompt = lambda *args:'Update facts from the user reply'
                obj._get_task_ledger_plan_prompt = Mock(return_value='Plan from clarified facts')
                obj._get_task_ledger_plan_update_prompt = Mock(return_value='Replan after failure')
                obj._extract_user_json = Mock()
                obj._update_task_ledger = lambda *args: GeoFahamOrchestrator._update_task_ledger(obj,*args)
                obj._reenter_outer_loop = AsyncMock()
                obj._orchestrate_step = AsyncMock()
                reply = 'Use 2023-08-28 only.' if not remaining_question else 'I am not sure.'
                message = GroupChatAgentResponse(name=AGENT_NAMES['USER_PROXY'],response=Response(
                    chat_message=TextMessage(content=reply,source=AGENT_NAMES['USER_PROXY'])))
                await GeoFahamOrchestrator.handle_agent_response(obj,message,
                    SimpleNamespace(cancellation_token=CancellationToken()))
                self.assertIn(reply,obj._task)
                self.assertIn(reply,obj._user_text_msg)
                self.assertEqual(obj._clarification_question,remaining_question)
                self.assertIsNone(obj._temporal_mode)
                obj._orchestrate_step.assert_not_awaited()
                obj._reenter_outer_loop.assert_awaited_once()
                obj._get_task_ledger_plan_update_prompt.assert_not_called()
                if remaining_question:
                    obj._get_task_ledger_plan_prompt.assert_not_called()
                    self.assertEqual(obj._planner_client.create.await_count,1)
                else:
                    obj._get_task_ledger_plan_prompt.assert_called_once()
                    self.assertEqual(obj._plan,'Plan using the confirmed date')

    async def test_question_survives_saved_state_and_old_states_remain_loadable(self):
        store = SimpleNamespace(to_dict=lambda:{},get_by_source=lambda source:[],
            from_dict=Mock(),get_all=lambda:[])
        obj = SimpleNamespace(_message_thread=[],_current_turn=0,_task='task',_facts='facts',_plan='pending',
            _clarification_question='Which date?',_n_rounds=1,_n_stalls=0,_response_store=store)
        state = await GeoFahamOrchestrator.save_state(obj)
        restored = SimpleNamespace(_message_factory=None,_response_store=store)
        await GeoFahamOrchestrator.load_state(restored,state)
        self.assertEqual(restored._clarification_question,'Which date?')
        state.pop('clarification_question')
        self.assertEqual(GeoFahamOrchestratorState.model_validate(state).clarification_question,'')


if __name__=='__main__':
    unittest.main()
