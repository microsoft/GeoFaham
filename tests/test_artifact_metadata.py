"""Compare declared artifact metadata with actual files before agent dispatch."""
import json
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box, mapping
from autogen_core import CancellationToken

from agents.core.types import GeoFahamToolResponse
from agents.core.config import AgentsConfig, ConfigProvider
from agents.shared.geojson import results_to_geojson
from agents.shared.responses import validate_response_artifacts
from agents.raster_ops_agent import io_utils, tools as raster_tools
from agents.maps_agent import feature_tools
from agents.vector_agent.tools import VectorQueryExecutor
import geopandas as gpd
import xarray as xr
from agents.orchestrator_agent.orchestrator import GeoFahamOrchestrator
from tests.test_workflow_contracts import ledger, manager


class ArtifactMetadataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def vector(self, *geometries):
        path = self.root/'features.geojson'
        path.write_text(json.dumps({'type':'FeatureCollection', 'features':[
            {'type':'Feature', 'properties':{}, 'geometry':mapping(geometry)} for geometry in geometries]}))
        return GeoFahamToolResponse(response_id='vector_input',source='user',data_type='vector',
            artifact={'path':str(path),'format':'geojson','features_count':len(geometries),
                      'geom_types':list({geometry.geom_type for geometry in geometries})})

    def raster(self, count=1, metadata=None):
        path = self.root/'raster.tif'
        with rasterio.open(path,'w',driver='GTiff',width=2,height=2,count=count,dtype='float32',
                           crs=32615,transform=from_origin(500000,4300020,10,10)) as ds:
            ds.write(np.zeros((count,2,2),dtype='float32'))
        return GeoFahamToolResponse(response_id='raster_input',source='user',data_type='raster',
            artifact={'path':str(path),'format':'geotiff','metadata':metadata or {}})

    def test_actual_mixed_geometry_types_and_feature_count_are_accepted(self):
        response = self.vector(Point(0,0),Point(1,1),box(0,0,1,1))
        validate_response_artifacts(response)
        response.artifact.geom_types.reverse()
        validate_response_artifacts(response)

    def test_incorrect_geometry_declaration_is_rejected(self):
        response = self.vector(Point(0,0))
        response.artifact.geom_types = ['Polygon']
        with self.assertRaisesRegex(ValueError,'geometry types do not match'):
            validate_response_artifacts(response)

    def test_incorrect_feature_count_is_rejected(self):
        response = self.vector(Point(0,0))
        response.artifact.features_count = 2
        with self.assertRaisesRegex(ValueError,'feature count does not match'):
            validate_response_artifacts(response)

    def test_missing_geometry_cannot_satisfy_a_declared_geometry_type(self):
        response = self.vector(Point(0,0))
        path = Path(response.artifact.path)
        payload = json.loads(path.read_text()); payload['features'][0]['geometry'] = None
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'missing or malformed geometry'):
            validate_response_artifacts(response)

    def test_correct_single_and_multiband_declarations_are_accepted(self):
        for count, bands in ((1,['metric']),(2,['B04','B08'])):
            with self.subTest(count=count):
                validate_response_artifacts(self.raster(count,{'crs':'EPSG:32615',
                    'band_count':count,'bands':bands}))

    def test_incorrect_band_count_or_band_list_is_rejected(self):
        for metadata in ({'band_count':2},{'bands':['B04','B08']},{'bands':'B04'}):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError,'band'):
                validate_response_artifacts(self.raster(1,metadata))

    def test_omitted_optional_metadata_remains_compatible(self):
        response = self.vector(Point(0,0))
        response.artifact.geom_types = None
        response.artifact.features_count = None
        validate_response_artifacts(response)
        validate_response_artifacts(self.raster(1,{'bands':[]}))

    async def test_orchestrator_blocks_mismatches_even_when_ledger_claims_inputs_are_valid(self):
        vector = self.vector(Point(0,0)); vector.artifact.geom_types = ['Polygon']
        raster = self.raster(1,{'bands':['B04','B08']})
        for response in (vector,raster):
            with self.subTest(response=response.response_id):
                obj = manager([ledger(inputs=[response.response_id])],[response])
                await GeoFahamOrchestrator._orchestrate_step(obj,CancellationToken())
                obj.update_message_thread.assert_not_awaited()
                self.assertIn('incomplete work',obj._prepare_final_answer.call_args.args[0])
                self.assertIn('band' if response.data_type=='raster' else 'geometry types',
                              obj._prepare_final_answer.call_args.args[0])


class GeneratedMetadataTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        cfg = AgentsConfig(); cfg.paths.base_dir = self.root
        self.stack.enter_context(ConfigProvider.override(cfg))
        self.stack.enter_context(patch.object(io_utils,'QUERY_JSONS_PATH',str(cfg.paths.export_dir)))

    async def test_vector_metadata_is_populated_with_or_without_statistics(self):
        for statistics in (True,False):
            with self.subTest(statistics=statistics):
                artifact = await results_to_geojson({'type':'FeatureCollection','features':[
                    {'type':'Feature','properties':{'name':'area'},'geometry':mapping(box(-90.31,38.65,-90.30,38.66))}]},
                    compute_stats=statistics)
                self.assertEqual(artifact.metadata,{'crs':'EPSG:4326','bounds':[-90.31,38.65,-90.30,38.66]})

    async def test_maps_and_vector_responses_preserve_the_artifact_metadata(self):
        frame = gpd.GeoDataFrame({'name':['Area']},geometry=[box(-90.31,38.65,-90.30,38.66)],crs=4326)
        with patch.object(feature_tools,'run_osmnx_async',new=AsyncMock(return_value=frame)):
            response = GeoFahamToolResponse.model_validate_json(await feature_tools.get_buildings(place_name='Test area'))
        self.assertEqual(response.artifact.metadata,{'crs':'EPSG:4326','bounds':[-90.31,38.65,-90.30,38.66]})
        executor = object.__new__(VectorQueryExecutor)
        for aggregate in (False,True):
            with self.subTest(aggregate=aggregate):
                response = GeoFahamToolResponse.model_validate_json(await executor._build_layer_response(
                    [{'name':'Area','geom':json.dumps(mapping(frame.geometry.iloc[0]))}],
                    'vector_result','test','geom',False,aggregate))
                self.assertEqual(response.artifact.metadata,{'crs':'EPSG:4326','bounds':[-90.31,38.65,-90.30,38.66]})
                validate_response_artifacts(response)

    def metric(self):
        return xr.DataArray(np.arange(4,dtype='float32').reshape(2,2),dims=('y','x'),
            coords={'y':[4300030.,4300010.],'x':[500005.,500015.]}).rio.write_crs(32615)

    def assert_raster_metadata(self,metadata,path):
        with rasterio.open(path) as saved:
            self.assertEqual(metadata['crs'],saved.crs.to_string())
            self.assertEqual(metadata['bounds'],list(saved.bounds))
            self.assertEqual(metadata['resolution'],list(saved.res))
            self.assertEqual(metadata['band_count'],saved.count)
            self.assertEqual(metadata['bands'],list(saved.descriptions))

    async def test_single_raster_metadata_uses_actual_saved_grid_and_band_descriptions(self):
        metric = self.metric()
        for result, labels in ((metric,[None]),
                              (metric.expand_dims(band=[1,2]).assign_attrs(long_name=['red','nir']),['red','nir'])):
            with self.subTest(labels=labels), patch.object(raster_tools.RasterCodeExecutor,'execute',
                    return_value={'result':result,'metadata':{}}):
                response = GeoFahamToolResponse.model_validate_json(await raster_tools._execute_custom_raster_code(
                    'result=test','test',True,'raster'))
                self.assert_raster_metadata(response.artifact.metadata,response.artifact.path)
                self.assertEqual(response.artifact.metadata['resolution'],[10.,20.])
                self.assertEqual(response.artifact.metadata['bands'],labels)
                validate_response_artifacts(response)

    async def test_timeline_layers_include_their_own_saved_file_metadata(self):
        metric = self.metric()
        with patch.object(raster_tools.RasterCodeExecutor,'execute',return_value={
                'result':{'metric':{'2024-01':metric,'2024-02':metric+1}},'metadata':{}}):
            response = GeoFahamToolResponse.model_validate_json(await raster_tools._execute_custom_raster_code(
                'result=test','test timeline',True,'raster'))
        layers = response.data[0]['layers']['metric']['temporal_layers']
        self.assertEqual(len(layers),2)
        for layer in layers:
            self.assert_raster_metadata(layer['metadata'],layer['url'])
        validate_response_artifacts(response)


if __name__=='__main__':
    unittest.main()
