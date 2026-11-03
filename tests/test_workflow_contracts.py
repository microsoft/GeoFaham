"""Artifact handoffs, orchestration and temporal provenance; no model or database calls."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import rasterio
import xarray as xr
from autogen_core import CancellationToken
from autogen_core.models import FunctionExecutionResult
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import TextMessage, ToolCallExecutionEvent
from autogen_agentchat.teams._group_chat._events import GroupChatAgentResponse
from autogen_ext.models.replay import ReplayChatCompletionClient

from agents.core.constants import AGENT_NAMES
from agents.core.types import GeoFahamToolResponse
from agents.orchestrator_agent.orchestrator import GeoFahamOrchestrator
from agents.orchestrator_agent.group_chat import GeoFahamGroupChat
from agents.raster_ops_agent.executor import RasterCodeExecutor, CodeExecutionError
from agents.raster_ops_agent.tools import _execute_custom_raster_code as execute_custom_raster_code
from agents.shared.responses import validate_response_artifacts


def ledger(*, complete=False, inputs=(), can_proceed=True, temporal_mode="unspecified"):
    return {
        "temporal_mode": temporal_mode,
        "validation_checks": {
            "plan_adherence": {"current_step": "Step 1", "all_previous_steps_completed": True,
                               "required_artifacts_present": True, "can_skip_step": False, "skip_reason": ""},
            "input_validation": {"next_agent_needs": [], "available_in_ledger": list(inputs),
                                 "missing_inputs": [], "data_type_matches": True, "can_proceed": can_proceed},
            "output_validation": {"last_agent_response_summary": "result", "expected_output": "result",
                                  "output_matches_expectation": True, "output_is_usable_for_next_step": True},
        },
        "is_request_satisfied": {"answer": complete, "reason": "test"},
        "is_progress_being_made": {"answer": True, "reason": "test"},
        "is_in_loop": {"answer": False, "reason": "test"},
        "next_speaker": {"answer": AGENT_NAMES["VECTOR_AGENT"], "reason": "test"},
        "instruction_or_question": {"reason": "test", "instruction": "count disasters", "context": "test",
                                    "inputs": list(inputs), "output_requirements": "table"},
    }


def manager(ledgers, responses=()):
    progress = SimpleNamespace(
        model_info={"json_output": True},
        create=AsyncMock(side_effect=[SimpleNamespace(content=json.dumps(item)) for item in ledgers]),
    )
    planner = SimpleNamespace(create=AsyncMock())
    return SimpleNamespace(
        _max_turns=8, _n_rounds=0, _n_stalls=0, _max_stalls=3, _max_json_retries=len(ledgers),
        _temporal_mode=None, _task="test", _user_text_msg="test", _name="orchestrator",
        _clarification_question="",
        _participant_names=[AGENT_NAMES["VECTOR_AGENT"]],
        _participant_name_to_topic_type={AGENT_NAMES["VECTOR_AGENT"]: "vector_topic"},
        _team_description="test", _agent_responses={r.response_id: r for r in responses},
        _thread_to_context=lambda: [], _get_progress_ledger_prompt=lambda *a: "ledger",
        _get_compatible_context=lambda c: c, _progress_client=progress, _planner_client=planner,
        publish_message=AsyncMock(), _output_topic_type="output", _output_message_queue=SimpleNamespace(put=AsyncMock()),
        update_message_thread=AsyncMock(), _log_message=AsyncMock(), _prepare_final_answer=AsyncMock(),
        _emit_team_events=False,
    )


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_checks_are_corrected_before_dispatch(self):
        obj = manager([ledger(can_proceed=False), ledger()])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertEqual(obj._progress_client.create.await_count, 2)
        obj._planner_client.create.assert_not_awaited()
        obj.update_message_thread.assert_awaited_once()
        feedback = obj._progress_client.create.call_args.args[0][-1].content
        self.assertIn("Input validation failed", feedback)

    async def test_rejected_progress_does_not_change_the_temporal_mode(self):
        for established in (None, "single_scene"):
            with self.subTest(established=established):
                bad = ledger(can_proceed=False, temporal_mode="composite")
                corrected = ledger(temporal_mode="single_scene")
                obj = manager([bad, corrected])
                obj._temporal_mode = established
                await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
                self.assertEqual(obj._progress_client.create.await_count, 2)
                self.assertEqual(obj._temporal_mode, "single_scene")
                obj.update_message_thread.assert_awaited_once()
                obj._prepare_final_answer.assert_not_awaited()

    async def test_first_accepted_single_scene_output_validates_its_provenance(self):
        response = GeoFahamToolResponse(
            response_id="ndvi_stats", source=AGENT_NAMES["RASTER_AGENT"], type="data",
            data_type="stats", data=[{"mean": 0.5}],
            metadata={"temporal_mode": "single_scene", "acquisition_dates": ["2023-08-28"]},
        )
        obj = manager([ledger(complete=True, inputs=[response.response_id], temporal_mode="single_scene")], [response])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertEqual(obj._temporal_mode, "single_scene")
        self.assertEqual(obj._prepare_final_answer.call_args.args[0], "test")

    async def test_nested_prompt_shape_is_rejected(self):
        bad = ledger()
        instruction = bad["instruction_or_question"]
        bad["instruction_or_question"] = {"reason": "test", "answer": instruction}
        obj = manager([bad])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        obj.update_message_thread.assert_not_awaited()
        self.assertIn("incomplete work", obj._prepare_final_answer.call_args.args[0])

    async def test_unknown_response_ids_stop_cleanly_after_retries(self):
        obj = manager([ledger(inputs=["missing"]), ledger(inputs=["missing"])])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        obj.update_message_thread.assert_not_awaited()
        self.assertIn("Unknown response ID", obj._prepare_final_answer.call_args.args[0])

    async def test_empty_artifact_cannot_complete(self):
        response = GeoFahamToolResponse(response_id="broken", source="raster_ops_agent", artifact={"path": ""})
        obj = manager([ledger(complete=True, inputs=["broken"])], [response])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertIn("artifact file is missing", obj._prepare_final_answer.call_args.args[0])
        obj.update_message_thread.assert_not_awaited()

    async def test_failed_tool_response_cannot_be_an_input(self):
        response = GeoFahamToolResponse(response_id="failed", source="worker", type="error", error_message="query failed")
        obj = manager([ledger(inputs=["failed"])], [response])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        obj.update_message_thread.assert_not_awaited()
        self.assertIn("query failed", obj._prepare_final_answer.call_args.args[0])

    async def test_zero_count_is_valid_completion_evidence(self):
        response = GeoFahamToolResponse(response_id="count", source="postgis_agent", type="data", data=[{"count": 0}])
        obj = manager([ledger(complete=True, inputs=["count"])], [response])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertEqual(obj._prepare_final_answer.call_args.args[0], "test")

    async def test_temporal_substitution_cannot_complete(self):
        response = GeoFahamToolResponse(
            response_id="composite", source=AGENT_NAMES["RASTER_AGENT"], type="data", data=[{"mean": 0.2}],
            metadata={"metadata": {"temporal_mode": "composite", "acquisition_dates": ["2023-08-18", "2023-08-28"]}},
        )
        obj = manager([ledger(complete=True, inputs=["composite"], temporal_mode="single_scene")], [response])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertIn("temporal mode", obj._prepare_final_answer.call_args.args[0])

    async def test_every_tool_result_is_registered(self):
        responses = [GeoFahamToolResponse(response_id=rid, source="worker", type="data", data=[{"count": 1}])
                     for rid in ["first", "second"]]
        event = ToolCallExecutionEvent(source="worker", content=[
            FunctionExecutionResult(content=r.model_dump_json(), name="tool", call_id=r.response_id) for r in responses
        ])
        message = GroupChatAgentResponse(name="worker", response=Response(
            chat_message=TextMessage(content="done", source="worker"), inner_messages=[event]))
        obj = SimpleNamespace(_agent_responses={}, _response_store=SimpleNamespace(store=Mock()),
                              _n_rounds=1, update_message_thread=AsyncMock(), _termination_condition=None,
                              _orchestrate_step=AsyncMock())
        await GeoFahamOrchestrator.handle_agent_response(obj, message, SimpleNamespace(cancellation_token=CancellationToken()))
        self.assertEqual(set(obj._agent_responses), {"first", "second"})
        self.assertEqual(obj._response_store.store.call_count, 2)

    async def test_planning_uses_planner_client(self):
        obj = SimpleNamespace(
            _thread_to_context=lambda: [], _get_task_ledger_facts_update_prompt=lambda *a: "facts",
            _get_task_ledger_plan_update_prompt=lambda *a: "plan", _get_compatible_context=lambda c: c,
            _task="task", _facts="facts", _name="orchestrator", _team_description="team",
            _clarification_question="", _max_json_retries=2,
            _planner_client=SimpleNamespace(model_info={}, create=AsyncMock(side_effect=[
                SimpleNamespace(content=json.dumps({"facts":"updated", "clarification_question":""})),
                SimpleNamespace(content="updated plan"),
            ])),
            _progress_client=SimpleNamespace(create=AsyncMock()),
        )
        obj._read_task_facts = lambda *args: GeoFahamOrchestrator._read_task_facts(obj, *args)
        await GeoFahamOrchestrator._update_task_ledger(obj, CancellationToken())
        self.assertEqual(obj._planner_client.create.await_count, 2)
        obj._progress_client.create.assert_not_awaited()


class ArtifactTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_raster_returns_readable_file_and_statistics(self):
        with tempfile.TemporaryDirectory() as folder:
            arr = xr.DataArray(np.arange(16, dtype="float32").reshape(4, 4), dims=("y", "x"),
                               coords={"y": [3.5, 2.5, 1.5, .5], "x": [.5, 1.5, 2.5, 3.5]}).rio.write_crs(4326)
            with patch("agents.raster_ops_agent.io_utils.QUERY_JSONS_PATH", folder), patch.object(
                RasterCodeExecutor, "execute", return_value={"result": arr, "metadata": {}}
            ):
                response = GeoFahamToolResponse.model_validate_json(
                    await execute_custom_raster_code("result = test", "test", True, "raster"))
            validate_response_artifacts(response)
            self.assertAlmostEqual(response.artifact.stats["mean"], 7.5)
            with rasterio.open(response.artifact.path) as raster:
                self.assertEqual(raster.shape, (4, 4))

    async def test_bad_json_and_missing_nested_raster_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"broken.geojson"
            p.write_text("[]")
            response = GeoFahamToolResponse(response_id="bad", source="test", artifact={"path": str(p)})
            with self.assertRaises(ValueError):
                validate_response_artifacts(response)
            nested = GeoFahamToolResponse(response_id="nested", source="test", type="data", data_type="raster_multi",
                                         data=[{"layers": {"ndvi": {"url": str(Path(folder)/"missing.tif")}}}])
            with self.assertRaisesRegex(ValueError, "missing"):
                validate_response_artifacts(nested)


    async def test_multiple_saved_intermediates_must_all_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metric.tif"
            with rasterio.open(path, "w", driver="GTiff", width=2, height=2,
                               count=1, dtype="float32", crs=4326,
                               transform=rasterio.transform.from_origin(1, 2, 0.01, 0.01)) as ds:
                ds.write(np.ones((2, 2), dtype="float32"), 1)
            response = GeoFahamToolResponse(
                response_id="intermediates", source="raster_ops_agent", type="data",
                data_type="raster_intermediate",
                data=[{"saved_intermediate_paths": {"red": str(path), "nir": str(path)}, "count": 2}],
            )
            validate_response_artifacts(response)
            response.data[0]["saved_intermediate_paths"]["nir"] = str(Path(folder) / "missing.tif")
            with self.assertRaisesRegex(ValueError, "artifact file is missing"):
                validate_response_artifacts(response)



class ResetRouteTests(unittest.TestCase):
    def test_reset_uses_the_relocated_route(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import backend.routes.reset as reset
        app = FastAPI()
        app.include_router(reset.router)
        with tempfile.TemporaryDirectory() as folder:
            paths = {}
            for name in ("TEAM_STATE_PATH", "CONVERSATION_HISTORY_PATH", "ARTIFACTS_LEDGER_PATH", "RESPONSE_STORE_PATH"):
                path = Path(folder)/name
                path.write_text("existing state")
                paths[name] = str(path)
            with patch.multiple(reset, **paths), patch.object(reset, 'get_response_store', return_value=Mock()), TestClient(app) as client:
                response = client.post("/api/reset")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Path(paths["CONVERSATION_HISTORY_PATH"]).read_text(), "[]")
            self.assertEqual(Path(paths["RESPONSE_STORE_PATH"]).read_text(), "")


class TemporalAndConfigTests(unittest.TestCase):
    def test_single_date_rejects_multiple_dates_and_separate_loads(self):
        executor = RasterCodeExecutor(temporal_mode="single_scene")
        executor._record_sources(["one"], ["2023-08-18"])
        with self.assertRaises(CodeExecutionError):
            executor._record_sources(["two"], ["2023-08-28"])
        self.assertEqual(executor.acquisition_dates, {"2023-08-18"})

    def test_loader_filters_one_date_before_single_scene_check(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"items.json"
            def item(date):
                return {"type": "Feature", "stac_version": "1.0.0", "id": date,
                        "geometry": {"type": "Point", "coordinates": [0, 0]}, "bbox": [0, 0, 0, 0],
                        "properties": {"datetime": date + "T12:00:00Z", "proj:code": "EPSG:32604"},
                        "links": [], "assets": {"B04": {"href": "https://example.com/test.tif"}}}
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [item("2023-08-18"), item("2023-08-28")]}))
            executor = RasterCodeExecutor(temporal_mode="single_scene")
            with patch("stackstac.stack", return_value=xr.DataArray([1])) as stack:
                with self.assertRaises(CodeExecutionError):
                    executor.load_stac_items(str(path), [-156.68, 20.88, -156.67, 20.89], ["B04"])
                stack.assert_not_called()
                executor.load_stac_items(str(path), [-156.68, 20.88, -156.67, 20.89], ["B04"],
                                         properties_filter={"datetime": "2023-08-18"})
                self.assertEqual(len(stack.call_args.args[0]), 1)
                self.assertEqual(executor.acquisition_dates, {"2023-08-18"})

    def test_saved_raster_preserves_single_date_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"intermediate.tif"
            provenance = {"temporal_mode": "single_scene", "source_scene_ids": ["one"],
                          "acquisition_dates": ["2023-08-18"]}
            arr = xr.DataArray(np.ones((2, 2)), dims=("y", "x"),
                               coords={"y": [1.5, .5], "x": [.5, 1.5]}).rio.write_crs(4326)
            arr.attrs["geofaham_temporal_provenance"] = json.dumps(provenance)
            arr.rio.to_raster(path)
            executor = RasterCodeExecutor(temporal_mode="single_scene")
            raster, _ = executor.load_raster_file(str(path))
            self.assertEqual(executor.acquisition_dates, {"2023-08-18"})
            self.assertEqual(executor.source_scene_ids, {"one"})
            raster.close()

    def test_composite_records_all_sources(self):
        executor = RasterCodeExecutor(temporal_mode="composite")
        executor._record_sources(["one", "two"], ["2023-08-18", "2023-08-28"])
        self.assertEqual(len(executor.acquisition_dates), 2)

    def test_interpreter_keeps_basic_builtins_without_execution_builtins(self):
        executor = RasterCodeExecutor()
        for name in ("open", "eval", "exec", "compile"):
            self.assertNotIn(name, executor.aeval.symtable)
        self.assertEqual(executor.aeval("sum(range(4))"), 6)

    def test_distinct_model_clients_survive_serialization(self):
        planner = ReplayChatCompletionClient(["planner"])
        progress = ReplayChatCompletionClient(["progress"])
        team = GeoFahamGroupChat([AssistantAgent("worker", planner)], planner, progress)
        config = team._to_config()
        restored = GeoFahamGroupChat._from_config(config)
        self.assertEqual(restored._model_client.dump_component(), planner.dump_component())
        self.assertEqual(restored._model_client2.dump_component(), progress.dump_component())
        self.assertNotEqual(config.model_client, config.model_client2)


if __name__ == "__main__":
    unittest.main()
