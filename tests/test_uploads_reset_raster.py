"""Uploaded inputs, reset, raster grids and OSM bounding-box calls."""
import asyncio
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import Point, Polygon, box, mapping
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autogen_core import CancellationToken
from autogen_agentchat.messages import TextMessage

from agents.core.config import AgentsConfig, ConfigProvider
from agents.core.response_store import ResponseStore, ResponseStoreProvider
from agents.core.types import GeoFahamToolResponse
from agents.orchestrator_agent.orchestrator import GeoFahamOrchestrator, GeoFahamOrchestratorState
from agents.raster_ops_agent.executor import RasterCodeExecutor
from agents.raster_ops_agent import io_utils
from backend.routes import geojson, reset, websocket, polling
from backend.services.chat_tasks import active_chat_tasks


def feature(geometry, **properties):
    return {'type': 'Feature', 'geometry': mapping(geometry) if geometry is not None else None,
            'properties': properties}


def collection(*features):
    return {'type': 'FeatureCollection', 'features': list(features)}


class UploadAndResetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        cfg = AgentsConfig(); cfg.paths.base_dir = self.folder
        self.stack.enter_context(ConfigProvider.override(cfg))
        self.store = ResponseStore(str(cfg.paths.response_store_path))
        self.stack.enter_context(patch.object(ResponseStoreProvider, '_instance', self.store))
        self.stack.enter_context(patch.multiple(geojson, USER_DATA_PATH=str(cfg.paths.user_data_dir),
                                             USER_ARTIFACTS_JSON=str(cfg.paths.user_artifacts_path)))
        self.paths = {'TEAM_STATE_PATH': str(cfg.paths.team_state_path),
                      'CONVERSATION_HISTORY_PATH': str(cfg.paths.conversation_history_path),
                      'RESPONSE_STORE_PATH': str(cfg.paths.response_store_path),
                      'ARTIFACTS_LEDGER_PATH': str(cfg.paths.state_dir/'ledger.jsonl')}
        self.stack.enter_context(patch.multiple(reset, **self.paths))
        self.app = FastAPI(); self.app.include_router(geojson.router)
        self.client = self.stack.enter_context(TestClient(self.app))

    def tearDown(self):
        self.stack.close()

    def upload(self, data, title='Test upload'):
        return self.client.post('/api/upload-geojson',
                                files={'file': ('test.geojson', json.dumps(data), 'application/geo+json')},
                                data={'title': title})

    async def test_upload_after_team_creation_reaches_websocket_and_polling(self):
        class Team:
            async def run_stream(self, task, **kwargs):
                self.request = task
                yield TextMessage(source='postgis_agent', content='done')
        ws = websocket.ChatSession(Mock(), 'multi-agent'); ws.team = Team()
        ps = polling.PollingSession('multi-agent'); ps.team = Team(); ps._save_state = AsyncMock()
        result = self.upload(collection(feature(Point(-90.3, 38.65))), 'Named AOI')
        self.assertEqual(result.status_code, 200)
        rid = result.json()['response_id']
        saved = self.store.get(rid)
        self.assertTrue(Path(saved.artifact.path).is_file())
        async for _ in ws.process_message({'content': 'Use Named AOI', 'source': 'user'}):
            pass
        await ps.process_message({'content': 'Use Named AOI', 'source': 'user'})
        for team in (ws.team, ps.team):
            self.assertIn(rid, team.request.content)
            self.assertIn('Named AOI', team.request.content)
            self.assertIn('User_JSON_START', team.request.content)

    async def test_clarification_reply_also_attaches_upload(self):
        result = self.upload(collection(feature(Point(-90.3, 38.65))))
        ws = websocket.ChatSession(SimpleNamespace(receive_json=AsyncMock(return_value={
            'content': 'Use the uploaded file', 'source': 'user'})), 'multi-agent')
        reply = await ws._user_input('Which file?', None)
        self.assertIn(result.json()['response_id'], reply)
        manager = SimpleNamespace(_task='', _agent_responses={}, _response_store=self.store)
        GeoFahamOrchestrator._extract_user_json(manager, reply)
        self.assertIn(result.json()['response_id'], manager._agent_responses)

    async def test_upload_survives_loading_an_older_team_snapshot(self):
        result = self.upload(collection(feature(Point(-90.3, 38.65))))
        manager = SimpleNamespace(_response_store=self.store)
        await GeoFahamOrchestrator.load_state(manager, GeoFahamOrchestratorState().model_dump())
        self.assertIn(result.json()['response_id'], manager._agent_responses)

    async def test_numeric_schema_uses_non_null_values_across_features(self):
        result = self.upload(collection(feature(Point(0, 0), capacity=None),
                                        feature(Point(1, 1), capacity=20, later_only=7)))
        self.assertEqual(result.status_code, 200)
        artifact = self.store.get(result.json()['response_id']).artifact
        for key in ('capacity', 'later_only'):
            self.assertIn(artifact.property_keys['points'][key]['type'], ('int', 'float'))
            self.assertTrue(artifact.property_keys['points'][key]['nullable'])

    async def test_projected_upload_is_converted_to_wgs84(self):
        x, y = Transformer.from_crs(4326, 3857, always_xy=True).transform(-90.3, 38.65)
        data = collection(feature(Point(x, y)))
        data['crs'] = {'type': 'name', 'properties': {'name': 'EPSG:3857'}}
        result = self.upload(data)
        self.assertEqual(result.status_code, 200)
        artifact = self.store.get(result.json()['response_id']).artifact
        coords = json.loads(Path(artifact.path).read_text())['features'][0]['geometry']['coordinates']
        np.testing.assert_allclose(coords, [-90.3, 38.65], atol=1e-8)

    async def test_invalid_uploads_are_rejected_without_registration(self):
        bow = Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])
        for data, reason in [(collection(feature(bow)), 'Invalid geometry'),
                             (collection(feature(Point(200, 95))), 'longitude/latitude'),
                             (collection(feature(None)), 'geometry'), (collection(), 'no features')]:
            with self.subTest(reason=reason):
                result = self.upload(data)
                self.assertEqual(result.status_code, 400)
                self.assertIn(reason, result.json()['detail'])
        self.assertEqual(self.store.get_all(), [])

    async def test_reset_waits_for_old_writers_and_clears_live_and_saved_state(self):
        self.store.store(GeoFahamToolResponse(response_id='old', source='test', type='data', data=[{'value': 1}]))
        for name, path in self.paths.items():
            if name != 'RESPONSE_STORE_PATH': Path(path).write_text('old state')
        started = asyncio.Event(); token = CancellationToken()
        async def old_writer():
            try:
                started.set(); await asyncio.Event().wait()
            finally:
                Path(self.paths['CONVERSATION_HISTORY_PATH']).write_text('late write')
                active_chat_tasks.pop(asyncio.current_task(), None)
        task = asyncio.create_task(old_writer()); active_chat_tasks[task] = token
        await started.wait()
        with patch.dict(polling._sessions, {'old-session': Mock()}):
            await reset.reset_application()
            self.assertEqual(polling._sessions, {})
        self.assertTrue(task.cancelled()); self.assertTrue(token.is_cancelled())
        self.assertEqual(self.store.get_all(), [])
        self.assertEqual(Path(self.paths['RESPONSE_STORE_PATH']).read_text(), '')
        self.assertEqual(Path(self.paths['CONVERSATION_HISTORY_PATH']).read_text(), '[]')
        request = await websocket.prepare_user_message({'source': 'user', 'content': 'fresh request'})
        self.assertEqual(request['content'], 'fresh request')

    async def test_missing_or_malformed_output_is_a_transport_error(self):
        from autogen_agentchat.messages import ToolCallExecutionEvent
        from autogen_core.models import FunctionExecutionResult
        bad = self.folder/'bad.geojson'; bad.write_text('{broken')
        for path in (self.folder/'absent.geojson', bad, None):
            response = GeoFahamToolResponse(response_id='bad-output', source='postgis_agent',
                                           artifact={'path': str(path)} if path is not None else None)
            event = ToolCallExecutionEvent(source='postgis_agent', content=[FunctionExecutionResult(
                name='execute_query', call_id='check', content=response.model_dump_json(), is_error=False)])
            result = await websocket.MessageProcessor.process_tool_execution(event)
            self.assertEqual(result.type, 'error')
            self.assertTrue(result.error_message)

    async def test_reset_cancels_polling_work_even_before_it_starts(self):
        session = polling.PollingSession('multi-agent')
        with patch.dict(polling._sessions, {'queued': session}), patch.object(session, 'process_message', new_callable=AsyncMock) as run:
            await polling.polling_send(polling.SendRequest(session_id='queued', content='old request'))
            await reset.reset_application()
            run.assert_not_awaited()
            self.assertEqual(active_chat_tasks, {})
            self.assertEqual(polling._sessions, {})


class BboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_neighborhood_queries_use_shared_bbox_helper(self):
        from agents.maps_agent import geocoding_tools, utils
        empty = gpd.GeoDataFrame(geometry=[], crs=4326)
        with patch.object(utils.ox, 'features_from_bbox', return_value=empty) as fetch:
            result = GeoFahamToolResponse.model_validate_json(await geocoding_tools.get_neighborhoods(
                bbox=[38.66, 38.65, -90.294, -90.304]))
        self.assertEqual(result.type, 'empty')
        self.assertEqual(fetch.call_count, 2)
        for call in fetch.call_args_list:
            self.assertEqual(call.args, ((-90.304, 38.65, -90.294, 38.66),))

    async def test_named_feature_search_uses_shared_bbox_helper(self):
        from agents.maps_agent import geocoding_tools, utils
        empty = gpd.GeoDataFrame(geometry=[], crs=4326)
        with patch.object(utils.ox, 'features_from_bbox', return_value=empty) as fetch:
            result = GeoFahamToolResponse.model_validate_json(await geocoding_tools.search_feature_by_name(
                'Test Road', bbox=[38.66, 38.65, -90.294, -90.304]))
        self.assertIn('Could not find road', result.error_message)
        self.assertEqual(fetch.call_args.args, ((-90.304, 38.65, -90.294, 38.66),))

    async def test_all_feature_tools_use_correct_osmnx_bounds(self):
        from agents.maps_agent import feature_tools, utils
        names = ['get_roads', 'get_buildings', 'get_waterways', 'get_bridges', 'get_pois',
                 'get_landuse', 'get_natural_features', 'get_infrastructure', 'get_features_by_tags']
        empty = gpd.GeoDataFrame(geometry=[], crs=4326)
        for name in names:
            with self.subTest(tool=name), patch.object(utils.ox, 'features_from_bbox', return_value=empty) as fetch:
                kwargs = {'bbox': [38.66, 38.65, -90.294, -90.304]}
                if name == 'get_features_by_tags': kwargs['tags'] = {'highway': True}
                result = GeoFahamToolResponse.model_validate_json(await getattr(feature_tools, name)(**kwargs))
                self.assertEqual(result.type, 'empty')
                self.assertEqual(fetch.call_args.args, ((-90.304, 38.65, -90.294, 38.66),))
                self.assertIn('tags', fetch.call_args.kwargs)


