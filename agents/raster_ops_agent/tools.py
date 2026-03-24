# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Raster Operations Agent Tools - Execute custom Python code for raster analysis.
"""

import uuid
import time
import logging
import traceback
from typing import Annotated

import xarray as xr
import geopandas as gpd

from agents.core.types import GeoFahamToolResponse
from agents.core.constants import AGENT_NAMES
from agents.shared.geojson import generate_response_id, results_to_geojson
from agents.shared.responses import (
    build_layer_response,
    build_raster_layer_response,
    build_data_response,
    build_error_response,
    build_intermediate_response,
)
from agents.core.types import DataType, ArtifactFormat

from agents.raster_ops_agent.executor import RasterCodeExecutor, CodeExecutionError
from agents.raster_ops_agent.io_utils import (
    write_result_as_geojson,
    save_intermediate_results,
)
from agents.raster_ops_agent.result_handlers import (
    handle_single_raster,
    handle_temporal_sequence,
)

logger = logging.getLogger(__name__)
AGENT_NAME = AGENT_NAMES["RASTER_AGENT"]


async def execute_custom_raster_code(
    code: Annotated[str, "Python code using allowed libraries. Must assign final result to 'result' variable."],
    result_explanation: Annotated[str, "Clear explanation of what the result represents"],
    return_layer: Annotated[bool, "Whether to return a map layer (True) or just data/statistics (False)"],
    expected_result_type: Annotated[str, "Expected type of result: 'raster' (xarray.DataArray), 'vector' (GeoDataFrame), 'statistics' (dict/number), 'mix' (combination of raster and vector)"]
) -> str:
    """
    Execute custom Python code for raster operations with full flexibility.

    This tool allows you to write any Python code using allowed libraries to perform 
    raster analysis. You have complete freedom to implement any algorithm or computation.
    Your code MUST assign the final result to a variable named 'result'.
    
    The LLM should embed all necessary file paths and parameters directly in the code.
    For example:
        pre_fire = load_stac_items('/path/to/pre.json', bbox, ['B04', 'B08'], 10)
        post_fire = load_stac_items('/path/to/post.json', bbox, ['B04', 'B08'], 10)
    
    Args:
        code: Python code to execute. Must assign result to 'result' variable.
        result_explanation: Human-readable description of what the results represent.
        return_layer: If True, writes raster result as COG or vector as GeoJSON for map display
        expected_result_type: 'raster', 'vector', 'statistics', or 'mix'
        
    Returns:
        JSON string with execution results and output file paths if applicable
    """
    response_id = generate_response_id()
    
    try:
        print(f"Executing custom raster code: {result_explanation}")
        
        # Initialize executor
        executor = RasterCodeExecutor()
        
        # Validate code
        is_valid, validation_msg = executor.validate_code(code)
        if not is_valid:
            return build_error_response(
                source=AGENT_NAME,
                error_message=validation_msg,
                metadata={"validation_error": True}
            )
        
        start_time = time.time()
        
        # Execute code
        result_meta = executor.execute(code)
        
        if "error" in result_meta:
            return build_error_response(
                source=AGENT_NAME,
                error_message=result_meta["error"],
                metadata={"execution_error": True}
            )
        
        result = result_meta.get("result", None)
        metadata = result_meta.get("metadata", {})
        
        # Handle intermediate saving if requested
        if metadata.get("save_as_intermediate", False):
            intermediate_name = metadata.get("intermediate_name", f"intermediate_{uuid.uuid4().hex[:8]}")
            save_result = save_intermediate_results(result, intermediate_name)
            metadata.update(save_result)
            logger.info(f"Saved {save_result['count']} intermediate layer(s)")
            
            return build_intermediate_response(
                source=AGENT_NAME,
                data=metadata,
                summary=result_explanation,
                metadata=metadata
            )

        if isinstance(result, (tuple, list)):
            result = result[0]
        
        # Build base response
        response = {
            "success": True,
            "result_explanation": result_explanation,
            "result_type": expected_result_type,
            "layers": {},
            "metadata": metadata
        }
        # check if it is dict with single key and single value
        if isinstance(result, dict) and len(result) == 1:
            key, value = next(iter(result.items()))
            if isinstance(value, (xr.DataArray, gpd.GeoDataFrame)):
                result = value
        # Handle dict results (potentially temporal sequences)
        if isinstance(result, dict):
            for lbl, data in result.items():
                if isinstance(data, dict):
                    if len(data) > 1:
                        timeline_data = {k: x for k, x in data.items() if isinstance(x, xr.DataArray)}
                        if len(timeline_data) > 1:
                            timeline_layers = await handle_temporal_sequence(timeline_data)
                            response['layers'][lbl] = timeline_layers
                        elif len(timeline_data) == 1:
                            single_layer = await handle_single_raster(next(iter(timeline_data.values())))
                            response['layers'][lbl] = single_layer
                    else:
                        single_layer = await handle_single_raster(next(iter(data.values())))
                        response['layers'][lbl] = single_layer
                elif isinstance(data, xr.DataArray):
                    raster_layer = await handle_single_raster(data)
                    response['layers'][lbl] = raster_layer
                elif isinstance(data, gpd.GeoDataFrame):
                    # make sure data is in 4326
                    if data.crs != "EPSG:4326":
                        data = data.to_crs("EPSG:4326")
                    geojson_data = data.to_geo_dict()
                    artifact = await results_to_geojson(geojson_data, compute_stats=True)
                    response['layers'][lbl] = artifact.model_dump()

            return build_data_response(
                source=AGENT_NAME,
                data=[response],
                summary=result_explanation,
                data_type=DataType.RASTER_MULTI,
                metadata=response
            )

        # Handle single DataArray
        if isinstance(result, xr.DataArray):
            single_layer = await handle_single_raster(result)
            artifact_path = single_layer.get("path", "")
            crs = str(result.rio.crs) if hasattr(result, 'rio') and result.rio.crs else "EPSG:4326"
            bounds = list(result.rio.bounds()) if hasattr(result, 'rio') else []
            return build_raster_layer_response(
                source=AGENT_NAME,
                artifact_path=artifact_path,
                summary=result_explanation,
                crs=crs,
                bounds=bounds,
                stats=single_layer.get("stats"),
                metadata=response
            )
        
        # Handle GeoDataFrame
        if isinstance(result, gpd.GeoDataFrame):
            if return_layer:
                # project to 4326 if not
                if result.crs != "EPSG:4326":
                    result = result.to_crs("EPSG:4326")
                geojson_data = result.to_geo_dict()
                artifact = await results_to_geojson(geojson_data, compute_stats=True)
                response['output_type'] = 'geojson'
            
            # artifact is SavedArtifact object, not dict
            artifact_path = artifact.path if return_layer else ""
            return build_layer_response(
                source=AGENT_NAME,
                artifact_path=artifact_path,
                summary=result_explanation,
                features_count=len(result),
                stats=artifact.stats if return_layer else None,
                property_keys=artifact.property_keys if return_layer else None,
                geom_types=list(result.geom_type.unique()) if len(result) > 0 else None,
                metadata=response,
                data_type=DataType.VECTOR,
                artifact_format=ArtifactFormat.GEOJSON
            )
        
        # Unsupported result type
        return build_error_response(
            source=AGENT_NAME,
            error_message="Unsupported result type",
            metadata=response
        )
        
    except CodeExecutionError as e:
        logger.error(f"Code execution error: {e}")
        return build_error_response(
            source=AGENT_NAME,
            error_message=str(e),
            metadata={
                "error_type": "execution",
                "result_explanation": result_explanation,
                "traceback": traceback.format_exc()
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in execute_custom_raster_code: {e}", exc_info=True)
        return build_error_response(
            source=AGENT_NAME,
            error_message=str(e),
            metadata={
                "error_type": "unexpected",
                "result_explanation": result_explanation,
                "traceback": traceback.format_exc()
            }
        )
