# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
GeoJSON routes - upload, processing, and artifact management.
"""
import json
import logging
import os
import time
import uuid
from typing import Any
import aiofiles
import geopandas as gpd
import numpy as np
from shapely.validation import explain_validity
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from backend.routes.config import USER_DATA_PATH, USER_ARTIFACTS_JSON
from agents.core.types import GeoFahamToolResponse
from agents.core.response_store import get_response_store
from agents.shared.analysis import collect_property_schema

logger = logging.getLogger(__name__)
router = APIRouter()


async def process_uploaded_geojson(
    file_content: bytes,
    filename: str,
    title: str,
    description: str
) -> dict[str, Any]:
    """
    Process uploaded GeoJSON file:
    1. Validate it's valid GeoJSON
    2. Ensure CRS is EPSG:4326
    3. Compute artifact metadata
    4. Save to user_data folder
    5. Register in user_artifacts.json
    """
    try:
        # Parse GeoJSON
        geojson_data = json.loads(file_content.decode('utf-8'))
        
        # Validate it's GeoJSON
        if 'type' not in geojson_data:
            raise ValueError("Invalid GeoJSON: missing 'type' field")
        
        # Load as GeoDataFrame for CRS handling
        if geojson_data['type'] == 'FeatureCollection':
            features = geojson_data.get('features', [])
        elif geojson_data['type'] == 'Feature':
            features = [geojson_data]
        else:
            raise ValueError("GeoJSON must be a Feature or FeatureCollection")
        
        if not features:
            raise ValueError("GeoJSON contains no features")
        
        if any(not feature.get('geometry') for feature in features):
            raise ValueError("Each feature must contain a geometry")
        crs = geojson_data.get('crs')
        source_crs = 'EPSG:4326'
        if crs:
            if not isinstance(crs, dict) or crs.get('type') != 'name':
                raise ValueError("Unsupported CRS declaration; use a named EPSG CRS")
            source_crs = crs['properties']['name']
        gdf = gpd.GeoDataFrame.from_features(features, crs=source_crs).to_crs(epsg=4326)
        for geometry in gdf.geometry:
            if geometry is None or geometry.is_empty:
                raise ValueError("Each feature must contain a non-empty geometry")
            if not geometry.is_valid:
                raise ValueError(f"Invalid geometry: {explain_validity(geometry)}")
            if geometry.geom_type not in ('Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'):
                raise ValueError(f"Unsupported geometry type: {geometry.geom_type}")
        bounds = gdf.total_bounds
        if not np.isfinite(bounds).all() or bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -90 or bounds[3] > 90:
            raise ValueError("Coordinates are outside valid longitude/latitude bounds; check the input CRS")
        
        # Generate unique ID and save path
        file_id = uuid.uuid4().hex
        save_filename = f"{file_id}_{os.path.basename(filename)}"
        file_path = os.path.join(USER_DATA_PATH, save_filename)
        
        # Convert back to GeoJSON dict
        geojson_result = json.loads(gdf.to_json())
        
        # Save the file
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(geojson_result, ensure_ascii=False))
        
        features = geojson_result['features']
        property_keys = {
            'points': collect_property_schema(features, ['Point', 'MultiPoint']),
            'polygons': collect_property_schema(features, ['Polygon', 'MultiPolygon']),
            'lines': collect_property_schema(features, ['LineString', 'MultiLineString']),
        }
        geom_types = {feature['geometry']['type'] for feature in features}
        
        # Create artifact metadata
        artifact_data = {
            "artifact_id": file_id,
            "filename": filename,
            "title": title,
            "description": description,
            "upload_timestamp": time.time(),
            "artifact": {
                "path": file_path,
                "content_type": "application/geo+json",
                "format": "geojson",
                "bytes": os.path.getsize(file_path),
                "features_count": len(geojson_result.get("features", [])),
                "stats": None,
                "property_keys": property_keys,
                "geom_types": list(geom_types),
                "metadata": {"crs": "EPSG:4326", "bounds": bounds.tolist()},
            }
        }
        
        # Load existing user artifacts
        if os.path.exists(USER_ARTIFACTS_JSON):
            try:
                async with aiofiles.open(USER_ARTIFACTS_JSON, 'r') as f:
                    content = await f.read()
                    user_artifacts = json.loads(content)
            except:
                user_artifacts = []
        else:
            user_artifacts = []
        
        # Add new artifact
        user_artifacts.append(artifact_data)
        
        # Save updated user artifacts
        async with aiofiles.open(USER_ARTIFACTS_JSON, 'w') as f:
            await f.write(json.dumps(user_artifacts, indent=2))

        response = GeoFahamToolResponse(
            response_id=f"user_{file_id}", source="user", artifact=artifact_data['artifact'],
            summary=f"Uploaded file: {title}. {description}",
            metadata={"uploaded_file": True, "title": title, "filename": filename},
        )
        get_response_store().store(response)
        
        return {
            "success": True,
            "artifact_id": file_id,
            "response_id": response.response_id,
            "filename": save_filename,
            "features_count": artifact_data["artifact"]["features_count"],
            "geometry_types": artifact_data["artifact"]["geom_types"],
            "message": f"Successfully uploaded '{title}'"
        }
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error processing GeoJSON: {str(e)}")


@router.post("/api/upload-geojson")
async def upload_geojson(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form("")
):
    """
    Upload a GeoJSON file from user.
    Validates, converts to EPSG:4326, and registers in artifacts ledger.
    """
    # Validate file type
    if not file.filename.lower().endswith(('.geojson', '.json')):
        raise HTTPException(
            status_code=400,
            detail="Only GeoJSON files (.geojson or .json) are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        
        # Process the file
        result = await process_uploaded_geojson(
            file_content=content,
            filename=file.filename,
            title=title,
            description=description
        )
        
        return JSONResponse(content=result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading GeoJSON: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/api/user-artifacts")
async def get_user_artifacts():
    """Get list of all user-uploaded artifacts."""
    try:
        if not os.path.exists(USER_ARTIFACTS_JSON):
            return JSONResponse(content=[])
        
        async with aiofiles.open(USER_ARTIFACTS_JSON, 'r') as f:
            content = await f.read()
            user_artifacts = json.loads(content)
        
        return JSONResponse(content=user_artifacts)
    except Exception as e:
        logger.error(f"Error getting user artifacts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
