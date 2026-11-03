"""Check executable prompt examples against their real interfaces."""
import inspect
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
import xarray as xr

from agents.orchestrator_agent import _prompts as orchestrator
from agents.orchestrator_agent._prompt_progress import ORCHESTRATOR_PROGRESS_LEDGER_PROMPT
from agents.raster_ops_agent._prompts import SYS_PROMPT
from agents.raster_ops_agent.executor import RasterCodeExecutor
from agents.raster_ops_agent import io_utils
from agents.stac_agent._prompts import STAC_SYSTEM_PROMPT
from agents.stac_agent.tools import execute_stac_search
from agents.stac_agent.collection_groups import parse_collections_input


class AgentPromptExampleTests(unittest.IsolatedAsyncioTestCase):
    def test_stac_json_examples_are_valid_tool_arguments(self):
        blocks = re.findall(r'```json\n(.*?)```', STAC_SYSTEM_PROMPT, re.S)
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            arguments = json.loads(block)
            inspect.signature(execute_stac_search).bind(**arguments)
            # The first block is explicitly a shape template; the others are concrete examples.
            if '<group_name>' not in arguments['collections']:
                groups = parse_collections_input(arguments['collections'])
                self.assertTrue(groups)

    def test_orchestrator_prompts_render_with_the_runtime_placeholders(self):
        values = dict(task='test', facts='facts', plan='plan', team='team',
                      names='postgis_agent', planning_guidance='guidance',
                      **orchestrator.AGENT_PLACEHOLDERS)
        for name, prompt in vars(orchestrator).items():
            if name.startswith('ORCHESTRATOR_') and isinstance(prompt, str):
                with self.subTest(prompt=name):
                    self.assertTrue(prompt.format(**values))
        self.assertTrue(ORCHESTRATOR_PROGRESS_LEDGER_PROMPT.format(**values))

    async def test_explore_example_saves_a_real_intermediate_with_computed_statistics(self):
        code = re.search(r'6\.1 STEP 1 PATTERN: Explore & Save.*?```python\n(.*?)```',
                         SYS_PROMPT, re.S).group(1)
        for values, expected_count, expected_mean in (
            ([[np.nan, -9999.], [.2, .8]], 2, .5),
            ([[np.nan, -9999.], [np.inf, -np.inf]], 0, None),
        ):
            with self.subTest(values=values):
                metric = xr.DataArray(values, dims=('y', 'x'),
                    coords={'y': [4300015., 4300005.], 'x': [500005., 500015.]})
                metric = metric.rio.write_crs(32615).rio.write_nodata(-9999.)
                executor = RasterCodeExecutor()
                executor.aeval.symtable['load_raster_file'] = lambda path: (metric, 32615)
                executor.aeval(code)
                self.assertEqual(executor.aeval.error, [])
                metadata = executor.aeval.symtable['metadata']
                self.assertEqual(metadata['stats']['valid_pixels'], expected_count)
                self.assertEqual(metadata['stats']['mean'], expected_mean)
                self.assertTrue(metadata['save_as_intermediate'])
                with tempfile.TemporaryDirectory() as folder, patch.object(io_utils, 'QUERY_JSONS_PATH', folder):
                    saved = io_utils.save_intermediate_results(executor.aeval.symtable['result'], 'example')
                    path = next(iter(saved['saved_intermediate_paths'].values()))
                    self.assertTrue(Path(path).is_file())
                    with rasterio.open(path) as ds:
                        self.assertEqual(ds.crs.to_epsg(), 32615)
                        self.assertEqual(ds.transform, metric.rio.transform())
                        self.assertEqual(ds.read(1, masked=True).count(), expected_count)


if __name__ == '__main__':
    unittest.main()
