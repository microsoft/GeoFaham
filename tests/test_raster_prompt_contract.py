"""Execute the Raster prompt's classification example and verify exported masks."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
import xarray as xr

from agents.raster_ops_agent._prompts import SYS_PROMPT
from agents.raster_ops_agent.executor import RasterCodeExecutor
from agents.raster_ops_agent import io_utils


class RasterPromptContractTests(unittest.IsolatedAsyncioTestCase):
    async def check_example(self, values, nodata, expected, fraction):
        code = re.search(r'6\.2 STEP 2\+ PATTERN: Apply Decisions.*?```python\n(.*?)```',
                         SYS_PROMPT, re.S).group(1)
        metric = xr.DataArray(values, dims=('y', 'x'),
                              coords={'y': [4300015., 4300005.], 'x': [500005., 500015.]})
        metric = metric.rio.write_crs(32615)
        if nodata is not None:
            metric = metric.rio.write_nodata(nodata)
        executor = RasterCodeExecutor()
        executor.aeval.symtable['load_raster_file'] = lambda path: (metric.copy(), 32615)
        executor.aeval(code)
        self.assertEqual(executor.aeval.error, [])
        result = executor.aeval.symtable['result']
        stats = executor.aeval.symtable['metadata']['stats']
        expected = np.asarray(expected, dtype='uint8')
        np.testing.assert_array_equal(result.values, expected)
        self.assertEqual(stats['total_pixels'], int((expected != 255).sum()))
        self.assertEqual(stats['positive_pixels'], int((expected == 1).sum()))
        self.assertEqual(stats['positive_fraction'], fraction)
        with tempfile.TemporaryDirectory() as folder, patch.object(io_utils, 'QUERY_JSONS_PATH', folder):
            path = await io_utils.write_result_as_cog(result, 'classification')
            with rasterio.open(path) as ds:
                np.testing.assert_array_equal(ds.read(1), expected)
                np.testing.assert_array_equal(ds.read_masks(1) > 0, expected != 255)
                self.assertEqual(ds.nodata, 255)
                self.assertEqual(ds.crs.to_epsg(), 32615)
                self.assertEqual(ds.transform, metric.rio.transform())
                self.assertEqual(ds.read(1, masked=True).count(), stats['total_pixels'])

    async def test_classification_preserves_missing_values_and_valid_class_zero(self):
        cases = [
            ([[np.nan, -9999.], [.2, .5]], -9999., [[255, 255], [0, 1]], .5),
            ([[np.nan, 9999.], [.2, .5]], 9999., [[255, 255], [0, 1]], .5),
            ([[np.inf, -np.inf], [.2, .5]], None, [[255, 255], [0, 1]], .5),
            ([[np.nan, .42], [.5, .8]], np.nan, [[255, 0], [1, 1]], 2/3),
        ]
        for values, nodata, expected, fraction in cases:
            with self.subTest(values=values, nodata=nodata):
                await self.check_example(values, nodata, expected, fraction)

    async def test_all_missing_input_does_not_report_a_zero_percent_result(self):
        await self.check_example([[np.nan, -9999.], [np.inf, -np.inf]], -9999.,
                                 [[255, 255], [255, 255]], None)


if __name__ == '__main__':
    unittest.main()
