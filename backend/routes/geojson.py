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
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from backend.routes.config import USER_DATA_PATH, USER_ARTIFACTS_JSON

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
        
        gdf = gpd.GeoDataFrame.from_features(features)
        
        # Ensure CRS is EPSG:4326
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        
        # Generate unique ID and save path
        file_id = uuid.uuid4().hex
        save_filename = f"{file_id}_{filename}"
        file_path = os.path.join(USER_DATA_PATH, save_filename)
        
        # Convert back to GeoJSON dict
        geojson_result = json.loads(gdf.to_json())
        
        # Save the file
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(geojson_result, ensure_ascii=False))
        
        # Compute property keys and geometry types
        property_keys = {'points': {}, 'polygons': {}, 'lines': {}}
        geom_types = set()
        
        for feat in geojson_result.get("features", []):
            geom_type = feat['geometry']['type']
            geom_types.add(geom_type)
            props = feat.get('properties', {})
            
            if geom_type in ['Point', 'MultiPoint']:
                if not property_keys['points'] and props:
                    property_keys['points'] = {
                        k: type(v).__name__ if v is not None else "NoneType" 
                        for k, v in props.items()
                    }
            elif geom_type in ['Polygon', 'MultiPolygon']:
                if not property_keys['polygons'] and props:
                    property_keys['polygons'] = {
                        k: type(v).__name__ if v is not None else "NoneType" 
                        for k, v in props.items()
                    }
            elif geom_type in ['LineString', 'MultiLineString']:
                if not property_keys['lines'] and props:
                    property_keys['lines'] = {
                        k: type(v).__name__ if v is not None else "NoneType" 
                        for k, v in props.items()
                    }
        
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
                "geom_types": list(geom_types)
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
        
        return {
            "success": True,
            "artifact_id": file_id,
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
