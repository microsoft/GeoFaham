# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoFaham Shared Utilities

Common utilities for GeoJSON processing, serialization, analysis, and response building.
"""

from agents.shared.serialization import serialize_value, serialize_properties
from agents.shared.geojson import (
    results_to_geojson,
    parse_geojson_files,
    classify_geometry_type,
    generate_response_id,
)
from agents.shared.analysis import (
    analyze_geojson_features,
    analyze_geojson,
    collect_property_schema,
    infer_python_type,
)
from agents.shared.responses import (
    build_layer_response,
    build_raster_layer_response,
    build_data_response,
    build_stac_items_response,
    build_timeline_response,
    build_empty_response,
    build_error_response,
    build_intermediate_response,
    parse_response,
    is_error_response,
    get_artifact_path,
)

__all__ = [
    # Serialization
    "serialize_value",
    "serialize_properties",
    # GeoJSON
    "results_to_geojson",
    "parse_geojson_files",
    "classify_geometry_type",
    "generate_response_id",
    # Analysis
    "analyze_geojson_features",
    "analyze_geojson",
    "collect_property_schema",
    "infer_python_type",
    # Response Builders
    "build_layer_response",
    "build_raster_layer_response",
    "build_data_response",
    "build_stac_items_response",
    "build_timeline_response",
    "build_empty_response",
    "build_error_response",
    "build_intermediate_response",
    "parse_response",
    "is_error_response",
    "get_artifact_path",
]
