"""Statistics survive the real interpreter, executor and tool response."""
import re
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import dask
import numpy as np
import xarray as xr

from agents.core.types import GeoFahamToolResponse
from agents.raster_ops_agent._prompts import SYS_PROMPT
from agents.raster_ops_agent.executor import RasterCodeExecutor
from agents.raster_ops_agent.tools import _execute_custom_raster_code as execute_custom_raster_code
from agents.shared.responses import validate_response_artifacts


class RasterStatisticsContractTests(unittest.IsolatedAsyncioTestCase):
    async def run_code(self, code, metric=None):
        executor = RasterCodeExecutor()
        if metric is not None:
            executor.aeval.symtable['load_raster_file'] = lambda path: (metric, 32615)
        # Keep execution real without opening Dask network sockets in unit tests.
        with patch('agents.raster_ops_agent.tools.RasterCodeExecutor', return_value=executor), \
                patch('agents.raster_ops_agent.executor.LocalCluster', return_value=nullcontext()), \
                patch('agents.raster_ops_agent.executor.Client', return_value=nullcontext()), \
                dask.config.set(scheduler='synchronous'):
            response = await execute_custom_raster_code(code, 'Summary statistics', False, 'statistics')
        return GeoFahamToolResponse.model_validate_json(response)

    async def test_named_statistics_and_metadata_reach_the_response(self):
        response = await self.run_code(
            "result = {'mean': 0.5, 'count': 0, 'undefined': None, 'quantiles': {'p50': 0.5}}\n"
            "metadata = {'units': 'NDVI'}")
        self.assertEqual(response.type, 'data')
        self.assertEqual(response.data_type, 'stats')
        self.assertEqual(response.data, [{'mean': .5, 'count': 0, 'undefined': None,
                                          'quantiles': {'p50': .5}}])
        self.assertEqual(response.metadata['units'], 'NDVI')
        self.assertIn('source_scene_ids', response.metadata)
        self.assertIsNone(response.artifact)
        validate_response_artifacts(response)

    async def test_invalid_statistics_do_not_succeed_with_an_empty_layer_response(self):
        for code in ('result = 0.5', 'result = {}',
                     "result = None\nmetadata = {'stats': {'mean': 0.5}}"):
            with self.subTest(code=code):
                response = await self.run_code(code)
                self.assertEqual(response.type, 'error')

    async def test_literal_prompt_example_handles_nodata_and_all_missing_input(self):
        code = re.search(r'Statistics-only example.*?```python\n(.*?)```', SYS_PROMPT, re.S).group(1)
        for values, expected in (
            ([np.nan, -9999., np.inf, -np.inf, .2, .8], {'valid_pixels': 2, 'mean': .5}),
            ([np.nan, -9999., np.inf, -np.inf], {'valid_pixels': 0, 'mean': None}),
        ):
            with self.subTest(values=values):
                metric = xr.DataArray(values, dims='x').rio.write_nodata(-9999.)
                response = await self.run_code(code, metric)
                self.assertEqual(response.type, 'data')
                self.assertEqual(response.data_type, 'stats')
                self.assertEqual(response.data, [expected])


if __name__ == '__main__':
    unittest.main()
