# Tool responses

Agent tools return a JSON string representing
[`GeoFahamToolResponse`](../agents/core/types.py). Use the builders in
[responses.py](../agents/shared/responses.py) when adding a tool.

## Common fields

| Field | Meaning | Default |
|-------|---------|---------|
| `response_id` | ID used to reference the response in later steps | Required |
| `source` | Producing agent, such as `postgis_agent` or `stac_agent` | Required |
| `type` | `layer`, `data`, `error`, or `empty` | `layer` |
| `data_type` | Content type listed below | `vector` |
| `data` | Inline rows or references | `[]` |
| `summary` | Description of the result | `""` |
| `error_message` | Error details | `null` |
| `artifact` | Saved file and its metadata | `null` |
| `metadata` | Tool-specific context, provenance, or display settings | `null` |

`type` describes the outcome; `data_type` describes its contents.

| `type` | Contents |
|--------|----------|
| `layer` | Map output, usually with an artifact |
| `data` | Inline rows, statistics, imagery references, or saved intermediate references |
| `empty` | Successful query with no results; explanation in `summary` |
| `error` | Failed operation; details in `error_message` |

| `data_type` | Use |
|-------------|-----|
| `vector` | GeoJSON geometry |
| `raster` | Single raster output |
| `raster_multi` | Multiple raster/vector outputs, possibly grouped by time |
| `raster_intermediate` | Saved outputs for later computation |
| `stac_items` | References to STAC item files for analysis |
| `timeline` | Imagery visualization with temporal metadata |
| `tabular` | Table rows |
| `json` | Other structured data |
| `stats` | Named statistics |
| `message` | Error, empty-result, or informational message |

## Saved artifacts

`artifact` is a [`SavedArtifact`](../agents/core/types.py). Its `path` points to
the saved file; the response does not embed that file's full contents.

| Field | Meaning |
|-------|---------|
| `path` | Required file path |
| `format` | `geojson` (default), `geotiff`, `json`, or `cog` |
| `content_type` | MIME type; defaults to `application/geo+json` |
| `bytes` | Optional file size |
| `features_count` | Optional feature or entry count; interpretation depends on the producer |
| `geom_types` | Optional GeoJSON geometry types |
| `property_keys` | Optional property schema grouped under `points`, `lines`, and `polygons` |
| `stats` | Optional geometry or raster statistics |
| `metadata` | Optional file metadata, including CRS and bounds |

GeoJSON property schemas describe each property's `type`, `nullable`, and
`fill_pct` where supplied. GeoJSON artifacts produced by the shared writer carry
`metadata.crs="EPSG:4326"` and `metadata.bounds`.

Raster metadata read from the saved file contains `crs`, `bounds`, `resolution`
as `[x, y]`, `band_count`, and `bands`. Bounds and resolution use the file's CRS.
Band descriptions can be `null` when the file has no names.

## Examples

These examples show the main fields; optional null fields and some metadata are
omitted. Counts and values are illustrative.

### Vector layer

Maps features, spatial Vector queries, and Raster vector outputs share this
structure. Layer responses may also include inline rows in `data`.

```json
{
  "response_id": "map_a1b2c3d4",
  "source": "osm_map_agent",
  "type": "layer",
  "data_type": "vector",
  "data": [],
  "summary": "Retrieved 2 roads.",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/roads.geojson",
    "format": "geojson",
    "content_type": "application/geo+json",
    "features_count": 2,
    "geom_types": ["LineString"],
    "metadata": {
      "crs": "EPSG:4326",
      "bounds": [-90.304, 38.65, -90.294, 38.66]
    }
  }
}
```

### Single raster

The Raster tool returns the file path in `artifact.path` and computed statistics
in `artifact.stats`. Its `data` array is empty for a single raster.

```json
{
  "response_id": "raster_a1b2c3d4",
  "source": "raster_ops_agent",
  "type": "layer",
  "data_type": "raster",
  "data": [],
  "summary": "Computed NDVI for the supplied AOI.",
  "artifact": {
    "path": "/runtime/artifacts/query_jsons/ndvi.tif",
    "format": "geotiff",
    "content_type": "image/tiff",
    "stats": {"valid_pixels": 2, "mean": 0.5},
    "metadata": {
      "crs": "EPSG:32604",
      "bounds": [740000, 2310000, 740020, 2310010],
      "resolution": [10, 10],
      "band_count": 1,
      "bands": [null]
    }
  }
}
```

The writer produces a COG; the single-raster response builder labels its format
`geotiff`. Execution details and generated-code metadata are held in the
response's `metadata`; generated provenance is nested under `metadata.metadata`.

### Statistics