class RasterGridTests(unittest.IsolatedAsyncioTestCase):
    async def test_raster_loader_preserves_multiple_bands_and_single_band_behavior(self):
        with tempfile.TemporaryDirectory() as folder:
            transform = from_origin(500000, 4300020, 10, 10)
            source = np.array([[[-9999, .2], [.4, .6]], [[-9999, .6], [.8, .9]]], dtype="float32")
            for count in (1, 2):
                with self.subTest(count=count):
                    path = Path(folder) / f"bands_{count}.tif"
                    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=count,
                                       dtype="float32", crs=32615, transform=transform, nodata=-9999) as ds:
                        ds.write(source[:count])
                        for band, label in enumerate(("red", "nir")[:count], 1):
                            ds.set_band_description(band, label)
                    raster, epsg = RasterCodeExecutor().load_raster_file(str(path))
                    try:
                        expected = np.where(source[:count] == -9999, np.nan, source[:count])
                        np.testing.assert_allclose(raster.values, expected[0] if count == 1 else expected,
                                                   equal_nan=True)
                        self.assertEqual(epsg, 32615)
                        self.assertEqual(raster.rio.transform(), transform)
                        self.assertEqual(raster.dims, ("y", "x") if count == 1 else ("band", "y", "x"))
                        if count == 2:
                            red, nir = raster.sel(band=1), raster.sel(band=2)
                            ndvi = (nir-red)/(nir+red)
                            np.testing.assert_allclose(ndvi.values, (expected[1]-expected[0])/(expected[1]+expected[0]),
                                                       equal_nan=True)
                            self.assertEqual(raster.attrs["long_name"], ("red", "nir"))
                    finally:
                        raster.close()

    async def test_real_stac_stack_and_export_preserve_source_pixel_locations(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); transform = from_origin(740000, 2310000, 10, 10)
            arrays = {'B04': np.arange(1, 65, dtype='float64').reshape(8, 8),
                      'B08': np.arange(11, 75, dtype='float64').reshape(8, 8)}
            for band, arr in arrays.items():
                with rasterio.open(folder/f'{band}.tif', 'w', driver='GTiff', width=8, height=8,
                                   count=1, dtype='float64', crs=32604, transform=transform) as ds: ds.write(arr, 1)
            bbox = rasterio.warp.transform_bounds(32604, 4326, 740000, 2309920, 740080, 2310000)
            item = {'type': 'Feature', 'stac_version': '1.0.0', 'id': 'local-grid', 'bbox': list(bbox),
                    'geometry': mapping(box(*bbox)), 'properties': {'datetime': '2023-08-28T12:00:00Z',
                    'proj:code': 'EPSG:32604'}, 'links': [], 'assets': {band: {
                        'href': str(folder/f'{band}.tif'), 'type': 'image/tiff', 'proj:epsg': 32604,
                        'proj:shape': [8, 8], 'proj:transform': list(transform)[:6]} for band in arrays}}
            items = folder/'items.json'; items.write_text(json.dumps(collection(item)))
            da, epsg = RasterCodeExecutor(temporal_mode='single_scene').load_stac_items(
                str(items), list(bbox), ['B04', 'B08'], resolution=10)
            nir, red = da.sel(band='B08').isel(time=0), da.sel(band='B04').isel(time=0)
            ndvi = ((nir-red)/(nir+red)).rio.write_crs(epsg)
            with patch.object(io_utils, 'QUERY_JSONS_PATH', str(folder)):
                output = await io_utils.write_result_as_cog(ndvi, 'ndvi')
            with rasterio.open(output) as ds:
                self.assertAlmostEqual(ds.transform.c % 10, 0, places=6)
                self.assertAlmostEqual(ds.transform.f % 10, 0, places=6)
                values = ds.read(1); bands = {}
                for band in arrays:
                    with rasterio.open(folder/f'{band}.tif') as src:
                        with WarpedVRT(src, crs=ds.crs, transform=ds.transform, width=ds.width, height=ds.height) as vrt:
                            bands[band] = vrt.read(1)
                valid = np.isfinite(values)
                expected = (bands['B08'][valid]-bands['B04'][valid])/(bands['B08'][valid]+bands['B04'][valid])
                np.testing.assert_allclose(values[valid], expected, atol=1e-12)
                np.testing.assert_allclose(io_utils.get_bounds(ndvi), rasterio.warp.transform_bounds(ds.crs, 4326, *ds.bounds))

    async def test_float_nodata_masks_match_saved_values_in_both_writers(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(io_utils, 'QUERY_JSONS_PATH', folder):
            for nodata in (-9999.0, np.nan, None):
                da = xr.DataArray([[.25, np.nan], [np.inf, -np.inf]], dims=('y', 'x'),
                                  coords={'y': [1.5, .5], 'x': [.5, 1.5]}).rio.write_crs(4326)
                if nodata is not None: da = da.rio.write_nodata(nodata)
                paths = [await io_utils.write_result_as_cog(da, 'float'),
                         io_utils.save_intermediate_layer(da, 'intermediate')]
                for path in paths:
                    with rasterio.open(path) as ds:
                        np.testing.assert_array_equal(ds.read_masks(1), [[255, 0], [0, 0]])
                        self.assertEqual(ds.read(1, masked=True).count(), 1)
                        self.assertEqual(float(ds.read(1, masked=True).mean()), .25)


if __name__ == '__main__': unittest.main()
