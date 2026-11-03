"""Execution cancellation, failed-workflow stops and real raster uploads."""
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import psycopg2
import rasterio
from rasterio.transform import from_origin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autogen_core import CancellationToken

from agents.core.config import AgentsConfig, ConfigProvider, QueryConfig
from agents.core.response_store import ResponseStore, ResponseStoreProvider
from agents.core.types import GeoFahamToolResponse
from agents.orchestrator_agent.orchestrator import GeoFahamOrchestrator
from agents.vector_agent.tools import VectorQueryExecutor, _is_safe_query
from agents.shared.responses import validate_response_artifacts
from backend.routes import raster, websocket
from tests.test_workflow_contracts import ledger, manager


class StopWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_work_stops_after_one_ledger_without_dispatch(self):
        failed = GeoFahamToolResponse(response_id='failed', source='stac_agent', type='error',
                                      error_message='Imagery service unavailable')
        entry = ledger(inputs=['failed'], can_proceed=False)
        entry['stop_reason'] = 'Imagery service unavailable; requested NDVI cannot be computed'
        obj = manager([entry], [failed])
        await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
        self.assertEqual(obj._progress_client.create.await_count, 1)
        obj.update_message_thread.assert_not_awaited()
        self.assertIn('incomplete work', obj._prepare_final_answer.call_args.args[0])
        self.assertIn('Imagery service unavailable', obj._prepare_final_answer.call_args.args[0])

    async def test_stop_requires_real_failure_evidence_and_cannot_claim_success(self):
        for complete, inputs in ((False, []), (False, ['unknown']), (True, ['failed'])):
            with self.subTest(complete=complete, inputs=inputs):
                entry = ledger(complete=complete, inputs=inputs)
                entry['stop_reason'] = 'Cannot continue'
                obj = manager([entry], [GeoFahamToolResponse(response_id='failed', source='test',
                    type='error', error_message='failed')])
                await GeoFahamOrchestrator._orchestrate_step(obj, CancellationToken())
                self.assertIn('invalid progress ledgers', obj._prepare_final_answer.call_args.args[0])
                obj.update_message_thread.assert_not_awaited()


class RasterUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_geotiff_is_registered_and_attached_to_next_chat_request(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = AgentsConfig(); cfg.paths.base_dir = Path(folder)
            store = ResponseStore(str(cfg.paths.response_store_path))
            source = Path(folder)/'metric.tif'
            with rasterio.open(source, 'w', driver='GTiff', width=2, height=2, count=1,
                    dtype='float32', crs=32615, transform=from_origin(500000,4300020,10,10), nodata=-9999) as ds:
                ds.write(np.array([[-9999, .2],[.4,.6]], dtype='float32'), 1)
            with ConfigProvider.override(cfg), patch.object(ResponseStoreProvider, '_instance', store), \
                    patch.multiple(raster, USER_DATA_PATH=str(cfg.paths.user_data_dir),
                                   USER_ARTIFACTS_JSON=str(cfg.paths.user_artifacts_path)):
                app = FastAPI(); app.include_router(raster.router)
                with TestClient(app) as client:
                    response = client.post('/api/upload-raster', files={
                        'file': ('metric.tif', source.read_bytes(), 'image/tiff')}, data={'title':'Metric'})
                self.assertEqual(response.status_code, 200, response.text)
                registered = store.get(response.json()['response_id'])
                self.assertEqual(registered.data_type, 'raster')
                self.assertTrue(registered.metadata['uploaded_file'])
                self.assertEqual(registered.artifact.metadata['crs'], 'EPSG:32615')
                validate_response_artifacts(registered)
                prepared = await websocket.prepare_user_message({'content':'Calculate the mean','source':'user'})
                self.assertIn(registered.response_id, prepared['content'])
                self.assertIn(registered.artifact.path, prepared['content'])
                with rasterio.open(registered.artifact.path) as ds:
                    self.assertEqual(ds.read(1,masked=True).count(), 3)


class SqlSafetyTests(unittest.TestCase):
    def test_single_read_queries_are_allowed(self):
        for query in (
            "SELECT 1;",
            "-- note\nWITH a AS (SELECT 1) SELECT * FROM a",
            "WITH {{GEOJSON_POLYGONS_CTE}} SELECT name FROM polygons_from_geojson",
            "SELECT name FROM disasters WHERE name = 'Do; COPY x'",
            "SELECT ST_ClusterDBSCAN(geom, 50, 2) OVER () AS cluster FROM flood_maps",
        ):
            self.assertTrue(_is_safe_query(query), query)

    def test_statements_that_escape_read_only_execution_are_rejected(self):
        for query in (
            "COMMIT; SELECT 1",
            "SELECT 1 /* ; */ ; COMMIT",
            "SET TRANSACTION READ WRITE",
            "DO $$BEGIN EXECUTE 'DR'||'OP TABLE disasters'; END$$",
            "COPY (SELECT 1) TO PROGRAM 'id'",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT * FROM dblink('host=x', 'SELECT 1') AS t(a int)",
        ):
            self.assertFalse(_is_safe_query(query), query)


class SqlCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sql_does_not_block_loop_and_cancellation_waits_for_query_cleanup(self):
        started, stopped = threading.Event(), threading.Event()
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor
        connection.cancel.side_effect = stopped.set
        def execute(sql, *args):
            if sql == 'SELECT slow':
                started.set()
                if not stopped.wait(5):
                    raise AssertionError('Query cancellation was never requested')
                raise psycopg2.errors.QueryCanceled('cancelled')
        cursor.execute.side_effect = execute
        executor = object.__new__(VectorQueryExecutor)
        executor._conn = connection
        executor._query_lock = asyncio.Lock()
        task = asyncio.create_task(executor._execute_query_impl('SELECT slow',False,'test'))
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        cursor.fetchall.return_value = [{'answer':42}]
        follower = asyncio.create_task(executor._execute_query_impl('SELECT 42',False,'after cancellation'))
        await asyncio.sleep(.02)
        self.assertFalse(follower.done())
        self.assertNotIn('SELECT 42', [call.args[0] for call in cursor.execute.call_args_list])
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        self.assertTrue(stopped.is_set())
        connection.cancel.assert_called()
        response = json.loads(await asyncio.wait_for(follower, 2))
        self.assertEqual(response['data'], [{'answer':42}])
        self.assertEqual(connection.__exit__.call_count, 2)
        self.assertIn('SET TRANSACTION READ ONLY', [call.args[0] for call in cursor.execute.call_args_list])
        self.assertTrue(any(call.args[0] == 'SET LOCAL statement_timeout = %s'
                            for call in cursor.execute.call_args_list))

    def test_timeout_configuration_rejects_disabling_the_limit(self):
        for options in ({'sql_timeout_seconds':0}, {'raster_timeout_seconds':-1}):
            with self.assertRaises(ValueError):
                QueryConfig(**options)


if __name__ == '__main__':
    unittest.main()