For statistics-only Raster calls, set `expected_result_type="statistics"`,
`return_layer=False`, and assign a non-empty dictionary to `result`.
Values must be JSON-compatible; use `None` for undefined values in Python.

```json
{
  "response_id": "raster_b2c3d4e5",
  "source": "raster_ops_agent",
  "type": "data",
  "data_type": "stats",
  "data": [{"mean": 0.5, "valid_pixels": 2}],
  "summary": "Calculated mean and valid pixel count."
}
```

Vector queries without geometry return inline rows. Their `data_type` depends
on the tool's output settings; inspect it rather than assuming all numeric rows
use `stats`.

## Imagery and multiple outputs

### STAC fetch mode

`execute_stac_search(mode="fetch")` returns `type="data"`,
`data_type="stac_items"`. Each imagery entry in `data` contains:

| Field | Meaning |
|-------|---------|
| `type` | `stac_items` |
| `collection_group` | Requested collection group |
| `items_json_path` | File containing the STAC items |
| `search_params` | Collection, acquisition information, scene count, coverage, bounds, bands, temporal coverage, and AOI path |

Each file is a GeoJSON FeatureCollection whose `features` are STAC items,
including their `properties` and `assets`. Its top-level `metadata` holds the
search context. The response's `artifact.path` references the first file;
read all `items_json_path` entries when multiple groups or periods were returned.
For this response, `artifact.features_count` counts entries in `data`, not
individual satellite scenes. A population-statistics entry may also be present.

### STAC show mode

`execute_stac_search(mode="show")` returns `type="layer"`,
`data_type="timeline"`. The GeoJSON is referenced by `artifact.path` and `data`
is empty. Display settings are in `metadata`, including `visualization_hints`,
`mosaic_jsons`, and `stac_item_tiles` where available.

### Raster groups and saved intermediates

A Raster dictionary containing multiple outputs returns `type="data"`,
`data_type="raster_multi"`. Its execution payload appears in `data[0]` and
`metadata`, with named outputs under `layers`:

| Output | Fields |
|--------|--------|
| Single raster | `type="single_layer"`, `url`, `statistics`, WGS84 `bounds`, `min_scale`, `max_scale`, file `metadata` |
| Temporal raster sequence | `type="temporal_sequence"`, `temporal_layers`, `min_scale`, `max_scale` |
| Temporal entry | `label`, `url`, `statistics`, WGS84 `bounds`, file `metadata` |
| Vector | Serialized `SavedArtifact` with `path` and GeoJSON metadata |

These nested raster entries use `url` and `statistics`; the single-raster tool
response above uses `artifact.path` and `artifact.stats`.

With `metadata.save_as_intermediate=True`, the Raster tool saves results and
returns `type="data"`, `data_type="raster_intermediate"`. The saved references
are in `data[0]` and `metadata`, under `saved_intermediate_path` or
`saved_intermediate_paths`, with a `count`.

## Raster statistics

[compute_stats()](../agents/raster_ops_agent/io_utils.py) excludes nodata and
nonfinite values. Its output depends on the array's dtype:

| Input | Statistics |
|-------|------------|
| Floating point | `shape`, `valid_pixels`, `total_pixels`, `min`, `max`, `mean`, `std`, and `percentiles` (`p10`, `p25`, `p50`, `p75`, `p90`) |
| Integer | `shape`, `valid_pixels`, `total_pixels`, `min`, `max`, and `class_distribution` |
| No valid values | `count=0`, `valid_pixels=0`, and `total_pixels` |

`class_distribution` maps integer values to percentages of valid values; JSON
serializes its keys as strings. Integer dtype selects this summary even when
the values are not semantic classes. For multiband arrays, these statistics
summarize valid values across the array rather than reporting each band separately.

## Builders and consumers

| Builder | Response |
|---------|----------|
| `build_layer_response` | Layer, usually vector |
| `build_raster_layer_response` | Single raster layer |
| `build_data_response` | Inline structured data |
| `build_stac_items_response` | STAC file references |
| `build_timeline_response` | Imagery timeline |
| `build_intermediate_response` | Saved intermediate references |
| `build_empty_response` | Empty result |
| `build_error_response` | Failed operation |

[`get_available_responses(filter_errors=True)`](../agents/core/response_store.py)
returns an object with `message` and `responses`, rather than a
`GeoFahamToolResponse`. It excludes errors by default. See
[Response Store](RESPONSE_STORE.md) for registration and retrieval.

The frontend's [response router](../frontend/js/core/response-router.js) uses
`type`, `data_type`, and metadata markers to choose a renderer. STAC tile and
mosaic markers take precedence over general raster/vector routing. Transport
messages can wrap or normalize tool responses; see the
[web interface](UI_DOCUMENTATION.md) for rendering behavior.
