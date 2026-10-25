# Raster code execution

The Raster Agent uses `execute_custom_raster_code()` to run generated Python.
This lets it combine band math, masking, classification, vectorization, and
statistics within a workflow. The implementation is in
[tools.py](../agents/raster_ops_agent/tools.py) and
[executor.py](../agents/raster_ops_agent/executor.py).

## Tool arguments

| Argument | Meaning |
|----------|---------|
| `code` | Python that assigns its output to `result` |
| `result_explanation` | Description of the computed output |
| `return_layer` | Whether to return a map layer |
| `expected_result_type` | `raster`, `vector`, `statistics`, or `mix` |
| `temporal_mode` | `unspecified`, `single_scene`, `composite`, or `change_detection` |

The executor exposes `xr`, `np`, `gpd`, `shapely`, `scipy`, `skimage`,
`datetime`, and `rasterio`, along with loading and clipping helpers.

| Helper | Return value |
|--------|--------------|
| `load_stac_items(items_json_path, bbox, bands, resolution=10, properties_filter=None)` | DataArray and EPSG code |
| `load_raster_file(path)` | DataArray and optional EPSG code |
| `load_vector_file(path)` | GeoDataFrame and EPSG code |
| `clip_to_aoi(da, aoi_gdf)` | Clipped DataArray |

## Execution and outputs

Each tool call runs in a spawned process through `asteval` with a local Dask
cluster. The executor reads `result` and optional `metadata`, computes lazy
outputs, and passes them to
result handlers. Depending on their type, results can become COG rasters,
GeoJSON layers, statistics, or temporal outputs. Exceptions and interpreter
errors are returned as tool errors for the agent to inspect.

For statistics only, use `expected_result_type="statistics"`, `return_layer=False`,
and assign a non-empty dictionary to `result`, for example `result={"mean": 0.5}`.
Values must be JSON-compatible; use `None` for undefined statistics. The response
has `type="data"`, `data_type="stats"`, and `data=[{"mean": 0.5}]`.
Optional `metadata` holds context and provenance. When returning raster/vector
outputs or saved intermediates, accompanying statistics can remain in `metadata["stats"]`.
Final GeoDataFrame outputs require `return_layer=True`; statistics-only requests
must return a named statistics dictionary instead of a GeoDataFrame.

## Dates and spatial scope

For single-date imagery, use `temporal_mode="single_scene"` and select one
timestamp with `properties_filter` before loading. The executor rejects multiple
acquisition dates and records source scene IDs and dates in the output provenance.
Composites require an explicit user request.

The tools currently target small AOIs. Dask delays computation, but export and
statistics materialize arrays locally. There is no distributed tile-processing
pipeline or preflight memory budget for large-area requests.

## Process limits

The Raster tool stops its worker on cancellation or timeout (300 seconds by
default, including startup and export). Direct calls to
`RasterCodeExecutor.execute()` bypass that process and time limit.

`asteval` exposes the listed libraries and helpers. Direct `open`, `eval`, `exec`,
and `compile` functions are excluded, but exposed library objects retain file
and network capabilities. The worker has no OS-level filesystem, network, or
memory isolation.

See [configuration](CONFIGURATION.md#execution-limits) for timeout settings and
[tool responses](TOOL_RESPONSE_SCHEMAS.md) for output fields.
