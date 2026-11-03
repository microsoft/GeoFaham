"""Regression checks for immutable search artifacts and complete tool outputs."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Point, box, mapping

from agents.core.types import GeoFahamToolResponse
from agents.core.config import AgentsConfig, ConfigProvider
from agents.raster_ops_agent import tools as raster
from agents.shared.responses import validate_response_artifacts
from agents.stac_agent import tools as stac
from agents.stac_agent.collection_groups import CollectionGroup, validate_required_groups


def search_result(date):
    return {
        'items': [{'type': 'Feature', 'id': date, 'geometry': mapping(box(0, 0, 1, 1)),
                   'properties': {'datetime': date}, 'assets': {}}],
        'item_count': 1, 'coverage_percent': 100, 'bands': ['B04', 'B08'],
    }


class StacResultIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_searches_do_not_overwrite_previous_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            aoi = Path(folder) / 'aoi.geojson'
            aoi.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
                {'type': 'Feature', 'properties': {}, 'geometry': mapping(box(0, 0, 1, 1))}]}))
            def search(**arguments):
                return search_result(arguments['date1']), None
            with patch.object(stac, 'get_export_dir', return_value=folder), \
                    patch.object(stac.pystac_client.Client, 'open'), \
                    patch.object(stac, 'search_single_collection', side_effect=search), \
                    patch.object(stac, '_get_population_stats', return_value=None), \
                    patch.object(stac, 'analyze_temporal_coverage', return_value={}):
                snapshots = []
                # Repeating the identical request must also preserve existing references.
                for date in ('2023-08-01', '2023-09-01', '2023-09-01'):
                    response = GeoFahamToolResponse.model_validate_json(await stac.execute_stac_search(
                        {'imagery': {'collection_ids': ['sentinel-2-l2a'], 'priority': 'high',
                                     'daterange1': date}}, str(aoi)))
                    self.assertEqual(response.type, 'data')
                    validate_response_artifacts(response)
                    path = Path(response.artifact.path)
                    self.assertEqual(json.loads(path.read_text())['features'][0]['id'], date)
                    snapshots.append((path, path.read_bytes()))
                self.assertEqual(len({path for path, _ in snapshots}), 3)
                for path, content in snapshots:
                    self.assertEqual(path.read_bytes(), content)

    def test_two_period_search_tries_fallback_until_both_periods_are_available(self):
        group = CollectionGroup('comparison', ['primary', 'fallback'], 'high',
                                daterange1='pre', daterange2='post')
        with patch.object(stac, 'search_single_collection', side_effect=[
            (search_result('primary-pre'), None),
            (search_result('fallback-pre'), search_result('fallback-post')),
        ]) as search:
            results, required = stac._search_all_groups(None, [group], [0, 0, 1, 1], 50, 80)
        self.assertEqual(search.call_count, 2)
        self.assertEqual(required['comparison'], 'fallback')
        self.assertEqual(results['comparison']['date1_result']['items'][0]['id'], 'fallback-pre')
        self.assertEqual(results['comparison']['date2_result']['items'][0]['id'], 'fallback-post')

    def test_missing_second_period_fails_the_required_group(self):
        group = CollectionGroup('comparison', ['primary', 'fallback'], 'high',
                                daterange1='pre', daterange2='post')
        with patch.object(stac, 'search_single_collection', return_value=(search_result('pre'), None)):
            results, required = stac._search_all_groups(None, [group], [0, 0, 1, 1], 50, 80)
        self.assertEqual(validate_required_groups(required), (False, ['comparison']))
        self.assertIsNone(results['comparison']['collection_id'])

    def test_single_period_search_does_not_require_a_second_period(self):
        group = CollectionGroup('imagery', ['primary', 'fallback'], 'high', daterange1='date')
        with patch.object(stac, 'search_single_collection', return_value=(search_result('date'), None)) as search:
            _, required = stac._search_all_groups(None, [group], [0, 0, 1, 1], 50, 80)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(validate_required_groups(required), (True, []))


class RasterVectorOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_vector_without_layer_is_a_clear_error_not_a_broken_artifact(self):
        frame = gpd.GeoDataFrame({'name': ['test']}, geometry=[Point(0, 0)], crs=4326)
        with patch.object(raster.RasterCodeExecutor, 'execute', return_value={'result': frame, 'metadata': {}}):
            response = GeoFahamToolResponse.model_validate_json(
                await raster._execute_custom_raster_code('result = test', 'test', False, 'vector'))
        self.assertEqual(response.type, 'error')
        self.assertIsNone(response.artifact)
        self.assertIn('return_layer=True', response.error_message)
        self.assertIn('statistics', response.error_message)

    async def test_vector_with_layer_still_exports_a_readable_geojson(self):
        frame = gpd.GeoDataFrame({'name': ['test']}, geometry=[Point(0, 0)], crs=4326)
        with tempfile.TemporaryDirectory() as folder:
            config = AgentsConfig()
            config.paths.base_dir = Path(folder)
            with ConfigProvider.override(config), patch.object(
                    raster.RasterCodeExecutor, 'execute', return_value={'result': frame, 'metadata': {}}):
                response = GeoFahamToolResponse.model_validate_json(
                    await raster._execute_custom_raster_code('result = test', 'test', True, 'vector'))
                self.assertEqual(response.type, 'layer')
                validate_response_artifacts(response)
                features = json.loads(Path(response.artifact.path).read_text())['features']
                self.assertEqual(features[0]['properties']['name'], 'test')


if __name__ == '__main__':
    unittest.main()
